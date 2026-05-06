"""replaced_by migration runner for JTBD bundles (E-3).

A deprecated JTBD carries ``replaced_by: <new_jtbd_id>``.  This module:

1. Resolves the full replacement chain (e.g. ``a → b → c``) up to a
   configurable depth ceiling.
2. Diffs the ``data_capture`` shape between the head and tail of the chain,
   classifying fields as added / removed / changed.
3. Optionally applies the diff to a concrete data record:
   - removed fields are dropped (with a warning list when they carried values),
   - added fields are set to ``None`` (callers supply domain defaults).
4. Renders the diff as a human-readable text block for CLI display.
5. Provides a :func:`build_migration` convenience function that combines
   chain resolution + shape diff in a single call.

All public functions operate on plain ``dict`` objects so the runner can be
used before the full Pydantic model layer (E-1) is wired up.
"""

from __future__ import annotations

import dataclasses
from typing import Any


class MigrationError(ValueError):
	"""Raised when the runner cannot resolve a replacement chain."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FieldChange:
	"""A field whose ``kind`` changed between old and new JTBD."""

	id: str
	old_kind: str
	new_kind: str


@dataclasses.dataclass(frozen=True)
class MigrationDiff:
	"""Structural diff of ``data_capture`` between two JTBD specs."""

	from_id: str
	to_id: str
	chain: tuple[str, ...]           # full replacement chain
	added: tuple[str, ...]           # field ids in new but not old
	removed: tuple[str, ...]         # field ids in old but not new
	changed: tuple[FieldChange, ...] # same field id, different kind


@dataclasses.dataclass(frozen=True)
class ApplyResult:
	"""Result of applying a :class:`MigrationDiff` to a concrete data record."""

	chain: tuple[str, ...]
	record: dict[str, Any]
	dropped: tuple[str, ...]  # removed fields that had non-None values in input


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _index_jtbds(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
	return {j["id"]: j for j in bundle.get("jtbds", []) or []}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_chain(
	bundle: dict[str, Any],
	start_id: str,
	*,
	max_depth: int = 32,
) -> list[str]:
	"""Follow ``replaced_by`` pointers from *start_id* to the terminal JTBD.

	Returns the full chain starting at *start_id* (inclusive).  A JTBD
	that is not deprecated returns a single-element list.

	Raises :exc:`MigrationError` on:
	- *start_id* missing from bundle
	- a ``replaced_by`` target missing from bundle
	- a cycle in the replacement chain
	- chain length exceeding *max_depth*
	"""
	assert isinstance(bundle, dict), "bundle must be a dict"
	assert start_id, "start_id must be a non-empty string"
	assert max_depth > 0, "max_depth must be positive"

	index = _index_jtbds(bundle)
	if start_id not in index:
		raise MigrationError(f"JTBD '{start_id}' not found in bundle")

	chain: list[str] = [start_id]
	seen: set[str] = {start_id}
	current = index[start_id]

	while True:
		replaced_by: str | None = current.get("replaced_by")
		if not replaced_by:
			break
		if len(chain) >= max_depth:
			raise MigrationError(
				f"replaced_by chain exceeded max_depth={max_depth}: "
				+ " → ".join(chain)
			)
		if replaced_by in seen:
			raise MigrationError(
				"cycle detected in replaced_by chain: "
				+ " → ".join(chain)
				+ f" → {replaced_by}"
			)
		if replaced_by not in index:
			raise MigrationError(
				f"replaced_by target '{replaced_by}' not found in bundle "
				f"(chain so far: {' → '.join(chain)})"
			)
		chain.append(replaced_by)
		seen.add(replaced_by)
		current = index[replaced_by]

	return chain


def diff_shapes(
	old_jtbd: dict[str, Any],
	new_jtbd: dict[str, Any],
) -> MigrationDiff:
	"""Compute the ``data_capture`` diff between *old_jtbd* and *new_jtbd*.

	*   **added**   — field ids present in new but not old
	*   **removed** — field ids present in old but not new
	*   **changed** — field ids in both whose ``kind`` differs

	The ``chain`` on the returned diff contains only ``(from_id, to_id)``.
	Use :func:`build_migration` to get a diff with the full chain populated.
	"""
	assert isinstance(old_jtbd, dict), "old_jtbd must be a dict"
	assert isinstance(new_jtbd, dict), "new_jtbd must be a dict"

	old_fields: dict[str, dict[str, Any]] = {
		f["id"]: f for f in old_jtbd.get("data_capture", []) or []
	}
	new_fields: dict[str, dict[str, Any]] = {
		f["id"]: f for f in new_jtbd.get("data_capture", []) or []
	}

	old_ids = set(old_fields)
	new_ids = set(new_fields)

	added = tuple(sorted(new_ids - old_ids))
	removed = tuple(sorted(old_ids - new_ids))
	changed = tuple(
		FieldChange(
			id=fid,
			old_kind=old_fields[fid].get("kind", ""),
			new_kind=new_fields[fid].get("kind", ""),
		)
		for fid in sorted(old_ids & new_ids)
		if old_fields[fid].get("kind") != new_fields[fid].get("kind")
	)

	return MigrationDiff(
		from_id=old_jtbd["id"],
		to_id=new_jtbd["id"],
		chain=(old_jtbd["id"], new_jtbd["id"]),
		added=added,
		removed=removed,
		changed=changed,
	)


def build_migration(
	bundle: dict[str, Any],
	start_id: str,
	*,
	max_depth: int = 32,
) -> MigrationDiff:
	"""Resolve the replacement chain and return a complete :class:`MigrationDiff`.

	Combines :func:`resolve_chain` + :func:`diff_shapes` in a single call,
	and populates the diff's ``chain`` with the full resolution path.
	"""
	chain = resolve_chain(bundle, start_id, max_depth=max_depth)
	index = _index_jtbds(bundle)
	diff = diff_shapes(index[chain[0]], index[chain[-1]])
	return dataclasses.replace(diff, chain=tuple(chain))


def apply_to_record(
	diff: MigrationDiff,
	record: dict[str, Any],
) -> ApplyResult:
	"""Apply *diff* to a concrete data *record*.

	Rules:

	- Removed fields are dropped; if a removed field had a non-``None``
	  value it is reported in :attr:`ApplyResult.dropped`.
	- Added fields are initialised to ``None``; callers supply defaults.
	- Changed fields (``kind`` change only) are kept as-is; callers must
	  coerce values as needed.
	"""
	assert isinstance(diff, MigrationDiff), "diff must be a MigrationDiff"
	assert isinstance(record, dict), "record must be a dict"

	out = dict(record)
	dropped: list[str] = []

	for fid in diff.removed:
		val = out.pop(fid, None)
		if val is not None:
			dropped.append(fid)

	for fid in diff.added:
		if fid not in out:
			out[fid] = None

	return ApplyResult(chain=diff.chain, record=out, dropped=tuple(dropped))


def format_diff_text(diff: MigrationDiff) -> str:
	"""Render *diff* as a human-readable text block suitable for CLI output."""
	chain_str = " → ".join(diff.chain)
	lines: list[str] = [
		f"replacement chain : {chain_str}",
		f"from              : {diff.from_id}",
		f"to                : {diff.to_id}",
		"",
	]
	if not (diff.added or diff.removed or diff.changed):
		lines.append("  (no data_capture changes)")
	else:
		for fid in diff.added:
			lines.append(f"  + {fid}")
		for fid in diff.removed:
			lines.append(f"  - {fid}")
		for ch in diff.changed:
			lines.append(f"  ~ {ch.id}  ({ch.old_kind} → {ch.new_kind})")

	return "\n".join(lines)


__all__ = [
	"ApplyResult",
	"FieldChange",
	"MigrationDiff",
	"MigrationError",
	"apply_to_record",
	"build_migration",
	"diff_shapes",
	"format_diff_text",
	"resolve_chain",
]
