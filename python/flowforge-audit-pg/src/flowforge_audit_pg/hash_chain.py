"""Hash-chain helpers for flowforge-audit-pg.

Mirrors the logic in backend/app/audit/integrity.py but is self-contained
so the framework package has no dependency on the UMS application layer.

Algorithm (sha256 chain):
    row_sha256 = sha256( (prev_sha256 or "") + canonical_json(row_data) )

The canonical_json encoding is deterministic: sorted keys, no whitespace,
ISO-8601 datetimes, UUIDs as str.  The tombstone marker written by
:func:`redact_payload` preserves the original sha256 so the chain stays
valid after GDPR redactions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------

TOMBSTONE = "__REDACTED__"


def _default(obj: Any) -> Any:
	if isinstance(obj, (datetime, date)):
		return obj.isoformat()
	if isinstance(obj, UUID):
		return str(obj)
	if isinstance(obj, Decimal):
		return str(obj)
	raise TypeError(f"not serialisable: {type(obj)!r}")


def canonical_json(data: dict[str, Any]) -> str:
	"""Deterministic JSON: sorted keys, no whitespace, ISO datetimes."""
	return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default)


def sha256_hex(text: str) -> str:
	return hashlib.sha256(text.encode()).hexdigest()


def compute_row_sha(prev_sha: str | None, row_data: dict[str, Any]) -> str:
	"""Return sha256( (prev_sha or "") + canonical_json(row_data) )."""
	return sha256_hex((prev_sha or "") + canonical_json(row_data))


# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------

def _set_nested(obj: Any, path_parts: list[str], marker: str) -> Any:
	"""Return a copy of *obj* with *path_parts* overwritten with *marker*.

	Supports dotted paths into nested dicts.  If a path segment is missing
	the original object is returned unchanged (soft failure — the chain
	must not break on non-existent paths).
	"""
	if not path_parts:
		return marker
	key = path_parts[0]
	if not isinstance(obj, dict) or key not in obj:
		return obj
	copy = dict(obj)
	copy[key] = _set_nested(obj[key], path_parts[1:], marker)
	return copy


def redact_payload(
	payload: dict[str, Any],
	paths: list[str],
) -> dict[str, Any]:
	"""Return a new payload dict with each dotted *path* set to TOMBSTONE.

	The chain columns (prev_sha256, row_sha256) are NOT touched; only the
	payload content changes.  The caller is responsible for persisting
	the returned value while keeping hash columns intact.

	Example::

		>>> redact_payload({"name": "Alice", "extra": {"ssn": "123"}},
		...                ["name", "extra.ssn"])
		{'name': '__REDACTED__', 'extra': {'ssn': '__REDACTED__'}}
	"""
	result = dict(payload)
	for path in paths:
		parts = path.split(".")
		result = _set_nested(result, parts, TOMBSTONE)  # type: ignore[assignment]
	return result


# ---------------------------------------------------------------------------
# In-memory chain verification
# ---------------------------------------------------------------------------

def _row_to_canonical_dict(row: "AuditRow") -> dict[str, Any]:
	"""Reconstruct the dict used when the row was originally written."""
	return {
		"tenant_id": row.tenant_id,
		"actor_user_id": row.actor_user_id,
		"kind": row.kind,
		"subject_kind": row.subject_kind,
		"subject_id": row.subject_id,
		"occurred_at": row.occurred_at,
		"payload": row.payload,
	}


def verify_chain_in_memory(rows: list["AuditRow"]) -> tuple[bool, str | None]:
	"""Verify a pre-fetched, ascending-order list of AuditRow objects.

	Returns ``(True, None)`` when the chain is intact or the list is empty.
	Returns ``(False, bad_event_id)`` for the first row whose sha256 does not
	match the recomputed value.

	Rows with ``row_sha256=None`` are skipped — they pre-date the chain.
	"""
	prev_sha: str | None = None
	for row in rows:
		if row.row_sha256 is None:
			# Legacy row — skip but do not advance prev_sha so the chain
			# "starts" at the first hashed row.
			continue
		canonical = canonical_json(_row_to_canonical_dict(row))
		expected = sha256_hex((prev_sha or "") + canonical)
		if row.row_sha256 != expected:
			return False, row.event_id
		prev_sha = row.row_sha256
	return True, None


# ---------------------------------------------------------------------------
# Lightweight row dataclass (used by both sink and tests)
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402


@dataclass
class AuditRow:
	"""In-memory representation of one audit_events row."""

	event_id: str
	tenant_id: str | None
	actor_user_id: str | None
	kind: str
	subject_kind: str
	subject_id: str
	occurred_at: datetime
	payload: dict[str, Any]
	prev_sha256: str | None = None
	row_sha256: str | None = None
