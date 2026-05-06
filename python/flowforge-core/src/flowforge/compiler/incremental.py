"""``IncrementalCompiler`` — only-affected-slice regeneration (E-26).

Implements the §10.1 + §23.6 contract from
``framework/docs/jtbd-editor-arch.md``:

* Each generated file declares an *input set* (jtbd spec hashes,
  bundle metadata, role / permission digests, dep-graph hash).
* The build lockfile remembers the expected hash of every file's
  input set plus the hash of the previously rendered output.
* On rebuild, the compiler hashes the current input set; matching
  files are skipped, mismatched files are re-rendered. Files whose
  on-disk content has been hand-edited surface as
  :attr:`~PlanEntryStatus.HAND_EDITED` and are skipped unless
  ``force=True``.

Pure compute layer: no host-specific I/O, no jinja templates. The CLI
builds a list of :class:`FileTarget` objects (each carrying a
``render_callable`` that produces bytes) and hands them to
:meth:`IncrementalCompiler.plan` / :meth:`IncrementalCompiler.apply`.
Tests use the in-memory :class:`InMemoryFileStore`; production wires
:class:`LocalFileStore` rooted at the project directory.

The §23.6 cross-cutting files (``audit_taxonomy.py``,
``permissions.py``, dep-graph) are first-class — they are just
:class:`FileTarget` rows whose input set aggregates over every JTBD
in the bundle. Adding a ``requires:`` edge changes their input hash;
the compiler rebuilds them automatically.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .build_lockfile import (
	BuildLockfile,
	hash_bytes,
	hash_inputs,
)


# ---------------------------------------------------------------------------
# Filesystem abstraction
# ---------------------------------------------------------------------------


class FileStore(Protocol):
	"""Minimal read/write surface the compiler needs.

	Production wires :class:`LocalFileStore`; tests pass
	:class:`InMemoryFileStore` so the rebuild logic stays decoupled
	from disk I/O.
	"""

	def read(self, path: str) -> bytes:
		...

	def write(self, path: str, data: bytes) -> None:
		...

	def exists(self, path: str) -> bool:
		...

	def remove(self, path: str) -> None:
		...


@dataclasses.dataclass
class InMemoryFileStore:
	"""Dict-backed FileStore used in tests."""

	files: dict[str, bytes] = dataclasses.field(default_factory=dict)

	def read(self, path: str) -> bytes:
		return self.files[path]

	def write(self, path: str, data: bytes) -> None:
		self.files[path] = data

	def exists(self, path: str) -> bool:
		return path in self.files

	def remove(self, path: str) -> None:
		self.files.pop(path, None)


@dataclasses.dataclass
class LocalFileStore:
	"""Filesystem-backed FileStore rooted at *root*.

	Paths passed to :meth:`read` / :meth:`write` are interpreted
	relative to *root*. Writes create parent directories. Production
	wires this at the project root so generated files land beside
	hand-written code.
	"""

	root: Path

	def __post_init__(self) -> None:
		self.root = Path(self.root)

	def _full(self, path: str) -> Path:
		return self.root / path

	def read(self, path: str) -> bytes:
		return self._full(path).read_bytes()

	def write(self, path: str, data: bytes) -> None:
		full = self._full(path)
		full.parent.mkdir(parents=True, exist_ok=True)
		full.write_bytes(data)

	def exists(self, path: str) -> bool:
		return self._full(path).exists()

	def remove(self, path: str) -> None:
		full = self._full(path)
		if full.exists():
			full.unlink()


# ---------------------------------------------------------------------------
# Inputs + targets
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FileTarget:
	"""One generated-file target the caller wants to keep up to date.

	* ``path`` — relative path inside the project tree.
	* ``inputs`` — the file's input set as a plain dict. Values must be
	  JSON-encodable; they are hashed via :func:`hash_inputs` to derive
	  the rebuild key.
	* ``render`` — callable that produces the output bytes. Invoked
	  only when the compiler decides a rebuild is needed.
	* ``last_jtbd_version`` — optional pointer for traceability /
	  debugging. Stored in the lockfile entry verbatim.
	* ``protected_when_hand_edited`` — when True (default) the compiler
	  refuses to overwrite a hand-edited file unless ``force=True``.
	  Cross-cutting files (``audit_taxonomy.py``, ``permissions.py``)
	  set this to False because losing a hand edit on a cross-cutting
	  file would silently break tenants.
	"""

	path: str
	inputs: dict[str, Any]
	render: Callable[[], bytes]
	last_jtbd_version: str | None = None
	protected_when_hand_edited: bool = True


# ---------------------------------------------------------------------------
# Plan + result
# ---------------------------------------------------------------------------


class PlanEntryStatus(str, Enum):
	UNCHANGED = "unchanged"  # input hash matches lockfile + file on disk
	REBUILD = "rebuild"  # input hash differs (or file missing)
	HAND_EDITED = "hand_edited"  # disk content drifted from lockfile output_hash
	NEW = "new"  # no lockfile entry yet
	REMOVED = "removed"  # lockfile knows about it but caller dropped the target


@dataclasses.dataclass(frozen=True)
class PlanEntry:
	path: str
	status: PlanEntryStatus
	expected_input_hash: str
	last_input_hash: str | None
	last_jtbd_version: str | None

	@property
	def needs_rebuild(self) -> bool:
		return self.status in (PlanEntryStatus.REBUILD, PlanEntryStatus.NEW)


@dataclasses.dataclass(frozen=True)
class BuildPlan:
	entries: tuple[PlanEntry, ...]

	def by_status(self, status: PlanEntryStatus) -> tuple[PlanEntry, ...]:
		return tuple(e for e in self.entries if e.status is status)

	def rebuild_paths(self) -> tuple[str, ...]:
		return tuple(e.path for e in self.entries if e.needs_rebuild)


@dataclasses.dataclass(frozen=True)
class ApplyResult:
	rebuilt: tuple[str, ...]
	skipped_unchanged: tuple[str, ...]
	skipped_hand_edited: tuple[str, ...]
	removed: tuple[str, ...]


# ---------------------------------------------------------------------------
# IncrementalCompiler
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class IncrementalCompiler:
	"""Plan + apply incremental rebuilds against a :class:`BuildLockfile`.

	The compiler is stateful only via the *lockfile* it carries. After
	:meth:`apply`, the caller is expected to persist the lockfile via
	:meth:`BuildLockfile.save` (the compiler does not own the path).

	Algorithm sketch (see §23.6):

		expected_input_hash = hash_inputs(target.inputs)
		entry = lockfile.get(target.path)
		if entry is None:                              -> NEW (rebuild)
		elif entry.expected_input_hash == expected and
		     fs.exists(path) and
		     hash(fs.read(path)) == entry.output_hash: -> UNCHANGED
		elif fs.exists(path) and
		     hash(fs.read(path)) != entry.output_hash and
		     target.protected_when_hand_edited:        -> HAND_EDITED
		else:                                          -> REBUILD

		paths in lockfile but not in targets            -> REMOVED
	"""

	lockfile: BuildLockfile
	store: FileStore

	# ------------------------------------------------------------------
	# plan
	# ------------------------------------------------------------------

	def plan(self, targets: Iterable[FileTarget]) -> BuildPlan:
		target_list = list(targets)
		seen_paths: set[str] = set()
		entries: list[PlanEntry] = []

		for target in target_list:
			if target.path in seen_paths:
				raise ValueError(
					f"duplicate target path in plan: {target.path!r}"
				)
			seen_paths.add(target.path)
			expected = hash_inputs(target.inputs)
			lock_entry = self.lockfile.get(target.path)

			status: PlanEntryStatus
			last_input_hash: str | None
			last_jtbd_version: str | None

			if lock_entry is None:
				status = PlanEntryStatus.NEW
				last_input_hash = None
				last_jtbd_version = None
			else:
				last_input_hash = lock_entry.expected_input_hash
				last_jtbd_version = lock_entry.last_jtbd_version
				file_exists = self.store.exists(target.path)
				disk_hash = (
					hash_bytes(self.store.read(target.path))
					if file_exists
					else None
				)
				if disk_hash is not None and disk_hash != lock_entry.output_hash:
					# Hand-edited; protected unless caller flips the flag.
					if target.protected_when_hand_edited:
						status = PlanEntryStatus.HAND_EDITED
					else:
						status = PlanEntryStatus.REBUILD
				elif (
					lock_entry.expected_input_hash == expected
					and file_exists
				):
					status = PlanEntryStatus.UNCHANGED
				else:
					# Either the input hash drifted or the file was
					# deleted out from under us — rebuild.
					status = PlanEntryStatus.REBUILD

			entries.append(
				PlanEntry(
					path=target.path,
					status=status,
					expected_input_hash=expected,
					last_input_hash=last_input_hash,
					last_jtbd_version=last_jtbd_version,
				),
			)

		# Detect entries the caller dropped — paths in the lockfile
		# that no current target claims. The compiler stages them as
		# REMOVED so the caller can decide to delete them via
		# ``apply(plan, prune=True)``.
		for path in self.lockfile.paths():
			if path in seen_paths:
				continue
			lock_entry = self.lockfile.get(path)
			if lock_entry is None:
				continue
			entries.append(
				PlanEntry(
					path=path,
					status=PlanEntryStatus.REMOVED,
					expected_input_hash="",
					last_input_hash=lock_entry.expected_input_hash,
					last_jtbd_version=lock_entry.last_jtbd_version,
				),
			)

		return BuildPlan(entries=tuple(entries))

	# ------------------------------------------------------------------
	# apply
	# ------------------------------------------------------------------

	def apply(
		self,
		plan: BuildPlan,
		targets: Iterable[FileTarget],
		*,
		force: bool = False,
		prune: bool = False,
	) -> ApplyResult:
		"""Execute *plan* against the FileStore + lockfile.

		* ``force`` — overwrite hand-edited files anyway. The lockfile's
		  ``hand_edited`` flag clears on the next forced rebuild.
		* ``prune`` — delete files corresponding to ``REMOVED`` plan
		  entries and drop them from the lockfile.

		Returns an :class:`ApplyResult` summarising what happened so
		the caller can render a build report.
		"""
		by_path: dict[str, FileTarget] = {t.path: t for t in targets}
		rebuilt: list[str] = []
		skipped_unchanged: list[str] = []
		skipped_hand_edited: list[str] = []
		removed: list[str] = []

		for entry in plan.entries:
			if entry.status is PlanEntryStatus.UNCHANGED:
				skipped_unchanged.append(entry.path)
				continue
			if entry.status is PlanEntryStatus.HAND_EDITED and not force:
				# Surface but do not overwrite. Mark in lockfile so
				# downstream callers can show a banner.
				self.lockfile.mark_hand_edited(entry.path)
				skipped_hand_edited.append(entry.path)
				continue
			if entry.status is PlanEntryStatus.REMOVED:
				if prune and self.store.exists(entry.path):
					self.store.remove(entry.path)
				if prune:
					self.lockfile.remove(entry.path)
					removed.append(entry.path)
				continue
			# NEW / REBUILD / forced HAND_EDITED — render + write.
			target = by_path.get(entry.path)
			if target is None:
				# Should never happen — plan() only emits NEW/REBUILD
				# for paths that exist in the targets iterable.
				raise RuntimeError(
					f"plan asked to rebuild {entry.path!r} but the caller did"
					" not supply that target to apply()"
				)
			data = target.render()
			self.store.write(target.path, data)
			self.lockfile.record(
				target.path,
				expected_input_hash=entry.expected_input_hash,
				output_hash=hash_bytes(data),
				last_jtbd_version=target.last_jtbd_version,
				hand_edited=False,
			)
			rebuilt.append(target.path)

		return ApplyResult(
			rebuilt=tuple(rebuilt),
			skipped_unchanged=tuple(skipped_unchanged),
			skipped_hand_edited=tuple(skipped_hand_edited),
			removed=tuple(removed),
		)


__all__ = [
	"ApplyResult",
	"BuildPlan",
	"FileStore",
	"FileTarget",
	"IncrementalCompiler",
	"InMemoryFileStore",
	"LocalFileStore",
	"PlanEntry",
	"PlanEntryStatus",
]
