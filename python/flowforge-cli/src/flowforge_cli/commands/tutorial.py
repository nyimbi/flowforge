"""``flowforge tutorial`` — interactive 5-step walkthrough (E-28).

Gets a new author from zero to a validated, simulated JTBD-backed workflow
in under five minutes. Each step prints a clear instruction block, writes
the necessary files, and runs the appropriate ``flowforge`` subcommand so
the author sees real output.

Steps:

1. **Define** — write a ``claim_intake`` JTBD bundle to ``<out>/bundle.json``.
2. **Generate** — scaffold workflow definition + form spec from the bundle.
3. **Validate** — validate the generated workflow definition.
4. **Simulate** — simulate two events (submit → review → done).
5. **Lint** — run the JTBD linter and show authoring feedback.

Usage::

    # Full walkthrough (interactive, pauses between steps):
    flowforge tutorial

    # Specify output directory:
    flowforge tutorial --out my-demo

    # Non-interactive (CI / tests):
    flowforge tutorial --no-pause

    # Single step:
    flowforge tutorial --step 2

    # Preview without writing or running:
    flowforge tutorial --dry-run
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from .._ux import console, error, success


# ---------------------------------------------------------------------------
# Starter bundle
# ---------------------------------------------------------------------------


_STARTER_BUNDLE: dict = {
	"project": {
		"name": "insurance-demo",
		"package": "insurance_demo",
		"domain": "insurance",
		"tenancy": "single",
	},
	"shared": {
		"roles": ["policyholder", "adjuster", "supervisor"],
		"permissions": [
			"claim.read",
			"claim.submit",
			"claim.review",
			"claim.approve",
		],
	},
	"jtbds": [
		{
			"id": "claim_intake",
			"title": "File a claim",
			"actor": {"role": "policyholder", "external": True},
			"situation": "A policyholder has suffered an insurable loss and needs to open a First Notice of Loss (FNOL) claim.",
			"motivation": "Recover financial losses covered by the insurance policy.",
			"outcome": "Claim is accepted into triage with all required FNOL fields captured.",
			"success_criteria": [
				"Claim is queued for adjuster review within SLA (4 hours).",
				"All required PII fields are captured with consent flags.",
				"Policyholder receives an acknowledgement notification.",
			],
			"data_capture": [
				{"id": "claimant_name", "kind": "text", "label": "Full name", "pii": True},
				{"id": "policy_number", "kind": "text", "label": "Policy number", "pii": False},
				{"id": "loss_date", "kind": "date", "label": "Date of loss", "pii": False},
				{"id": "loss_amount", "kind": "money", "label": "Estimated loss amount", "pii": False},
				{"id": "incident_description", "kind": "textarea", "label": "Incident description", "pii": False},
			],
			"approvals": [
				{"role": "adjuster", "policy": "1_of_1"},
			],
			"sla": {"warn_pct": 75, "breach_seconds": 14400},
			"notifications": [
				{"trigger": "state_enter", "channel": "email", "audience": "policyholder"},
				{"trigger": "approved", "channel": "email", "audience": "policyholder"},
			],
			"metrics": ["fnol_submission_rate", "time_to_triage"],
		}
	],
}


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------


_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         flowforge interactive tutorial  (E-28)               ║
║  Five steps from zero to a validated, simulated workflow.    ║
╚══════════════════════════════════════════════════════════════╝
""".strip()

_STEPS = [
	{
		"n": 1,
		"title": "Define your JTBD bundle",
		"description": (
			"A JTBD bundle is the author-facing spec that describes the job "
			"to be done in plain language. We'll write a `claim_intake` JTBD "
			"for an insurance FNOL (First Notice of Loss) workflow."
		),
	},
	{
		"n": 2,
		"title": "Generate the workflow scaffold",
		"description": (
			"flowforge reads the bundle and generates a full workflow definition "
			"(state machine + form spec + audit taxonomy) in `generated/`."
		),
	},
	{
		"n": 3,
		"title": "Validate the workflow",
		"description": (
			"The validator checks reachability, transition priorities, guard "
			"syntax, and gate permissions against the generated definition."
		),
	},
	{
		"n": 4,
		"title": "Simulate two events",
		"description": (
			"The simulator runs two events through the workflow — `submit` "
			"(policyholder → review) and `approve` (adjuster → done) — and "
			"shows the state transitions + audit log."
		),
	},
	{
		"n": 5,
		"title": "Lint the JTBD bundle",
		"description": (
			"The JTBD linter checks lifecycle completeness, dependency order, "
			"actor consistency, and compliance coverage. The canonical generator "
			"schema does not yet carry lint lifecycle-stage declarations, so "
			"stage completeness may appear as authoring feedback."
		),
	},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_step_header(step: dict, total: int = 5) -> None:
	n = step["n"]
	title = step["title"]
	console.print(
		Panel(
			step["description"],
			title=f"Step {n}/{total}: {title}",
			border_style="cyan",
		)
	)


def _validated_cwd(cwd: Path) -> Path:
	"""Resolve *cwd* to an absolute, existing directory.

	audit-2026 CL-02: subprocess invocations previously accepted
	relative ``Path(".")`` which made the working directory implicit
	and brittle (e.g., differs between dev shell and uvicorn). The
	validated path is absolute and exists at call time.
	"""

	resolved = cwd.expanduser().resolve()
	if not resolved.is_absolute():
		raise ValueError(f"cwd must be absolute, got {cwd!r} (resolved={resolved!r})")
	if not resolved.exists() or not resolved.is_dir():
		raise FileNotFoundError(f"cwd does not exist or is not a directory: {resolved}")
	return resolved


def _run_cmd(args: list[str], *, cwd: Path, dry_run: bool) -> bool:
	"""Run a flowforge CLI command. Returns True on success.

	*cwd* is normalised through :func:`_validated_cwd` so a relative
	``Path(".")`` cannot reach :func:`subprocess.run` — every dispatch
	is bound to an absolute, existing directory.
	"""

	cmd_str = " ".join(args)
	typer.echo(f"  $ {cmd_str}")
	if dry_run:
		typer.echo("  (dry-run: skipped)")
		return True
	resolved_cwd = _validated_cwd(cwd)
	result = subprocess.run(args, cwd=resolved_cwd, capture_output=False)
	return result.returncode == 0


def _flowforge() -> str:
	"""Return the path to the current flowforge executable."""
	ff = shutil.which("flowforge")
	return ff if ff is not None else sys.argv[0]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
	app.command("tutorial", help="Interactive 5-step walkthrough from JTBD bundle to simulated workflow.")(tutorial_cmd)


def _load_domain_bundle(domain: str) -> dict:
	"""Load ``examples/bundle.yaml`` from ``flowforge-jtbd-<domain>`` package.

	Imports the domain package's ``load_bundle()`` helper (the E-51 / D-03
	standard), converts the result to the tutorial-compatible dict structure,
	and returns it.  Raises :exc:`typer.Exit` with a helpful message on any
	``ImportError`` or ``ModuleNotFoundError``.
	"""
	pkg_name = f"flowforge_jtbd_{domain.replace('-', '_')}"
	try:
		import importlib
		mod = importlib.import_module(pkg_name)
	except ImportError:  # catches ModuleNotFoundError + transitive ImportError
		error(
			"Domain tutorial package is not installed.",
			why=f"{pkg_name!r} could not be imported.",
			next_step=f"Install it with: uv pip install flowforge-jtbd-{domain}",
		)
		raise typer.Exit(1)

	if not hasattr(mod, "load_bundle"):
		error(
			"Domain tutorial package is missing load_bundle().",
			why=f"{pkg_name} does not follow the E-51 package contract.",
			next_step="Upgrade the domain package or use the built-in tutorial without --domain.",
		)
		raise typer.Exit(1)

	try:
		bundle: dict = mod.load_bundle()
	except Exception as exc:
		error(
			"Domain tutorial bundle failed to load.",
			why=f"{pkg_name}.load_bundle() raised {type(exc).__name__}: {exc}",
			next_step="Fix the domain package bundle loader and retry.",
		)
		raise typer.Exit(1) from exc
	return bundle


def tutorial_cmd(
	out: Annotated[
		Path,
		typer.Option("--out", help="Output directory for tutorial files."),
	] = Path("flowforge-demo"),
	step: Annotated[
		int | None,
		typer.Option("--step", help="Run only this step number (1-5)."),
	] = None,
	pause: Annotated[
		bool,
		typer.Option("--pause/--no-pause", help="Pause between steps for interactive mode."),
	] = True,
	dry_run: Annotated[
		bool,
		typer.Option("--dry-run", help="Show steps without writing files or running commands."),
	] = False,
	domain: Annotated[
		str | None,
		typer.Option(
			"--domain",
			help=(
				"Load the tutorial bundle from an installed flowforge-jtbd-<domain> package "
				"instead of the built-in insurance example. "
				"E.g. --domain insurance loads flowforge_jtbd_insurance.load_bundle()."
			),
		),
	] = None,
) -> None:
	"""Walk through the five tutorial steps end-to-end."""

	console.print(
		Panel(
			"flowforge interactive tutorial\nFive steps from zero to a validated, simulated workflow.",
			title="Tutorial",
			border_style="green",
		)
	)
	console.print(f"Output directory: {out.resolve()}")
	if dry_run:
		console.print("  (dry-run mode - no files will be written)")

	# Determine bundle data: domain override or built-in starter.
	if domain is not None:
		bundle_data = _load_domain_bundle(domain)
		typer.echo(f"  domain bundle: flowforge-jtbd-{domain}")
	else:
		bundle_data = _STARTER_BUNDLE

	selected_steps = _STEPS if step is None else [s for s in _STEPS if s["n"] == step]
	if not selected_steps:
		error(
			"Invalid tutorial step.",
			why=f"--step must be 1-5; got {step}.",
			next_step="Choose --step 1, 2, 3, 4, or 5.",
		)
		raise typer.Exit(1)

	bundle_path = out / "bundle.json"
	generated_dir = out / "generated"
	# Extract first JTBD once; reused for wf_path and step-1 display fields
	# (fix: was computed twice independently — double extraction could diverge).
	_first_jtbd = ((bundle_data.get("jtbds") or [{}])[0])
	_first_jtbd_id = _first_jtbd.get("id", "claim_intake")
	wf_path = generated_dir / "workflows" / _first_jtbd_id / "definition.json"

	errors: list[str] = []

	for s in selected_steps:
		_print_step_header(s)
		n = s["n"]

		# ── Step 1: Write bundle ──────────────────────────────────────────
		if n == 1:
			if not dry_run:
				out.mkdir(parents=True, exist_ok=True)
				bundle_path.write_text(
					json.dumps(bundle_data, indent=2),
					encoding="utf-8",
				)
			typer.echo(f"  ✓ Written: {bundle_path}")
			_actor = (_first_jtbd.get("actor") or {}).get("role", "?")
			_dc_count = len(_first_jtbd.get("data_capture") or [])
			_sla = _first_jtbd.get("sla") or {}
			table = Table(title="Bundle fields", show_header=True, header_style="bold")
			table.add_column("Field")
			table.add_column("Value")
			table.add_row("JTBD id", str(_first_jtbd_id))
			table.add_row("Actor", str(_actor))
			table.add_row("Data capture", f"{_dc_count} field(s)")
			table.add_row("SLA breach", f"{_sla.get('breach_seconds', '?')}s")
			console.print(table)

		# ── Step 2: Generate ─────────────────────────────────────────────
		elif n == 2:
			ok = _run_cmd(
				["flowforge", "jtbd-generate", "--jtbd", str(bundle_path), "--out", str(generated_dir)],
				cwd=(out.parent if out.parent.exists() else Path.cwd()).resolve(),
				dry_run=dry_run,
			)
			if not ok:
				errors.append("jtbd-generate failed")
			typer.echo(f"  ✓ Generated into: {generated_dir}/")

		# ── Step 3: Validate ─────────────────────────────────────────────
		elif n == 3:
			if wf_path.exists() or dry_run:
				ok = _run_cmd(
					["flowforge", "validate", "--def", str(wf_path)],
					cwd=Path.cwd(),
					dry_run=dry_run,
				)
				if not ok:
					errors.append("validate failed")
			else:
				typer.echo(f"  ! Skipping validate — run step 2 first (missing {wf_path})")

		# ── Step 4: Simulate ─────────────────────────────────────────────
		elif n == 4:
			if wf_path.exists() or dry_run:
				# Derive event names from the generated workflow definition so the
				# tutorial works for any domain (fix: was hardcoded to "submit"/"approve"
				# which are only correct for the built-in insurance starter).
				_sim_events = ["submit", "approve"]
				if wf_path.exists():
					try:
						_wf_raw = json.loads(wf_path.read_text(encoding="utf-8"))
						_evs = [
							t.get("event") for t in _wf_raw.get("transitions", [])
							if t.get("event")
						]
						# Preserve order, deduplicate, cap at 2 for the tutorial.
						_unique_evs = list(dict.fromkeys(_evs))
						if _unique_evs:
							_sim_events = _unique_evs[:2]
					except Exception as _exc:
						import logging as _logging
						_logging.getLogger(__name__).warning(
							"tutorial: could not derive event names from %s (%s); "
							"falling back to defaults %s",
							wf_path,
							_exc,
							_sim_events,
						)
				_sim_args = [item for ev in _sim_events for item in ("--events", ev)]
				ok = _run_cmd(
					["flowforge", "simulate", "--def", str(wf_path)] + _sim_args,
					cwd=Path.cwd(),
					dry_run=dry_run,
				)
				if not ok:
					errors.append("simulate failed")
			else:
				typer.echo(f"  ! Skipping simulate — run step 2 first (missing {wf_path})")

		# ── Step 5: Lint ─────────────────────────────────────────────────
		elif n == 5:  # pragma: no branch - selected steps are prevalidated to 1-5.
			if bundle_path.exists() or dry_run:
				ok = _run_cmd(
					["flowforge", "jtbd", "lint", "--bundle", str(bundle_path), "--warn-only"],
					cwd=Path.cwd(),
					dry_run=dry_run,
				)
				if not ok:
					errors.append("jtbd lint returned non-zero")
			else:
				typer.echo(f"  ! Skipping lint — run step 1 first (missing {bundle_path})")

		# Pause between steps
		if pause and not dry_run and s["n"] < selected_steps[-1]["n"]:
			console.print("")
			console.print("[bold]Press Enter to continue to the next step...[/]", markup=True, end="")
			input("")

	# Summary
	if errors:
		console.print(
			Panel(
				f"Tutorial completed with {len(errors)} error(s):",
				title="Tutorial Summary",
				border_style="red",
			)
		)
		for err in errors:
			typer.echo(f"    x {err}")
		raise typer.Exit(1)
	else:
		success("Tutorial complete!")
		typer.echo(f"  Your demo project lives in: {out.resolve()}/")
		typer.echo("")
		typer.echo("  Next steps:")
		typer.echo(f"    flowforge jtbd lint --bundle {bundle_path}")
		typer.echo(f"    flowforge jtbd migrate --bundle {bundle_path} --from claim_intake")
		typer.echo("    Read the docs: docs/flowforge-handbook.md")
