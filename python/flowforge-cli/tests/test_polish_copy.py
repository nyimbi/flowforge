"""Tests for v0.3.0 W4b / item 22: copy-override sidecar (ADR-002).

Covers:

* :class:`JtbdCopyOverrides` schema — ``extra='forbid'`` at the top level,
  namespace-pattern validation for applied ``strings`` keys.
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

import importlib.machinery
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from flowforge_cli.commands import polish_copy as polish_copy_module
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


def test_schema_accepts_valid_field_label_namespace_keys() -> None:
	"""The applied field-label namespace validates cleanly."""

	model = JtbdCopyOverrides(
		tone_profile="formal-professional",
		strings={
			"claim_intake.field.claimant_name.label": "Claimant full name",
		},
		llm_provider="anthropic",
		llm_model="claude-3-5-sonnet-latest",
		prompt_sha256="a" * 64,
	)
	assert model.tone_profile == "formal-professional"
	assert model.llm_provider == "anthropic"
	assert model.llm_model == "claude-3-5-sonnet-latest"
	assert model.prompt_sha256 == "a" * 64
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


def test_schema_rejects_unapplied_or_typo_suffixes() -> None:
	"""Only field labels are accepted until other namespaces are wired."""

	for bad in (
		"claim_intake.field.claimant_name.labels",  # plural
		"claim_intake.field.claimant_name.helper_text",  # not applied by generators
		"claim_intake.button.submit.text",  # not applied by generators
		"claim_intake.notification.x.template",  # not applied by generators
		"claim_intake.error.lapsed.message",  # not applied by generators
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
	"""``OVERRIDE_KEY_KINDS`` matches the namespaces generators apply."""

	assert set(OVERRIDE_KEY_KINDS) == {"field"}
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


def test_validate_key_against_bundle_reports_malformed_inputs() -> None:
	err = validate_key_against_bundle("not.a.valid.override", _bundle())
	assert err is not None and "namespace grammar" in err

	err = validate_key_against_bundle(
		"claim_intake.field.claimant_name.label",
		{"project": {"name": "missing-jtbds"}},
	)
	assert err is not None and "no `jtbds` list" in err

	bundle = _bundle()
	bundle["jtbds"][0].pop("data_capture")
	err = validate_key_against_bundle(
		"claim_intake.field.claimant_name.label",
		bundle,
	)
	assert err is not None and "no `data_capture` list" in err


def test_build_canonical_strings_emits_every_label() -> None:
	"""Canonical map carries every field label — the LLM's polish target."""

	canonical = build_canonical_strings(_bundle())
	assert canonical["claim_intake.field.claimant_name.label"] == "Claimant"
	assert canonical["claim_intake.field.loss_amount.label"] == "Loss"


def test_build_canonical_strings_skips_malformed_bundle_shapes() -> None:
	assert build_canonical_strings({"project": {"name": "missing-jtbds"}}) == {}

	bundle: dict[str, object] = {
		"jtbds": [
			"not-a-jtbd",
			{"id": 7, "data_capture": []},
			{"id": "missing_capture"},
			{
				"id": "claim_intake",
				"data_capture": [
					"not-a-field",
					{"id": 3, "label": "Ignored"},
					{"id": "claimant_name", "label": ""},
				],
			},
		]
	}

	assert build_canonical_strings(bundle) == {
		"claim_intake.field.claimant_name.label": "Claimant Name"
	}


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


def _install_fake_anthropic(
	monkeypatch: pytest.MonkeyPatch,
	*,
	body: str,
) -> None:
	"""Install a minimal fake anthropic module for the opt-in provider path."""

	class FakeMessages:
		def create(
			self,
			*,
			model: str,
			max_tokens: int,
			messages: list[dict[str, str]],
		) -> types.SimpleNamespace:
			assert model == polish_copy_module._ANTHROPIC_MODEL
			assert max_tokens == 4096
			assert messages[0]["role"] == "user"
			return types.SimpleNamespace(
				content=[types.SimpleNamespace(text=body)]
			)

	class FakeAnthropic:
		def __init__(self, *, api_key: str) -> None:
			assert api_key == "test-key"
			self.messages = FakeMessages()

	fake = types.ModuleType("anthropic")
	fake.Anthropic = FakeAnthropic  # type: ignore[attr-defined]
	monkeypatch.setitem(sys.modules, "anthropic", fake)
	monkeypatch.setattr(
		polish_copy_module.importlib.util,
		"find_spec",
		lambda name: (
			importlib.machinery.ModuleSpec(name, loader=None)
			if name == "anthropic"
			else None
		),
	)


def test_detect_polish_fn_claude_cli_missing_binary_returns_noop(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("FLOWFORGE_POLISH_PROVIDER", "claude-cli")
	monkeypatch.setattr(polish_copy_module.shutil, "which", lambda _name: None)

	fn, reason, provider, model = polish_copy_module._detect_polish_fn()

	assert provider is None
	assert model is None
	assert "claude CLI was not found" in reason
	assert fn({"claim_intake.field.claimant_name.label": "Claimant"}, "formal-professional") == {
		"claim_intake.field.claimant_name.label": "Claimant"
	}


def test_detect_polish_fn_missing_anthropic_extra_returns_noop(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
	monkeypatch.setattr(
		polish_copy_module.importlib.util,
		"find_spec",
		lambda _name: None,
	)

	fn, reason, provider, model = polish_copy_module._detect_polish_fn()

	assert provider is None
	assert model is None
	assert "flowforge-cli[llm]" in reason
	assert fn({"claim_intake.field.claimant_name.label": "Claimant"}, "formal-professional") == {
		"claim_intake.field.claimant_name.label": "Claimant"
	}


def test_detect_polish_fn_anthropic_polish_filters_and_defaults(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
	_install_fake_anthropic(
		monkeypatch,
		body=json.dumps(
			{
				"claim_intake.field.claimant_name.label": "Policyholder legal name",
				"claim_intake.field.loss_amount.label": 42,
			}
		),
	)

	fn, reason, provider, model = polish_copy_module._detect_polish_fn()

	assert reason == "anthropic API key detected — running LLM polish"
	assert provider == "anthropic"
	assert model == polish_copy_module._ANTHROPIC_MODEL
	assert fn({}, "formal-professional") == {}
	assert fn(
		{
			"claim_intake.field.claimant_name.label": "Claimant",
			"claim_intake.field.loss_amount.label": "Loss",
		},
		"formal-professional",
	) == {
		"claim_intake.field.claimant_name.label": "Policyholder legal name",
		"claim_intake.field.loss_amount.label": "Loss",
	}


@pytest.mark.parametrize(
	("body", "message"),
	[
		("not json", "anthropic response was not valid JSON"),
		(json.dumps(["not", "an", "object"]), "anthropic response must be a JSON object"),
	],
)
def test_detect_polish_fn_anthropic_rejects_bad_response(
	monkeypatch: pytest.MonkeyPatch,
	body: str,
	message: str,
) -> None:
	monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
	_install_fake_anthropic(monkeypatch, body=body)
	fn, _reason, _provider, _model = polish_copy_module._detect_polish_fn()

	with pytest.raises(polish_copy_module.PolishProviderError, match=message):
		fn({"claim_intake.field.claimant_name.label": "Claimant"}, "formal-professional")


def test_run_claude_cli_polish_empty_strings_skips_subprocess(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
		raise AssertionError("subprocess should not run for empty input")

	monkeypatch.setattr(polish_copy_module.subprocess, "run", fail_run)

	assert polish_copy_module._run_claude_cli_polish(
		{},
		"formal-professional",
		"sonnet-test",
	) == {}


@pytest.mark.parametrize(
	("exc", "message"),
	[
		(OSError("missing binary"), "claude CLI execution failed: missing binary"),
		(subprocess.TimeoutExpired(["claude"], 120), "claude CLI timed out"),
	],
)
def test_run_claude_cli_polish_reports_transport_errors(
	monkeypatch: pytest.MonkeyPatch,
	exc: Exception,
	message: str,
) -> None:
	def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
		raise exc

	monkeypatch.setattr(polish_copy_module.subprocess, "run", fake_run)

	with pytest.raises(polish_copy_module.PolishProviderError, match=message):
		polish_copy_module._run_claude_cli_polish(
			{"claim_intake.field.claimant_name.label": "Claimant"},
			"formal-professional",
			"sonnet-test",
		)


@pytest.mark.parametrize(
	("stdout", "message"),
	[
		("not json", "claude CLI response was not valid JSON"),
		(json.dumps(["not", "an", "object"]), "claude CLI response must be a JSON object"),
		(
			json.dumps({"is_error": True, "api_error_status": "401"}),
			"claude CLI returned error status 401",
		),
		(
			json.dumps({"is_error": True}),
			"claude CLI returned error status unknown",
		),
		(
			json.dumps({"structured_output": []}),
			"claude CLI response missing structured_output object",
		),
	],
)
def test_run_claude_cli_polish_rejects_unusable_payloads(
	monkeypatch: pytest.MonkeyPatch,
	stdout: str,
	message: str,
) -> None:
	def fake_run(
		cmd: list[str],
		*,
		check: bool,
		capture_output: bool,
		text: bool,
		timeout: int,
	) -> subprocess.CompletedProcess[str]:
		return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

	monkeypatch.setattr(polish_copy_module.subprocess, "run", fake_run)

	with pytest.raises(polish_copy_module.PolishProviderError, match=message):
		polish_copy_module._run_claude_cli_polish(
			{"claim_intake.field.claimant_name.label": "Claimant"},
			"formal-professional",
			"sonnet-test",
		)


def test_run_claude_cli_polish_filters_and_defaults(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_run(
		cmd: list[str],
		*,
		check: bool,
		capture_output: bool,
		text: bool,
		timeout: int,
	) -> subprocess.CompletedProcess[str]:
		assert "--max-budget-usd" in cmd
		assert check is False
		assert capture_output is True
		assert text is True
		assert timeout == 120
		return subprocess.CompletedProcess(
			cmd,
			0,
			stdout=json.dumps(
				{
					"structured_output": {
						"claim_intake.field.claimant_name.label": "Policyholder legal name",
						"claim_intake.field.loss_amount.label": 42,
					}
				}
			),
			stderr="",
		)

	monkeypatch.setattr(polish_copy_module.subprocess, "run", fake_run)

	assert polish_copy_module._run_claude_cli_polish(
		{
			"claim_intake.field.claimant_name.label": "Claimant",
			"claim_intake.field.loss_amount.label": "Loss",
		},
		"formal-professional",
		"sonnet-test",
	) == {
		"claim_intake.field.claimant_name.label": "Policyholder legal name",
		"claim_intake.field.loss_amount.label": "Loss",
	}


def test_diff_lines_reports_add_change_and_delete() -> None:
	assert polish_copy_module._diff_lines(
		{"unchanged": "same", "removed": "old", "changed": "old"},
		{"unchanged": "same", "added": "new", "changed": "new"},
	) == [
		"  + added: 'new'",
		"  ~ changed: 'old' → 'new'",
		"  - removed: 'old'",
	]


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


def test_cli_require_llm_no_api_key_fails_without_sidecar(tmp_path: Path) -> None:
	"""Release authoring can opt into fail-closed LLM detection."""

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--require-llm",
			"--commit",
		],
	)
	assert result.exit_code == 1, result.output
	assert "--require-llm needs ANTHROPIC_API_KEY" in result.output
	assert "FLOWFORGE_POLISH_PROVIDER=claude-cli" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_require_llm_missing_llm_extra_fails_without_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""--require-llm also fails when credentials exist but the LLM extra is absent."""

	monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			polish_copy_module._noop_polish,
			"anthropic package not installed (extras: 'flowforge-cli[llm]') — no-op echo",
			None,
			None,
		),
	)

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--require-llm",
			"--commit",
		],
	)
	assert result.exit_code == 1, result.output
	assert "flowforge-cli[llm]" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_require_llm_noop_polish_fails_without_new_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Release authoring cannot silently pass when the LLM produces no sidecar diff."""

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			lambda strings, _tone: dict(strings),
			"test LLM returned canonical copy",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--require-llm",
			"--commit",
		],
	)
	assert result.exit_code == 1, result.output
	assert "produced no sidecar-worthy changes" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_commit_noop_preserves_existing_reviewed_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""A canonical/no-op polish must not erase an existing reviewed sidecar."""

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			lambda strings, _tone: dict(strings),
			"test LLM returned canonical copy",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

	path = _write_bundle(tmp_path)
	sidecar = sidecar_path_for(path)
	original = dump_sidecar(
		JtbdCopyOverrides(
			tone_profile="formal-professional",
			strings={
				"claim_intake.field.claimant_name.label": "Reviewed claimant name",
			},
			llm_provider="anthropic",
			llm_model="claude-review-model",
			prompt_sha256="b" * 64,
		)
	)
	sidecar.write_text(original, encoding="utf-8")

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
	assert "reviewed sidecars" in result.output
	assert sidecar.read_text(encoding="utf-8") == original


def test_cli_provider_error_fails_without_writing_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Malformed provider output is a failed authoring run, not a canonical rewrite."""

	def broken_polish(_strings: dict[str, str], _tone: str) -> dict[str, str]:
		raise polish_copy_module.PolishProviderError("provider returned non-JSON")

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			broken_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

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
	assert result.exit_code == 1, result.output
	assert "LLM polish failed: provider returned non-JSON" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_unexpected_provider_exception_fails_without_traceback_or_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Provider transport/auth failures should be operator errors, not tracebacks."""

	def failing_polish(_strings: dict[str, str], _tone: str) -> dict[str, str]:
		raise RuntimeError("invalid x-api-key")

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			failing_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--require-llm",
			"--commit",
		],
		catch_exceptions=False,
	)
	assert result.exit_code == 1, result.output
	assert "LLM polish failed: RuntimeError: invalid x-api-key" in result.output
	assert "Traceback" not in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_claude_provider_records_cli_metadata(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""The explicit Claude CLI provider is a real-LLM authoring backend."""

	def fake_run(
		cmd: list[str],
		*,
		check: bool,
		capture_output: bool,
		text: bool,
		timeout: int,
	) -> subprocess.CompletedProcess[str]:
		assert cmd[:2] == ["claude", "--bare"]
		assert "--json-schema" in cmd
		assert check is False
		assert capture_output is True
		assert text is True
		assert timeout == 120
		return subprocess.CompletedProcess(
			cmd,
			0,
			stdout=json.dumps(
				{
					"is_error": False,
					"structured_output": {
						"claim_intake.field.claimant_name.label": "Policyholder legal name"
					},
				}
			),
			stderr="",
		)

	monkeypatch.setenv("FLOWFORGE_POLISH_PROVIDER", "claude-cli")
	monkeypatch.setenv("FLOWFORGE_POLISH_CLAUDE_MODEL", "sonnet-test")
	monkeypatch.setattr(polish_copy_module.shutil, "which", lambda _name: "/bin/claude")
	monkeypatch.setattr(polish_copy_module.subprocess, "run", fake_run)

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--require-llm",
			"--commit",
		],
	)
	assert result.exit_code == 0, result.output
	sidecar = load_sidecar(path)
	assert sidecar is not None
	assert sidecar.llm_provider == "claude-cli"
	assert sidecar.llm_model == "sonnet-test"
	assert sidecar.strings["claim_intake.field.claimant_name.label"] == (
		"Policyholder legal name"
	)


def test_cli_claude_provider_failure_fails_without_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Claude CLI failures remain failed authoring runs."""

	def fake_run(
		cmd: list[str],
		*,
		check: bool,
		capture_output: bool,
		text: bool,
		timeout: int,
	) -> subprocess.CompletedProcess[str]:
		assert check is False
		assert capture_output is True
		assert text is True
		assert timeout == 120
		return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not funded")

	monkeypatch.setenv("FLOWFORGE_POLISH_PROVIDER", "claude-cli")
	monkeypatch.setattr(polish_copy_module.shutil, "which", lambda _name: "/bin/claude")
	monkeypatch.setattr(polish_copy_module.subprocess, "run", fake_run)

	path = _write_bundle(tmp_path)
	result = runner.invoke(
		app,
		[
			"polish-copy",
			"--bundle",
			str(path),
			"--tone",
			"formal-professional",
			"--require-llm",
			"--commit",
		],
	)
	assert result.exit_code == 1, result.output
	assert "claude CLI failed: not funded" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_commit_llm_polish_records_model_and_prompt_checksum(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Committed LLM sidecars carry enough metadata for audit review."""

	def fake_polish(strings: dict[str, str], _tone: str) -> dict[str, str]:
		out = dict(strings)
		out["claim_intake.field.claimant_name.label"] = "Policyholder legal name"
		return out

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			fake_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

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
	sidecar = load_sidecar(path)
	assert sidecar is not None
	assert sidecar.strings["claim_intake.field.claimant_name.label"] == (
		"Policyholder legal name"
	)
	assert sidecar.llm_provider == "anthropic"
	assert sidecar.llm_model == "claude-test-model-20260518"
	assert sidecar.prompt_sha256 == polish_copy_module._prompt_sha256(
		build_canonical_strings(_bundle()),
		"formal-professional",
	)


def test_cli_rejects_polish_output_for_unknown_bundle_key(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_polish(strings: dict[str, str], _tone: str) -> dict[str, str]:
		out = dict(strings)
		out["claim_intake.field.unknown_field.label"] = "Unknown"
		return out

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			fake_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

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
	assert result.exit_code != 0
	assert "polish output rejected" in result.output


def test_cli_dry_run_reports_llm_proposed_changes(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_polish(strings: dict[str, str], _tone: str) -> dict[str, str]:
		out = dict(strings)
		out["claim_intake.field.claimant_name.label"] = "Policyholder legal name"
		return out

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			fake_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

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
	assert "proposed changes" in result.output
	assert "~ claim_intake.field.claimant_name.label" in result.output
	assert not sidecar_path_for(path).exists()


def test_cli_commit_skips_semantically_unchanged_sidecar(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	polished = {
		"claim_intake.field.claimant_name.label": "Policyholder legal name",
		"claim_intake.field.loss_amount.label": "Loss",
	}

	def fake_polish(_strings: dict[str, str], _tone: str) -> dict[str, str]:
		return dict(polished)

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			fake_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

	path = _write_bundle(tmp_path)
	sidecar = sidecar_path_for(path)
	original = dump_sidecar(
		JtbdCopyOverrides(
			tone_profile="formal-professional",
			strings=polished,
			llm_provider="anthropic",
			llm_model="older-model",
			prompt_sha256="c" * 64,
		)
	)
	sidecar.write_text(original, encoding="utf-8")

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
	assert "no semantic change" in result.output
	assert sidecar.read_text(encoding="utf-8") == original


def test_cli_commit_can_rewrite_metadata_without_applied_change_lines(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	polished = {
		"claim_intake.field.claimant_name.label": "Policyholder legal name",
		"claim_intake.field.loss_amount.label": "Loss",
	}

	def fake_polish(_strings: dict[str, str], _tone: str) -> dict[str, str]:
		return dict(polished)

	monkeypatch.setattr(
		polish_copy_module,
		"_detect_polish_fn",
		lambda: (
			fake_polish,
			"test LLM polish",
			"anthropic",
			"claude-test-model-20260518",
		),
	)

	path = _write_bundle(tmp_path)
	sidecar_path_for(path).write_text(
		dump_sidecar(
			JtbdCopyOverrides(
				tone_profile="friendly-direct",
				strings=polished,
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
			"--commit",
		],
	)
	assert result.exit_code == 0, result.output
	assert "wrote" in result.output
	assert "applied changes" not in result.output
	sidecar = load_sidecar(path)
	assert sidecar is not None
	assert sidecar.tone_profile == "formal-professional"


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


def test_cli_dry_run_no_api_key_preserves_existing_sidecar(
	tmp_path: Path,
) -> None:
	"""No-key dry-run must not imply a reviewed sidecar should be reverted."""

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
	assert "existing reviewed sidecar is preserved" in result.output
	assert "proposed changes" not in result.output


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
