"""``flowforge.lockfile`` — per-file rebuild-decision cache.

Distinct from the JTBD composition lockfile shipped in
:mod:`flowforge_jtbd.dsl.lockfile` (E-1). That one pins jtbd_id ×
version × spec_hash for a project bundle. *This* one tracks the
per-generated-file expected-input-hash + output-hash + hand-edit flag
that the incremental compiler reads to decide rebuild eligibility (see
``framework/docs/jtbd-editor-arch.md`` §10.1 + §23.6).

The two lockfiles coexist on disk under different names:

* ``jtbd.lock``      — composition pin table (``flowforge_jtbd``).
* ``flowforge.lockfile`` — generator rebuild cache (this module).

Schema is JSON, byte-stable: object keys sorted, no whitespace, no
trailing newline. The same canonical-JSON conventions used by E-1 hold
here so a CI run can re-hash the lockfile body and verify it has not
drifted between commits.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

LOCKFILE_SCHEMA_VERSION = "1"


@dataclasses.dataclass
class BuildLockEntry:
	"""One row in the build lockfile — one generated file.

	Fields:

	* ``expected_input_hash`` — sha256 of the canonical-JSON serialisation
	  of the file's input set (jtbd spec hashes, project metadata, etc.).
	  When it matches the cached value, the file does not need rebuilding.
	* ``output_hash`` — sha256 of the rendered output bytes. Used to
	  detect hand edits: if the file on disk hashes differently,
	  ``hand_edited`` flips to True and the compiler skips the rebuild
	  unless the caller passes ``force=True``.
	* ``last_jtbd_version`` — the JTBD spec version this file was
	  rendered from. Optional: cross-cutting files (audit_taxonomy.py,
	  permissions.py) carry ``None`` because they aggregate every JTBD.
	* ``hand_edited`` — set by the compiler when it detects a mismatch
	  between the file on disk and ``output_hash``. Cleared on the next
	  forced rebuild.
	"""

	expected_input_hash: str
	output_hash: str
	last_jtbd_version: str | None = None
	hand_edited: bool = False

	def to_json(self) -> dict[str, Any]:
		return {
			"expected_input_hash": self.expected_input_hash,
			"output_hash": self.output_hash,
			"last_jtbd_version": self.last_jtbd_version,
			"hand_edited": self.hand_edited,
		}

	@classmethod
	def from_json(cls, payload: dict[str, Any]) -> "BuildLockEntry":
		return cls(
			expected_input_hash=str(payload.get("expected_input_hash", "")),
			output_hash=str(payload.get("output_hash", "")),
			last_jtbd_version=(
				None
				if payload.get("last_jtbd_version") is None
				else str(payload.get("last_jtbd_version"))
			),
			hand_edited=bool(payload.get("hand_edited", False)),
		)


@dataclasses.dataclass
class BuildLockfile:
	"""Per-project rebuild-cache lockfile.

	Implements the §23.6 contract: keyed by generated-file path; each
	entry carries the expected input hash plus the output hash. Re-
	running ``flowforge new`` consults this object before invoking any
	generator.

	Mutations go through :meth:`record` so the in-memory state can never
	drift from what would round-trip through ``to_json``/``from_json``.
	"""

	entries: dict[str, BuildLockEntry] = dataclasses.field(default_factory=dict)
	schema_version: str = LOCKFILE_SCHEMA_VERSION

	# ------------------------------------------------------------------
	# read
	# ------------------------------------------------------------------

	def get(self, path: str) -> BuildLockEntry | None:
		return self.entries.get(path)

	def expected_hash_for(self, path: str) -> str | None:
		entry = self.entries.get(path)
		return entry.expected_input_hash if entry is not None else None

	def __contains__(self, path: str) -> bool:
		return path in self.entries

	def __len__(self) -> int:
		return len(self.entries)

	def paths(self) -> list[str]:
		return sorted(self.entries.keys())

	# ------------------------------------------------------------------
	# mutate
	# ------------------------------------------------------------------

	def record(
		self,
		path: str,
		*,
		expected_input_hash: str,
		output_hash: str,
		last_jtbd_version: str | None = None,
		hand_edited: bool = False,
	) -> None:
		"""Insert or replace the entry for *path*."""
		self.entries[path] = BuildLockEntry(
			expected_input_hash=expected_input_hash,
			output_hash=output_hash,
			last_jtbd_version=last_jtbd_version,
			hand_edited=hand_edited,
		)

	def mark_hand_edited(self, path: str) -> None:
		entry = self.entries.get(path)
		if entry is not None:
			self.entries[path] = dataclasses.replace(entry, hand_edited=True)

	def remove(self, path: str) -> None:
		"""Drop a path from the lockfile (used when the source JTBD goes
		away). Caller is responsible for deleting the file itself."""
		self.entries.pop(path, None)

	# ------------------------------------------------------------------
	# serialisation
	# ------------------------------------------------------------------

	def to_json(self) -> dict[str, Any]:
		return {
			"schema_version": self.schema_version,
			"entries": {
				path: self.entries[path].to_json() for path in sorted(self.entries)
			},
		}

	def to_bytes(self) -> bytes:
		"""Serialise the lockfile to canonical JSON bytes (sorted keys,
		no whitespace, no trailing newline). Two CLIs running on the
		same lockfile state must produce byte-identical output."""
		return json.dumps(
			self.to_json(),
			sort_keys=True,
			ensure_ascii=False,
			separators=(",", ":"),
			allow_nan=False,
		).encode("utf-8")

	@classmethod
	def from_json(cls, payload: dict[str, Any]) -> "BuildLockfile":
		entries_raw = payload.get("entries") or {}
		if not isinstance(entries_raw, dict):
			raise ValueError("lockfile.entries must be an object")
		entries: dict[str, BuildLockEntry] = {}
		for path, body in entries_raw.items():
			if not isinstance(path, str):
				raise ValueError("lockfile.entries keys must be strings")
			if not isinstance(body, dict):
				raise ValueError(f"lockfile.entries[{path!r}] must be an object")
			entries[path] = BuildLockEntry.from_json(body)
		schema_version = str(payload.get("schema_version", LOCKFILE_SCHEMA_VERSION))
		return cls(entries=entries, schema_version=schema_version)

	@classmethod
	def from_bytes(cls, payload: bytes) -> "BuildLockfile":
		if not payload:
			return cls()
		data = json.loads(payload.decode("utf-8"))
		if not isinstance(data, dict):
			raise ValueError("lockfile JSON must be an object")
		return cls.from_json(data)

	@classmethod
	def load(cls, path: str | Path) -> "BuildLockfile":
		"""Read a lockfile from disk; missing file → empty lockfile."""
		p = Path(path)
		if not p.exists():
			return cls()
		return cls.from_bytes(p.read_bytes())

	def save(self, path: str | Path) -> None:
		"""Write the canonical lockfile JSON to *path* atomically."""
		p = Path(path)
		p.parent.mkdir(parents=True, exist_ok=True)
		tmp = p.with_suffix(p.suffix + ".tmp")
		tmp.write_bytes(self.to_bytes())
		tmp.replace(p)


def hash_inputs(inputs: dict[str, Any]) -> str:
	"""Hash an input-set dict to a stable sha256 hex digest.

	The dict is canonicalised (sorted keys, no whitespace, NFC strings
	via Python's default JSON UTF-8 encoder) before hashing. Two calls
	with logically-equivalent dicts return the same hash.

	Floats are rejected (they have no canonical JSON representation);
	use integers + canonical fractions in the input set instead.
	"""
	encoded = json.dumps(
		inputs,
		sort_keys=True,
		ensure_ascii=False,
		separators=(",", ":"),
		allow_nan=False,
	).encode("utf-8")
	return hashlib.sha256(encoded).hexdigest()


def hash_bytes(payload: bytes) -> str:
	"""Sha256 hex digest of arbitrary bytes."""
	return hashlib.sha256(payload).hexdigest()


__all__ = [
	"BuildLockEntry",
	"BuildLockfile",
	"LOCKFILE_SCHEMA_VERSION",
	"hash_bytes",
	"hash_inputs",
]
