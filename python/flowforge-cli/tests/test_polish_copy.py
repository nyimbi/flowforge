"""Tests for v0.3.0 W4b / item 22: copy-override sidecar (ADR-002).

Covers:

* :class:`JtbdCopyOverrides` schema — ``extra='forbid'`` at the top level,
  namespace-pattern validation for ``strings`` keys.
* Sidecar lookup precedence (``--overrides`` flag wins, then co-located,
  then ``None``).
* :mod:`flowforge_cli.commands.polish_copy` no-op behaviour when no
  API key is set (the CI default).
* ``flowforge jtbd-generate`` picks up the co-located sidecar and applies
  field-label overrides at form_spec / Step.tsx emission time.
* Determinism: two regen passes with the same sidecar produce
  byte-identical output.
* ``spec_hash`` invariance: same canonical bundle, different sidecars →
  identical canonical bundle (sidecar is *not* part of the bundle).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.overrides import (
	JtbdCopyOverrides,
	OVERRIDE_KEY_KINDS,
	TONE_PROFILES,
	build_canonical_strings,
	dump_sidecar,
	load_sidecar,
	resolve_sidecar,
	sidecar_path_for,
	validate_key_against_bundle,
)
from flowforge_cli.main import app


runner = CliRunner()


def _bundle() -> dict[str, Any]:
	"""Minimal valid bundle the generator can chew."""

	return {
		"project": {
			"name": "polish-demo",
			"package": "polish_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {
			"roles": ["adjuster"],
			"permissions": ["claim.read"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Loss",
						"required": True,
						"pii": False,
					},
				],
			}
		],
	}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_accepts_valid_namespace_keys() -> None:
	"""Each documented key kind validates cleanly."""

	model = JtbdCopyOverrides(
		tone_profile="formal-professional",
		strings={
			"claim_intake.field.claimant_name.label": "Claimant full name",
			"claim_intake.field.claimant_name.helper_text": "As shown on policy.",
			"claim_intake.button.submit.text": "File claim",
			"claim_intake.notification.claim.created.template": "Hello {{ name }}.",
			"claim_intake.error.lapsed.message": "Policy lapsed.",
		},
	)
	assert model.tone_profile == "formal-professional"
	assert model.version == "1.0"
	# Round-trip through dump → parse → equality.
	rendered = dump_sidecar(model)
	parsed = JtbdCopyOverrides.model_validate_json(rendered)
	assert parsed.strings == model.strings


def test_schema_rejects_unknown_namespace() -> None:
	"""A key outside the documented namespace fails validation."""

	with pytest.raises(ValidationError) as exc:
		JtbdCopyOverrides(
			tone_profile="formal-professional",
			strings={"claim_intake.label": "Nope"},
		)
	assert "override keys must match" in str(exc.value)


def test_schema_rejects_typo_suffix() -> None:
	"""``labels`` (plural) and ``msg`` typos fail — leaf suffix is locked down."""

	for bad in (
		"claim_intake.field.claimant_name.labels",  # plural
		"claim_intake.button.submit.label",  # wrong leaf for button
		"claim_intake.notification.x.body",  # wrong leaf for notification
	):
		with pytest.raises(ValidationError):
			JtbdCopyOverrides(
				tone_profile="friendly-direct",
				strings={bad: "value"},
			)


def test_schema_forbids_extra_top_level() -> None:
	"""``extra='forbid'`` keeps the top-level surface locked."""

	with pytest.raises(ValidationError):
		JtbdCopyOverrides.model_validate(
			{
				"tone_profile": "regulator-compliant",
				"strings": {},
				"extra_key": "not allowed",
			}
		)


def test_schema_locks_tone_profile() -> None:
	"""Tone profile is a closed Literal — typo fails."""

	with pytest.raises(ValidationError):
		JtbdCopyOverrides(
			tone_profile="casual",  # type: ignore[arg-type]
			strings={},
		)


def test_kinds_constants_align() -> None:
	"""``OVERRIDE_KEY_KINDS`` matches the four documented namespaces."""

	assert set(OVERRIDE_KEY_KINDS) == {"field", "button", "notification", "error"}
	assert "formal-professional" in TONE_PROFILES
	assert "friendly-direct" in TONE_PROFILES
	assert "regulator-compliant" in TONE_PROFILES


# ---------------------------------------------------------------------------
# Sidecar path math + lookup precedence
# ---------------------------------------------------------------------------


def test_sidecar_path_appends_overrides_json(tmp_path: Path) -> None:
	"""Two neighbouring bundles never collide because the sidecar carries
	the full bundle filename (not just the stem)."""

	b1 = tmp_path / "claims.json"
	b2 = tmp_path / "claims-v2.json"
	s1 = sidecar_path_for(b1)
	s2 = sidecar_path_for(b2)
	assert s1.name == "claims.json.overrides.json"
	assert s2.name == "claims-v2.json.overrides.json"
	assert s1 != s2


def test_resolve_sidecar_explicit_wins(tmp_path: Path) -> None:
	"""Explicit ``--overrides <path>`` flag overrides the co-located file."""

	bundle = tmp_path / "b.json"
	bundle.write_text("{}", encoding="utf-8")

	colo = sidecar_path_for(bundle)
	colo.write_text(
		dump_sidecar(
			JtbdCopyOverrides(
				tone_profile="formal-professional",
				strings={"x.field.a.label": "colocated"},
			)
		),
		encoding="utf-8",
	)

	other = tmp_path / "explicit.overrides.json"
	other.write_text(
		dump_sidecar(
			JtbdCopyOverrides(
				tone_profile="friendly-direct",
				strings={"x.field.a.label": "explicit"},
			)
		),
		encoding="utf-8",
	)

	# co-located alone
	hit = resolve_sidecar(bundle)
	assert hit is not None and hit.strings["x.field.a.label"] == "colocated"

	# explicit beats co-located
	hit2 = resolve_sidecar(bundle, other)
	assert hit2 is not None and hit2.strings["x.field.a.label"] == "explicit"


def test_load_sidecar_none_when_missing(tmp_path: Path) -> None:
	"""No sidecar on disk → ``None``; canonical fall-through path."""

	bundle = tmp_path / "lonely.json"
	bundle.write_text("{}", encoding="utf-8")
	assert load_sidecar(bundle) is None


def test_validate_key_against_bundle_catches_typos() -> None:
	"""A hand-edited sidecar key that targets a non-existent field is rejected."""

	bundle = _bundle()
	# Valid — claimant_name is a real field.
	assert (
		validate_key_against_bundle(
			"claim_intake.field.claimant_name.label", bundle
		)
		is None
	)
	# Typo on field id.
	err = validate_key_against_bundle(
		"claim_intake.field.claimentnme.label", bundle
	)
	assert err is not None and "no data_capture field" in err
	# Wrong JTBD id.
	err = validate_key_against_bundle(
		"unknown_jtbd.field.claimant_name.label", bundle
	)
	assert err is not None and "no JTBD" in err


def test_build_canonical_strings_emits_every_label() -> None:
	"""Canonical map carries every field label — the LLM's polish target."""

	canonical = build_canonical_strings(_bundle())
	assert canonical["claim_intake.field.claimant_name.label"] == "Claimant"
	assert canonical["claim_intake.field.loss_amount.label"] == "Loss"


# ---------------------------------------------------------------------------
# Generator integration — overrides apply at normalize → form_spec / Step.tsx
# ---------------------------------------------------------------------------


def _form_spec_for(files: list[Any], jtbd_id: str) -> dict[str, Any]:
	(spec,) = [f for f in files if f.path == f"workflows/{jtbd_id}/form_spec.json"]
	return json.loads(spec.content)


def _step_tsx_for(files: list[Any], class_name: str) -> str:
	(step,) = [
		f for f in files if f.path.endswith(f"{class_name}Step.tsx")
	]
	return step.content


def test_generate_without_overrides_uses_canonical_labels() -> None:
	"""No sidecar → canonical labels in form_spec.json (and Step.tsx)."""

	files = generate(_bundle())
	spec = _form_spec_for(files, "claim_intake")
	fields = {f["id"]: f for f in spec["fields"]}
	assert fields["claimant_name"]["label"] == "Claimant"
	assert fields["loss_amount"]["label"] == "Loss"


def test_generate_applies_override_labels() -> None:
	"""Sidecar replaces field labels in form_spec.json and the Step.tsx FIELDS array."""

	overrides = JtbdCopyOverrides(
		tone_profile="formal-professional",
		strings={
			"claim_intake.field.claimant_name.label": "Claimant full name",
			"claim_intake.field.loss_amount.label": "Estimated loss",
		},
	)
	files = generate(_bundle(), overrides=overrides)
	spec = _form_spec_for(files, "claim_intake")
	fields = {f["id"]: f for f in spec["fields"]}
	assert fields["claimant_name"]["label"] == "Claimant full name"
	assert fields["loss_amount"]["label"] == "Estimated loss"

	# Step.tsx FIELDS array picks up the same label.
	step = _step_tsx_for(files, "ClaimIntake")
	assert 'label: "Claimant full name"' in step
	assert 'label: "Estimated loss"' in step


def test_generate_with_overrides_is_deterministic() -> None:
	"""Two runs with the same overrides produce byte-identical output."""

	overrides = JtbdCopyOverrides(
		tone_profile="regulator-compliant",
		strings={
			"claim_intake.field.claimant_name.label": "Claimant (full legal name)",
		},
	)
	a = [(f.path, f.content) for f in generate(_bundle(), overrides=overrides)]
	b = [(f.path, f.content) for f in generate(_bundle(), overrides=overrides)]
	assert a == b


def test_overrides_dont_pollute_canonical_bundle() -> None:
	"""ADR-002 invariant — sidecar never mutates the canonical bundle."""

	raw = _bundle()
	import copy

	snapshot = copy.deepcopy(raw)
	overrides = JtbdCopyOverrides(
		tone_profile="friendly-direct",
		strings={
			"claim_intake.field.claimant_name.label": "Mutated",
		},
	)
	generate(raw, overrides=overrides)
	assert raw == snapshot


def test_overrides_partial_passes_through_missing_keys() -> None:
	"""Overrides for one field; others fall back to canonical."""

	overrides = JtbdCopyOverrides(
		tone_profile="friendly-direct",
		strings={
			"claim_intake.field.claimant_name.label": "Your name",
		},
	)
	files = generate(_bundle(), overrides=overrides)
	spec = _form_spec_for(files, "claim_intake")
	fields = {f["id"]: f for f in spec["fields"]}
	assert fields["claimant_name"]["label"] == "Your name"
	# loss_amount has no override → canonical label survives.
	assert fields["loss_amount"]["label"] == "Loss"


# ---------------------------------------------------------------------------
# CLI — polish-copy command (no API key path is the CI default)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
	"""All polish-copy tests run under the no-API-key contract."""

	monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
	monkeypatch.delenv("CLAUDE_API_KEY", raising=False)


def _write_bundle(tmp_path: Path, bundle: dict[str, Any] | None = None) -> Path:
	path = tmp_path / "jtbd-bundle.json"
	path.write_text(json.dumps(bundle if bundle is not None else _bundle()), encoding="utf-8")
	return path


def test_cli_dry_run_no_api_key_reports_empty_diff(tmp_path: Path) -> None:
	"""--dry-run with no API key returns canonical → empty diff."""

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	assert "no-op echo" in result.output
	assert "no diff" in result.output
	# No sidecar should be created in dry-run mode.
	assert not sidecar_path_for(path).exists()


def test_cli_commit_no_api_key_does_not_write_sidecar(tmp_path: Path) -> None:
	"""--commit with no API key is a no-op (canonical = polished) → no file written.

	Keeps the CI ``git status --porcelain`` gate clean when polish-copy
	is invoked without an LLM available.
	"""

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--commit",
		],
	)
	assert result.exit_code == 0, result.output
	assert "no-op" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_rejects_invalid_tone(tmp_path: Path) -> None:
	"""Tone profile is closed; typos fail loudly."""

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"casual-bro",
		],
	)
	assert result.exit_code != 0


def test_cli_dry_run_with_existing_sidecar_shows_proposed_diff(
	tmp_path: Path,
) -> None:
	"""When a sidecar exists, --dry-run diffs canonical-polish vs that sidecar."""

	path = _write_bundle(tmp_path)
	# Seed an existing sidecar that polishes claimant_name.
	sidecar = sidecar_path_for(path)
	sidecar.write_text(
		dump_sidecar(
			JtbdCopyOverrides(
				tone_profile="formal-professional",
				strings={
					"claim_intake.field.claimant_name.label": "Claimant (full legal name)",
				},
			)
		),
		encoding="utf-8",
	)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	# No API key → polish_fn returns canonical. Canonical differs from
	# the existing sidecar (sidecar = "Claimant (full legal name)";
	# canonical = "Claimant") → diff shows the revert.
	assert "claim_intake.field.claimant_name.label" in result.output


def test_cli_overrides_flag_threads_into_generate(tmp_path: Path) -> None:
	"""jtbd-generate --overrides <path> picks up an explicit sidecar."""

	path = _write_bundle(tmp_path)
	# Write a sidecar at a path different from the co-located one.
	override_path = tmp_path / "tone.overrides.json"
	override_path.write_text(
		dump_sidecar(
			JtbdCopyOverrides(
				tone_profile="formal-professional",
				strings={
					"claim_intake.field.claimant_name.label": "Claimant full name",
				},
			)
		),
		encoding="utf-8",
	)

	out_dir = tmp_path / "out"
	result = runner.invoke(
		app,
		[
			"jtbd-generate",
			"--jtbd",
			str(path),
			"--out",
			str(out_dir),
			"--overrides",
			str(override_path),
			"--force",
		],
	)
	assert result.exit_code == 0, result.output

	spec_path = out_dir / "workflows" / "claim_intake" / "form_spec.json"
	assert spec_path.exists()
	spec = json.loads(spec_path.read_text(encoding="utf-8"))
	fields = {f["id"]: f for f in spec["fields"]}
	assert fields["claimant_name"]["label"] == "Claimant full name"


def test_cli_jtbd_generate_picks_colocated_sidecar(tmp_path: Path) -> None:
	"""No --overrides flag → co-located sidecar is auto-applied."""

	path = _write_bundle(tmp_path)
	sidecar = sidecar_path_for(path)
	sidecar.write_text(
		dump_sidecar(
			JtbdCopyOverrides(
				tone_profile="formal-professional",
				strings={
					"claim_intake.field.loss_amount.label": "Estimated loss",
				},
			)
		),
		encoding="utf-8",
	)

	out_dir = tmp_path / "out"
	result = runner.invoke(
		app,
		[
			"jtbd-generate",
			"--jtbd",
			str(path),
			"--out",
			str(out_dir),
			"--force",
		],
	)
	assert result.exit_code == 0, result.output

	spec_path = out_dir / "workflows" / "claim_intake" / "form_spec.json"
	spec = json.loads(spec_path.read_text(encoding="utf-8"))
	fields = {f["id"]: f for f in spec["fields"]}
	assert fields["loss_amount"]["label"] == "Estimated loss"


def test_cli_smoke_against_real_example_bundle() -> None:
	"""Smoke: dry-run on examples/insurance_claim/ produces an empty diff.

	The example carries no sidecar today, no API key in CI → canonical
	round-trip should be byte-clean.
	"""

	repo_root = Path(__file__).resolve().parents[3]
	bundle = repo_root / "examples" / "insurance_claim" / "jtbd-bundle.json"
	assert bundle.exists(), f"missing example bundle at {bundle}"

	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(bundle),
			"--tone",
			"formal-professional",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	assert "no diff" in result.output, result.output
