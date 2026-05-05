"""``flowforge audit verify`` — verify hash chain over a time range.

Skeleton stub. Mounted under the ``audit`` subgroup.
"""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
	app.command("verify", help="Verify audit hash chain for a time range (skeleton).")(audit_verify_cmd)


def audit_verify_cmd(
	range_: str = typer.Option(..., "--range", help="Range expressed as <ts1>..<ts2>."),
) -> None:
	raise NotImplementedError(f"flowforge audit verify --range {range_} is not yet implemented.")
