"""``flowforge audit verify`` — verify audit hash-chain export files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer


def register(app: typer.Typer) -> None:
	app.command("verify", help="Verify an exported audit hash chain.")(audit_verify_cmd)


def audit_verify_cmd(
	file: Path | None = typer.Option(
		None,
		"--file",
		"-f",
		exists=True,
		dir_okay=False,
		help="JSONL export of audit rows to verify.",
	),
	range_: str | None = typer.Option(None, "--range", help="Informational range label for the export."),
) -> None:
	"""Verify a hash-chain export produced by a host audit store."""

	if file is None:
		typer.echo("error: audit verify requires --file <audit-export.jsonl>", err=True)
		raise typer.Exit(2)
	try:
		rows = _load_rows(file)
		from flowforge.ports.audit import Verdict
		from flowforge_audit_pg.hash_chain import verify_chain_in_memory

		ok, bad_id = verify_chain_in_memory(rows)
	except Exception as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(2) from exc
	verdict = Verdict.supported_ok(len(rows)) if ok else Verdict.supported_bad(str(bad_id), len(rows))
	if verdict.ok:
		label = f" ({range_})" if range_ else ""
		typer.echo(f"audit chain ok{label}: checked {verdict.checked_count} rows")
		return
	typer.echo(
		f"audit chain broken: first bad event {verdict.first_bad_event_id}; checked {verdict.checked_count} rows",
		err=True,
	)
	raise typer.Exit(1)


def _load_rows(path: Path) -> list[Any]:
	rows: list[Any] = []
	for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
		if not line.strip():
			continue
		raw = json.loads(line)
		if not isinstance(raw, dict):
			raise ValueError(f"{path}:{line_no}: expected object")
		rows.append(_row(raw, line_no))
	return rows


def _row(raw: dict[str, Any], line_no: int) -> Any:
	try:
		from flowforge_audit_pg.hash_chain import AuditRow

		occurred = raw.get("occurred_at") or raw.get("created_at") or "1970-01-01T00:00:00"
		if isinstance(occurred, str):
			occurred_at = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
		elif isinstance(occurred, datetime):
			occurred_at = occurred
		else:
			raise TypeError("occurred_at must be a string")
		payload = raw.get("payload") or {}
		if not isinstance(payload, dict):
			raise TypeError("payload must be an object")
		return AuditRow(
			event_id=str(raw["event_id"]),
			tenant_id=raw.get("tenant_id"),
			actor_user_id=raw.get("actor_user_id"),
			kind=str(raw["kind"]),
			subject_kind=str(raw["subject_kind"]),
			subject_id=str(raw["subject_id"]),
			occurred_at=occurred_at,
			payload=payload,
			prev_sha256=raw.get("prev_sha256"),
			row_sha256=raw.get("row_sha256"),
		)
	except KeyError as exc:
		raise ValueError(f"line {line_no}: missing required field {exc.args[0]!r}") from exc
