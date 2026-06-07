"""``flowforge jtbd lock`` — generate or verify a JTBD bundle lockfile (E-1).

Wraps :class:`flowforge_jtbd.dsl.lockfile.JtbdLockfile` to produce
a ``bundle.lock.json`` artefact that pins every JTBD spec in a bundle
to its exact ``(version, spec_hash)`` triple, making regen determinism
verifiable in CI.

Usage examples::

    # Generate bundle.lock.json next to the bundle:
    flowforge jtbd lock --init path/to/jtbd-bundle.json

    # Verify an existing lockfile matches the current bundle:
    flowforge jtbd lock --verify path/to/jtbd-bundle.json

Exit codes: 0=ok, 1=error/mismatch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .._io import load_structured, write_json
from flowforge_jtbd.dsl.lockfile import JtbdLockfile, JtbdLockfilePin
from flowforge_jtbd.dsl.canonical import spec_hash as _spec_hash


def register(app: typer.Typer) -> None:
	app.command(
		"lock",
		help="Generate (--init) or verify (--verify) a JTBD bundle lockfile.",
	)(jtbd_lock_cmd)


# ---------------------------------------------------------------------------
# Lockfile helpers
# ---------------------------------------------------------------------------


def _bundle_id(raw: dict[str, Any]) -> str:
	return (raw.get("project") or {}).get("name") or "unknown"


def _bundle_package(raw: dict[str, Any]) -> str:
	pkg = (raw.get("project") or {}).get("package") or ""
	return pkg or _bundle_id(raw)


def _make_pins(raw: dict[str, Any]) -> list[JtbdLockfilePin]:
	"""Derive one pin per JTBD in the bundle."""
	pins: list[JtbdLockfilePin] = []
	for jtbd in raw.get("jtbds", []) or []:
		jtbd_id: str = jtbd.get("id") or jtbd.get("jtbd_id") or "unknown"
		version: str = jtbd.get("version") or "1.0.0"
		# Canonical hash of the individual JTBD dict.
		h = _spec_hash(jtbd)
		pins.append(JtbdLockfilePin(jtbd_id=jtbd_id, version=version, spec_hash=h))
	return pins


def build_lockfile(bundle_path: Path, raw: dict[str, Any]) -> JtbdLockfile:
	"""Build a :class:`JtbdLockfile` from *raw* bundle data."""
	bid = _bundle_id(raw)
	pkg = _bundle_package(raw)
	pins = _make_pins(raw)
	lf = JtbdLockfile(
		composition_id=bid,
		project_package=pkg,
		pins=pins,
		generated_by="flowforge jtbd lock",
	)
	return lf.with_body_hash()


def lockfile_path(bundle_path: Path) -> Path:
	"""Return the canonical lockfile path adjacent to *bundle_path*."""
	return bundle_path.parent / "bundle.lock.json"


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def jtbd_lock_cmd(
	bundle_path: Annotated[
		Path,
		typer.Argument(help="Path to the JTBD bundle JSON file."),
	],
	init: Annotated[
		bool,
		typer.Option("--init/--no-init", help="Generate bundle.lock.json next to the bundle."),
	] = False,
	verify: Annotated[
		bool,
		typer.Option("--verify/--no-verify", help="Verify existing lockfile matches current bundle."),
	] = False,
	out: Annotated[
		Path | None,
		typer.Option("--out", help="Custom output path for the lockfile (--init only)."),
	] = None,
) -> None:
	"""Generate or verify a JTBD bundle lockfile.

	Pass --init to create bundle.lock.json; pass --verify to check that an
	existing lockfile still matches the current bundle contents.
	"""
	if not init and not verify:
		typer.echo("error: pass --init to generate or --verify to check the lockfile.", err=True)
		raise typer.Exit(1)

	if not bundle_path.exists():
		typer.echo(f"error: bundle not found: {bundle_path}", err=True)
		raise typer.Exit(1)

	raw = load_structured(bundle_path)
	lf = build_lockfile(bundle_path, raw)

	if init:
		dst = out or lockfile_path(bundle_path)
		write_json(dst, lf.model_dump(mode="json"))
		typer.echo(f"lock: wrote {dst}")
		typer.echo(f"  composition_id : {lf.composition_id}")
		typer.echo(f"  project_package: {lf.project_package}")
		typer.echo(f"  pins           : {len(lf.pins)}")
		typer.echo(f"  body_hash      : {lf.body_hash}")
		# When only --init was requested, stop here.  When both --init and --verify
		# are passed, fall through so the freshly-written lockfile is validated
		# in the same invocation (fix: early return silently skipped verification).
		if not verify:
			return

	# --verify
	lf_path = out or lockfile_path(bundle_path)
	if not lf_path.exists():
		typer.echo(f"error: lockfile not found: {lf_path} — run --init first.", err=True)
		raise typer.Exit(1)

	existing_data = json.loads(lf_path.read_text(encoding="utf-8"))
	try:
		existing = JtbdLockfile.model_validate(existing_data)
	except Exception as exc:
		typer.echo(f"error: lockfile parse failed: {exc}", err=True)
		raise typer.Exit(1) from exc

	# Recompute body_hash of the on-disk lockfile body to confirm it wasn't tampered.
	on_disk_hash = existing.compute_body_hash()
	if existing.body_hash and existing.body_hash != on_disk_hash:
		typer.echo(
			f"error: lockfile body_hash mismatch — stored={existing.body_hash} "
			f"computed={on_disk_hash}",
			err=True,
		)
		raise typer.Exit(1)

	# Now compare pin set against the freshly-derived lockfile.
	fresh_pins = {p.jtbd_id: p for p in lf.pins}
	stored_pins = {p.jtbd_id: p for p in existing.pins}

	mismatches: list[str] = []
	for jtbd_id, fresh_pin in fresh_pins.items():
		stored = stored_pins.get(jtbd_id)
		if stored is None:
			mismatches.append(f"  new in bundle, missing from lock: {jtbd_id}")
		elif stored.spec_hash != fresh_pin.spec_hash:
			mismatches.append(
				f"  hash mismatch for {jtbd_id}: "
				f"lock={stored.spec_hash} bundle={fresh_pin.spec_hash}"
			)
	for jtbd_id in stored_pins:
		if jtbd_id not in fresh_pins:
			mismatches.append(f"  in lock but removed from bundle: {jtbd_id}")

	if mismatches:
		typer.echo("error: lockfile verification failed:", err=True)
		for m in mismatches:
			typer.echo(m, err=True)
		raise typer.Exit(1)

	typer.echo(f"ok: lockfile verified ({len(lf.pins)} pins, body_hash={lf.body_hash})")
