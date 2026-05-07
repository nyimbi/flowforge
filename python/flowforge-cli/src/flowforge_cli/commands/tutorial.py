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
5. **Lint** — run the JTBD linter to show zero semantic issues.

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
			"actor consistency, and compliance coverage."
		),
	},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_step_header(step: dict, total: int = 5) -> None:
	n = step["n"]
	title = step["title"]
	typer.echo(f"\n─── Step {n}/{total}: {title} ───")
	typer.echo(f"  {step['description']}")
	typer.echo("")


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
	return sys.executable.replace("python", "flowforge") if shutil.which("flowforge") else sys.argv[0]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
	app.command("tutorial", help="Interactive 5-step walkthrough from JTBD bundle to simulated workflow.")(tutorial_cmd)


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
) -> None:
	"""Walk through the five tutorial steps end-to-end."""

	typer.echo(_BANNER)
	typer.echo(f"\nOutput directory: {out.resolve()}")
	if dry_run:
		typer.echo("  (dry-run mode — no files will be written)")

	selected_steps = _STEPS if step is None else [s for s in _STEPS if s["n"] == step]
	if not selected_steps:
		typer.echo(f"error: --step must be 1-5; got {step}", err=True)
		raise typer.Exit(1)

	bundle_path = out / "bundle.json"
	generated_dir = out / "generated"
	wf_path = generated_dir / "claim_intake" / "definition.json"

	errors: list[str] = []

	for s in selected_steps:
		_print_step_header(s)
		n = s["n"]

		# ── Step 1: Write bundle ──────────────────────────────────────────
		if n == 1:
			if not dry_run:
				out.mkdir(parents=True, exist_ok=True)
				bundle_path.write_text(
					json.dumps(_STARTER_BUNDLE, indent=2),
					encoding="utf-8",
				)
			typer.echo(f"  ✓ Written: {bundle_path}")
			typer.echo("  Bundle fields:")
			typer.echo("    - JTBD id       : claim_intake")
			typer.echo("    - Actor         : policyholder (external)")
			typer.echo("    - Data capture  : 5 fields (name, policy#, date, amount, desc)")
			typer.echo("    - Approvals     : adjuster (1_of_1)")
			typer.echo("    - SLA           : 4h breach, 75% warn")

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
					["flowforge", "validate", str(wf_path)],
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
				ok = _run_cmd(
					[
						"flowforge", "simulate", str(wf_path),
						"--events", "submit:{}",
						"--events", "approve:{}",
					],
					cwd=Path.cwd(),
					dry_run=dry_run,
				)
				if not ok:
					errors.append("simulate failed")
			else:
				typer.echo(f"  ! Skipping simulate — run step 2 first (missing {wf_path})")

		# ── Step 5: Lint ─────────────────────────────────────────────────
		elif n == 5:
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
			typer.echo("")
			input("  Press Enter to continue to the next step…")

	# Summary
	typer.echo("\n" + "─" * 60)
	if errors:
		typer.echo(f"  Tutorial completed with {len(errors)} error(s):")
		for err in errors:
			typer.echo(f"    ✗ {err}")
		raise typer.Exit(1)
	else:
		typer.echo("  ✓ Tutorial complete!")
		typer.echo(f"  Your demo project lives in: {out.resolve()}/")
		typer.echo("")
		typer.echo("  Next steps:")
		typer.echo("    flowforge jtbd lint --bundle flowforge-demo/bundle.json")
		typer.echo("    flowforge jtbd migrate --bundle flowforge-demo/bundle.json --from claim_intake")
		typer.echo("    Read the docs: framework/docs/flowforge-handbook.md")
