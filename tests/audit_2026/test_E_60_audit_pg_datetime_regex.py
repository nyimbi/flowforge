"""E-60 / AU-04 — audit-pg `_looks_like_datetime` tightening.

Audit finding (audit-fix-plan §4.3 AU-04, §7 E-60):

The legacy `_looks_like_datetime` matched any string starting with
``\\d{4}-\\d{2}-\\d{2}`` — a regex that also accepts a UUID like
``1234-56-78-9abc...`` and any numeric-prefixed event-id whose first
three groups happen to be 4-2-2 digits. The audit calls for a switch
to ``datetime.fromisoformat`` try/except so only genuine ISO-8601
datetime strings produce a True.

Acceptance: a UUID-shaped or hex-shaped event-id whose first 10 chars
*could* satisfy the old regex now resolves as the event-id cursor path,
not the datetime path.
"""

from __future__ import annotations


def test_AU_04_iso8601_dates_still_match() -> None:
	"""Genuine ISO-8601 datetimes are still recognised."""

	from flowforge_audit_pg.sink import _looks_like_datetime

	for good in (
		"2026-05-06",
		"2026-05-06T12:34:56",
		"2026-05-06T12:34:56.123",
		"2026-05-06T12:34:56+00:00",
		"2026-05-06T12:34:56.123456+02:00",
		"2026-05-06 12:34:56",  # Postgres-style space separator
	):
		assert _looks_like_datetime(good), f"expected {good!r} to be recognised as ISO-8601"


def test_AU_04_uuid_prefixed_digits_no_longer_match() -> None:
	"""A UUID like ``1234-56-78-9abc-...`` would have matched the
	original ``\\d{4}-\\d{2}-\\d{2}`` regex via its first 10 characters.
	The fromisoformat-backed gate rejects it."""

	from flowforge_audit_pg.sink import _looks_like_datetime

	uuid_like_strings = [
		# 8-4-4-4-12 hex with leading-digit segments
		"1234-56-78-9abc-def012345678",
		"2024-12-31-abcd-ef0123456789",
		# Looks like 4-2-2 prefix but invalid month/day
		"2026-13-99",  # month 13 / day 99 → fromisoformat rejects
		"2026-00-15",  # month 0 → reject
		"2026-02-30",  # invalid Feb day
		# Numeric event-id with embedded hyphens
		"1234-56-78-batch_42",
		# Plain string with a hyphenated digit prefix
		"abcd-ef-12",  # not even \\d{4} — pre-fix would not match either
	]
	for bad in uuid_like_strings:
		assert not _looks_like_datetime(bad), (
			f"{bad!r} must NOT be recognised as a datetime; falls through "
			f"to the event-id cursor path."
		)


def test_AU_04_event_id_shaped_strings_use_event_id_path() -> None:
	"""Common event-id shapes (UUID7 strings, ULIDs, hex digests) all
	resolve as event-ids, not datetimes."""

	from flowforge_audit_pg.sink import _looks_like_datetime

	event_ids = [
		"01HM7Z5J5R8RZHJVE6P4HSGXRS",  # ULID
		"018d6f15-3b2c-7c0f-9876-1234567890ab",  # UUID7
		"0123456789abcdef0123456789abcdef",  # hex digest
		"evt-20260506-001",  # human-readable but not ISO
		"event_42",
	]
	for eid in event_ids:
		assert not _looks_like_datetime(eid), (
			f"event-id {eid!r} must not be recognised as ISO-8601"
		)


def test_AU_04_empty_and_garbage_inputs_safe() -> None:
	"""Empty / garbage inputs return False without raising."""

	from flowforge_audit_pg.sink import _looks_like_datetime

	for s in ("", " ", "not-a-date", "9999", "T12:34:56", "2026"):
		assert _looks_like_datetime(s) is False
