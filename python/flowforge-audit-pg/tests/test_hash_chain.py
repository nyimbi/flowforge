"""Unit tests for flowforge_audit_pg.hash_chain.

No database required — pure in-memory logic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from flowforge_audit_pg.hash_chain import (
	TOMBSTONE,
	AuditRow,
	canonical_json,
	compute_row_sha,
	redact_payload,
	sha256_hex,
	verify_chain_in_memory,
)


# ---------------------------------------------------------------------------
# canonical_json
# ---------------------------------------------------------------------------

def test_canonical_json_sorted_keys():
	"""Keys must be sorted so encoding is deterministic."""
	d = {"z": 1, "a": 2, "m": 3}
	raw = canonical_json(d)
	assert raw == '{"a":2,"m":3,"z":1}'


def test_canonical_json_datetime_iso():
	dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
	raw = canonical_json({"ts": dt})
	assert "2024-06-01T12:00:00+00:00" in raw


def test_canonical_json_no_whitespace():
	raw = canonical_json({"key": "val"})
	assert " " not in raw


def test_canonical_json_stable():
	"""Same dict -> same bytes on repeated calls."""
	d = {"b": [1, 2], "a": {"x": True}}
	assert canonical_json(d) == canonical_json(d)


# ---------------------------------------------------------------------------
# sha256_hex / compute_row_sha
# ---------------------------------------------------------------------------

def test_sha256_hex_known_value():
	assert sha256_hex("abc") == hashlib.sha256(b"abc").hexdigest()


def test_compute_row_sha_no_prev():
	data = {"kind": "test", "value": 42}
	expected = sha256_hex(canonical_json(data))
	assert compute_row_sha(None, data) == expected


def test_compute_row_sha_with_prev():
	prev = "deadbeef" * 8  # 64-char fake sha
	data = {"kind": "test"}
	expected = sha256_hex(prev + canonical_json(data))
	assert compute_row_sha(prev, data) == expected


def test_compute_row_sha_chaining():
	"""sha2 must differ from sha1 and depend on sha1."""
	data1 = {"kind": "a"}
	data2 = {"kind": "b"}
	sha1 = compute_row_sha(None, data1)
	sha2 = compute_row_sha(sha1, data2)
	assert sha1 != sha2
	sha2_no_prev = compute_row_sha(None, data2)
	assert sha2 != sha2_no_prev


# ---------------------------------------------------------------------------
# redact_payload
# ---------------------------------------------------------------------------

def test_redact_top_level_key():
	payload = {"name": "Alice", "age": 30}
	result = redact_payload(payload, ["name"])
	assert result["name"] == TOMBSTONE
	assert result["age"] == 30  # untouched


def test_redact_nested_dotted_path():
	payload = {"person": {"ssn": "123-45-6789", "dob": "1990-01-01"}}
	result = redact_payload(payload, ["person.ssn"])
	assert result["person"]["ssn"] == TOMBSTONE
	assert result["person"]["dob"] == "1990-01-01"


def test_redact_multiple_paths():
	payload = {"a": "keep", "b": "redact", "c": {"d": "redact_too"}}
	result = redact_payload(payload, ["b", "c.d"])
	assert result["a"] == "keep"
	assert result["b"] == TOMBSTONE
	assert result["c"]["d"] == TOMBSTONE


def test_redact_missing_path_is_noop():
	"""A path that doesn't exist must not raise and must return payload unchanged."""
	payload = {"x": 1}
	result = redact_payload(payload, ["nonexistent"])
	assert result == {"x": 1}


def test_redact_does_not_mutate_original():
	payload = {"secret": "value"}
	_ = redact_payload(payload, ["secret"])
	assert payload["secret"] == "value"


def test_tombstone_marker_value():
	assert TOMBSTONE == "__REDACTED__"


# ---------------------------------------------------------------------------
# verify_chain_in_memory
# ---------------------------------------------------------------------------

def _make_row(
	event_id: str,
	kind: str,
	prev_sha: str | None,
	row_sha: str | None,
	*,
	tenant_id: str = "t1",
) -> AuditRow:
	now = datetime(2024, 1, 1, tzinfo=timezone.utc)
	return AuditRow(
		event_id=event_id,
		tenant_id=tenant_id,
		actor_user_id=None,
		kind=kind,
		subject_kind="workflow",
		subject_id="wf-1",
		occurred_at=now,
		payload={},
		prev_sha256=prev_sha,
		row_sha256=row_sha,
	)


def _build_valid_chain(n: int) -> list[AuditRow]:
	"""Build a valid hash chain of length *n*."""
	rows: list[AuditRow] = []
	prev_sha: str | None = None
	for i in range(n):
		row = _make_row(f"e{i}", f"event.{i}", prev_sha=None, row_sha=None)
		from flowforge_audit_pg.hash_chain import _row_to_canonical_dict
		row_data = _row_to_canonical_dict(row)
		row_sha = compute_row_sha(prev_sha, row_data)
		row.prev_sha256 = prev_sha
		row.row_sha256 = row_sha
		rows.append(row)
		prev_sha = row_sha
	return rows


def test_empty_chain_is_ok():
	ok, bad = verify_chain_in_memory([])
	assert ok is True
	assert bad is None


def test_single_row_chain():
	rows = _build_valid_chain(1)
	ok, bad = verify_chain_in_memory(rows)
	assert ok is True
	assert bad is None


def test_valid_three_row_chain():
	rows = _build_valid_chain(3)
	ok, bad = verify_chain_in_memory(rows)
	assert ok is True


def test_tampered_row_detected():
	rows = _build_valid_chain(3)
	# Tamper with the payload of row 1 after chain was built.
	rows[1].payload["tampered"] = True
	ok, bad = verify_chain_in_memory(rows)
	assert ok is False
	assert bad == "e1"


def test_tampered_last_row_detected():
	rows = _build_valid_chain(4)
	rows[-1].payload["evil"] = "injected"
	ok, bad = verify_chain_in_memory(rows)
	assert ok is False
	assert bad == f"e{len(rows) - 1}"


def test_null_sha_rows_skipped():
	"""Rows with row_sha256=None are treated as legacy and skipped."""
	row = _make_row("legacy", "old.event", prev_sha=None, row_sha=None)
	row.row_sha256 = None
	ok, bad = verify_chain_in_memory([row])
	assert ok is True
	assert bad is None


def test_redacted_payload_breaks_chain():
	"""Redaction changes the payload so the chain hash no longer matches.

	This is the expected behaviour — redaction is a deliberate audit action
	and verify_chain should flag it, signalling that the row was modified
	post-write.  Operators document the redaction via the reason field.
	"""
	rows = _build_valid_chain(2)
	# Simulate what redact() does: update payload but keep sha columns.
	rows[0].payload["ssn"] = TOMBSTONE
	ok, _ = verify_chain_in_memory(rows)
	assert ok is False


def test_chain_detects_inserted_row():
	"""Inserting a row in the middle with a recalculated sha for itself but
	without updating subsequent rows breaks the chain."""
	rows = _build_valid_chain(3)
	# Build a row that fits between rows[0] and rows[1] but doesn't update
	# rows[1].prev_sha256.
	from flowforge_audit_pg.hash_chain import _row_to_canonical_dict
	inserted = _make_row("inserted", "injected.event", prev_sha=None, row_sha=None)
	inserted_data = _row_to_canonical_dict(inserted)
	inserted.prev_sha256 = rows[0].row_sha256
	inserted.row_sha256 = compute_row_sha(rows[0].row_sha256, inserted_data)
	# Splice in between rows[0] and rows[1] without re-chaining rows[1..2].
	tampered = [rows[0], inserted, rows[1], rows[2]]
	ok, bad = verify_chain_in_memory(tampered)
	assert ok is False
