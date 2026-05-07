"""Canonical-bytes golden fixture loader/regenerator (E-37 AU-03).

Why this exists
---------------
The audit row sha256 chain uses a deterministic canonical-JSON encoding
(:func:`flowforge_audit_pg.hash_chain.canonical_json`). If a release ever
changes the encoding (sort order, separators, default encoder, …) every
existing audit row's ``row_sha256`` becomes invalid retroactively. SOX
and HIPAA both treat that as data destruction — hence the AU-03
escalation to P1 / S0.

This module owns:

- ``GoldenRow`` / ``GoldenBundle`` — the on-disk shape.
- :func:`build_golden` — produce the bundle from a fixed input vector.
- :func:`write_golden` — serialise + sign the bundle (envelope sha256).
- :func:`load_golden` — verify the envelope and return the bundle.
- :func:`recompute_row` — recompute ``canonical_json + row_sha256`` for a
  single golden row using the in-process helpers; tests assert these
  match the committed bytes.
- ``__main__`` — ``python -m flowforge_audit_pg._golden write <path>`` to
  regenerate the committed fixture after a deliberate format change.

Format
------
The on-disk file is a length-prefixed stream::

    b"FFAUDITGOLDEN\x01"            # magic + version byte
    sha256(payload).hex().encode()  # 64 ascii bytes — envelope hash
    b"\\n"
    payload                         # JSON-encoded list[dict]

Where ``payload`` lists rows with their input dict, the canonical bytes,
the (computed) row_sha256, and the prev_sha256 they should chain off.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hash_chain import canonical_json, compute_row_sha


_MAGIC = b"FFAUDITGOLDEN\x01"


class GoldenIntegrityError(Exception):
	"""Raised when the on-disk envelope sha256 does not match the payload."""


@dataclass(frozen=True)
class GoldenRow:
	"""One row of the golden fixture."""

	event_id: str
	prev_sha256: str | None
	input: dict[str, Any]
	canonical_json_bytes: bytes
	row_sha256: str


@dataclass(frozen=True)
class GoldenBundle:
	"""The full fixture, plus the envelope hash that signed it."""

	rows: list[GoldenRow]
	envelope_sha: str


# ---------------------------------------------------------------------------
# Canonical input vector — DO NOT MODIFY without a SOX/HIPAA-tagged change.
#
# Five rows, mixed shapes, mixed null/non-null fields, with both ASCII and
# unicode payload to surface encoder drift.
# ---------------------------------------------------------------------------


_BASE_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _canonical_input_vector() -> list[dict[str, Any]]:
	return [
		{
			"event_id": "00000000-0000-7000-8000-000000000001",
			"tenant_id": "tenant-A",
			"actor_user_id": "user-1",
			"kind": "workflow.fired",
			"subject_kind": "workflow_instance",
			"subject_id": "wf-1",
			"occurred_at": _BASE_TS,
			"payload": {"amount": 100, "currency": "USD"},
		},
		{
			"event_id": "00000000-0000-7000-8000-000000000002",
			"tenant_id": "tenant-A",
			"actor_user_id": None,
			"kind": "workflow.guard_passed",
			"subject_kind": "workflow_instance",
			"subject_id": "wf-1",
			"occurred_at": _BASE_TS.replace(second=1),
			"payload": {"guard": "amount > 0", "result": True},
		},
		{
			"event_id": "00000000-0000-7000-8000-000000000003",
			"tenant_id": "tenant-A",
			"actor_user_id": "user-2",
			"kind": "workflow.completed",
			"subject_kind": "workflow_instance",
			"subject_id": "wf-1",
			"occurred_at": _BASE_TS.replace(second=2),
			"payload": {"note": "héllo wörld 🚀", "approved_by": ["user-2"]},
		},
		{
			"event_id": "00000000-0000-7000-8000-000000000004",
			"tenant_id": None,  # null tenant — pre-multitenancy row
			"actor_user_id": "system",
			"kind": "system.bootstrap",
			"subject_kind": "system",
			"subject_id": "boot-1",
			"occurred_at": _BASE_TS.replace(year=2025, month=12, day=31, hour=23),
			"payload": {},
		},
		{
			"event_id": "00000000-0000-7000-8000-000000000005",
			"tenant_id": "tenant-B",
			"actor_user_id": "user-X",
			"kind": "workflow.fired",
			"subject_kind": "workflow_instance",
			"subject_id": "wf-99",
			"occurred_at": _BASE_TS.replace(month=2),
			"payload": {"nested": {"a": [1, 2, 3], "b": None}},
		},
	]


def build_golden() -> GoldenBundle:
	"""Build the golden bundle from the canonical input vector.

	Each row chains off the previous row's ``row_sha256``; the bundle is
	thus an end-to-end test of both ``canonical_json`` and the chain math.
	"""
	rows: list[GoldenRow] = []
	prev_sha: str | None = None
	for inp in _canonical_input_vector():
		event_id = inp["event_id"]
		row_input = {k: v for k, v in inp.items() if k != "event_id"}
		canonical_str = canonical_json(row_input)
		canonical_bytes = canonical_str.encode("utf-8")
		row_sha = compute_row_sha(prev_sha, row_input)
		rows.append(
			GoldenRow(
				event_id=event_id,
				prev_sha256=prev_sha,
				input=row_input,
				canonical_json_bytes=canonical_bytes,
				row_sha256=row_sha,
			)
		)
		prev_sha = row_sha

	envelope_sha = _envelope_sha(rows)
	return GoldenBundle(rows=rows, envelope_sha=envelope_sha)


def _envelope_sha(rows: list[GoldenRow]) -> str:
	hasher = hashlib.sha256()
	for r in rows:
		hasher.update(r.event_id.encode("utf-8"))
		hasher.update(b"\x00")
		hasher.update((r.prev_sha256 or "").encode("utf-8"))
		hasher.update(b"\x00")
		hasher.update(r.canonical_json_bytes)
		hasher.update(b"\x00")
		hasher.update(r.row_sha256.encode("utf-8"))
		hasher.update(b"\x00")
	return hasher.hexdigest()


def _row_to_jsonable(row: GoldenRow) -> dict[str, Any]:
	# Datetimes are encoded by ``canonical_json`` already; for the JSON
	# payload we keep them as ISO strings so the file is human-diffable.
	def _iso(v: Any) -> Any:
		if isinstance(v, datetime):
			return v.isoformat()
		if isinstance(v, dict):
			return {k: _iso(x) for k, x in v.items()}
		if isinstance(v, list):
			return [_iso(x) for x in v]
		return v

	return {
		"event_id": row.event_id,
		"prev_sha256": row.prev_sha256,
		"input": _iso(row.input),
		"canonical_json_bytes_hex": row.canonical_json_bytes.hex(),
		"row_sha256": row.row_sha256,
	}


def _row_from_jsonable(d: dict[str, Any]) -> GoldenRow:
	def _parse(v: Any) -> Any:
		if isinstance(v, str) and len(v) >= 19 and v[4] == "-" and v[7] == "-" and "T" in v:
			try:
				return datetime.fromisoformat(v)
			except ValueError:
				return v
		if isinstance(v, dict):
			return {k: _parse(x) for k, x in v.items()}
		if isinstance(v, list):
			return [_parse(x) for x in v]
		return v

	return GoldenRow(
		event_id=d["event_id"],
		prev_sha256=d["prev_sha256"],
		input=_parse(d["input"]),
		canonical_json_bytes=bytes.fromhex(d["canonical_json_bytes_hex"]),
		row_sha256=d["row_sha256"],
	)


def write_golden(path: Path, bundle: GoldenBundle | None = None) -> Path:
	"""Serialise *bundle* (or a freshly built one) to *path*."""
	bundle = bundle or build_golden()
	payload = json.dumps(
		[_row_to_jsonable(r) for r in bundle.rows],
		sort_keys=True,
		separators=(",", ":"),
	).encode("utf-8")
	envelope = hashlib.sha256(payload).hexdigest().encode("ascii")
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("wb") as fh:
		fh.write(_MAGIC)
		fh.write(envelope)
		fh.write(b"\n")
		fh.write(payload)
	return path


def load_golden(path: Path) -> GoldenBundle:
	"""Load *path*; raise :class:`GoldenIntegrityError` on envelope mismatch."""
	raw = path.read_bytes()
	if not raw.startswith(_MAGIC):
		raise GoldenIntegrityError(
			f"{path}: missing magic header — not a flowforge audit golden bundle"
		)
	body = raw[len(_MAGIC):]
	# envelope_sha (64 hex chars) + b"\n" + payload
	if len(body) < 65 or body[64:65] != b"\n":
		raise GoldenIntegrityError(f"{path}: malformed envelope header")
	envelope = body[:64].decode("ascii")
	payload = body[65:]
	got = hashlib.sha256(payload).hexdigest()
	if got != envelope:
		raise GoldenIntegrityError(
			f"{path}: envelope sha256 mismatch (committed={envelope}, recomputed={got}) — refusing to load"
		)
	rows_data = json.loads(payload.decode("utf-8"))
	rows = [_row_from_jsonable(d) for d in rows_data]
	return GoldenBundle(rows=rows, envelope_sha=envelope)


def recompute_row(prev_sha: str | None, input_dict: dict[str, Any]) -> tuple[bytes, str]:
	"""Return ``(canonical_json_bytes, row_sha256)`` recomputed in-process.

	Tests use this to assert the on-disk bytes match what the current code
	produces. Drift means the canonical encoding changed, which is a
	SOX/HIPAA-relevant regression.
	"""
	canonical = canonical_json(input_dict).encode("utf-8")
	row_sha = compute_row_sha(prev_sha, input_dict)
	return canonical, row_sha


# ---------------------------------------------------------------------------
# CLI — `python -m flowforge_audit_pg._golden write <path>`
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="flowforge_audit_pg._golden")
	sub = parser.add_subparsers(dest="cmd", required=True)
	wp = sub.add_parser("write", help="write the canonical golden fixture")
	wp.add_argument("path", type=Path)
	vp = sub.add_parser("verify", help="verify a committed fixture")
	vp.add_argument("path", type=Path)
	ns = parser.parse_args(argv)
	if ns.cmd == "write":
		path = write_golden(ns.path)
		print(f"wrote {path}")
		return 0
	if ns.cmd == "verify":
		bundle = load_golden(ns.path)
		print(f"ok: {len(bundle.rows)} rows, envelope_sha={bundle.envelope_sha}")
		return 0
	return 1


if __name__ == "__main__":  # pragma: no cover
	sys.exit(_main(sys.argv[1:]))
