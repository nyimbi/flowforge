"""``flowforge add-jtbd`` — append/refresh one JTBD inside an existing project.

Idempotent: re-running with the same bundle is a no-op (sorted JSON, stable
keys). Mirrors the §10.1 contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from .._io import load_structured, write_json
from .new import _stub_workflow_for_jtbd, _validate_bundle


def register(app: typer.Typer) -> None:
	app.command("add-jtbd", help="Add or refresh one JTBD inside an existing project (idempotent).")(add_jtbd_cmd)


def add_jtbd_cmd(
	jtbd: Path = typer.Argument(..., exists=True, dir_okay=False, help="JTBD bundle file (single or multi)."),
	project: Path = typer.Option(Path.cwd(), "--project", help="Project root (default: cwd)."),
) -> None:
	"""Merge *jtbd* into ``<project>/workflows/jtbd_bundle.json`` and emit DSL stubs."""

	assert jtbd is not None
	incoming = load_structured(jtbd)
	_validate_bundle(incoming)

	bundle_path = project / "workflows" / "jtbd_bundle.json"
	if bundle_path.exists():
		current = load_structured(bundle_path)
	else:
		current = {
			"project": incoming["project"],
			"shared": incoming.get("shared", {}),
			"jtbds": [],
		}

	by_id: dict[str, dict[str, Any]] = {j["id"]: j for j in current.get("jtbds", [])}
	added: list[str] = []
	updated: list[str] = []
	for jt in incoming.get("jtbds", []):
		jt_id = jt["id"]
		if jt_id in by_id:
			if by_id[jt_id] != jt:
				updated.append(jt_id)
			by_id[jt_id] = jt
		else:
			added.append(jt_id)
			by_id[jt_id] = jt

	current["jtbds"] = [by_id[k] for k in sorted(by_id)]
	# Merge shared roles/permissions/entities deterministically.
	current["shared"] = _merge_shared(current.get("shared", {}), incoming.get("shared", {}))
	write_json(bundle_path, current)

	subject_kind = current["project"].get("domain", "subject")
	wf_files: list[str] = []
	for jt_id in sorted(set(added) | set(updated)):
		wf = _stub_workflow_for_jtbd(by_id[jt_id], subject_kind)
		rel = Path("workflows") / jt_id / "definition.json"
		write_json(project / rel, wf)
		wf_files.append(str(rel))

	typer.echo(f"merged jtbd_bundle.json: +{len(added)} added, ~{len(updated)} updated, "
				f"={len(by_id) - len(added) - len(updated)} unchanged")
	for rel in wf_files:
		typer.echo(f"      created/refreshed  {rel}")


def _merge_shared(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
	out: dict[str, Any] = {}
	for key in ("roles", "permissions"):
		merged = sorted(set(a.get(key, []) or []) | set(b.get(key, []) or []))
		if merged:
			out[key] = merged
	# entities: dedupe by name when present.
	entities: dict[str, Any] = {}
	for src in (a.get("entities", []) or [], b.get("entities", []) or []):
		for ent in src:
			name = ent.get("name") or ent.get("id") or repr(sorted(ent.items()))
			entities[name] = ent
	if entities:
		out["entities"] = [entities[k] for k in sorted(entities)]
	return out
