"""``flowforge polish-copy`` — opt-in LLM copy polish via sidecar (v0.3.0 W4b / item 22).

Per ADR-002 (``docs/v0.3.0-engineering/adr/ADR-002-copy-override-sidecar.md``):

* Result lands at ``<bundle_path>.overrides.json`` — a sidecar, never
  inside the canonical bundle. ``spec_hash`` stays invariant.
* This is the only LLM touchpoint in the entire generation pipeline.
* The LLM run is an **authoring-time** step. ``jtbd-generate`` reads
  the sidecar at emit time; the LLM is never invoked during regen or
  in CI.
* If the host has no API key configured, the command degrades to a
  no-op echo: the canonical strings round-trip unchanged and
  ``--dry-run`` reports an empty diff.

Modes:

* ``--dry-run`` (default) — print the override key→value diff vs the
  on-disk sidecar (or vs canonical when no sidecar exists). Does not
  touch the filesystem. Exits 0 always.
* ``--commit`` — write the sidecar to disk. If the rewrite is
  identical to canonical (e.g. no API key set), the sidecar is **not
  written** — that keeps the CI gate
  ``tests/v0_3_0/test_polish_copy_committed_overrides.py`` green when
  the command is invoked without an LLM available.

Tone profiles (per ADR-002): ``formal-professional``,
``friendly-direct``, ``regulator-compliant``. The profile is recorded
on the sidecar so a reviewer can trace intent.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable

import typer

from .._io import load_structured
from ..jtbd.overrides import (
	JtbdCopyOverrides,
	SCHEMA_VERSION,
	TONE_PROFILES,
	ToneProfile,
	build_canonical_strings,
	dump_sidecar,
	resolve_sidecar,
	sidecar_path_for,
	validate_key_against_bundle,
)


__all__ = ["register", "polish_copy_cmd"]


# Generator version stamp written into the sidecar. Bump alongside the
# ``flowforge-cli`` package version so two sidecars produced by different
# CLI builds are distinguishable in audit trails.
_GENERATOR_VERSION = "flowforge polish-copy v0.3.0"


# Polish function signature: (canonical-key→value, tone) → rewritten-key→value.
# Pluggable so tests can inject a deterministic fake without needing an
# LLM credential.
PolishFn = Callable[[dict[str, str], ToneProfile], dict[str, str]]


def _noop_polish(strings: dict[str, str], _tone: ToneProfile) -> dict[str, str]:
	"""Identity polish — returned when no LLM is wired up."""

	# ``_tone`` intentionally unused; the no-op path is tone-agnostic.
	# Pyright basic-mode wants the reference to silence the unused-arg
	# diagnostic, so consume it here without observable side effects.
	assert _tone in TONE_PROFILES or isinstance(_tone, str)
	return dict(strings)


def _detect_polish_fn() -> tuple[PolishFn, str]:
	"""Pick the polish callable based on what credentials are configured.

	Returns ``(fn, reason)``. ``reason`` is a one-line human-readable
	description that the CLI prints so an operator running the command
	can see why it degraded to a no-op (the most common case in CI).
	"""

	# Anthropic is the project's preferred LLM (project CLAUDE.md routes
	# LLM work through Claude). The optional ``anthropic`` package is
	# declared under ``[project.optional-dependencies] llm``; if it's not
	# installed, or if no key is set, we degrade to a no-op echo.
	api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
	if not api_key:
		return _noop_polish, "no ANTHROPIC_API_KEY/CLAUDE_API_KEY set — no-op echo"
	# Existence check via ``importlib.util.find_spec`` — keeps
	# ``flowforge-cli`` importable without the optional ``anthropic``
	# dep installed (matches ADR-002 + plan §11 #3: the LLM is opt-in
	# soft dep). The actual import lives inside the polish closure so
	# the type checker sees a real usage, not a discarded import.
	if importlib.util.find_spec("anthropic") is None:
		return (
			_noop_polish,
			"anthropic package not installed (extras: 'flowforge-cli[llm]') — no-op echo",
		)

	def _anthropic_polish(strings: dict[str, str], tone: ToneProfile) -> dict[str, str]:
		"""Real LLM polish path — kept thin; the prompt is the contract.

		The function is *defined* but **never exercised in CI** — the CI
		env never has an API key. Hosts that run ``polish-copy`` with a
		key see real rewrites; everyone else gets the no-op path above.
		"""

		# Cheap defence in depth: with zero strings to polish, skip the
		# round-trip entirely.
		if not strings:
			return {}
		import anthropic  # type: ignore[import-not-found]

		client = anthropic.Anthropic(api_key=api_key)
		prompt = (
			"You are a UX copywriter. Rewrite each value in the JSON object "
			"below in the requested tone. PRESERVE the keys exactly. PRESERVE "
			"the meaning. Return only the JSON object, no commentary.\n\n"
			f"Tone: {tone}\n"
			f"Strings: {strings!r}\n"
		)
		message = client.messages.create(
			model="claude-3-5-sonnet-latest",
			max_tokens=4096,
			messages=[{"role": "user", "content": prompt}],
		)
		# ``message.content`` is a list of content blocks; for the
		# JSON-only contract above the first block is a text block.
		body = "".join(
			getattr(b, "text", "") for b in message.content
		).strip()
		import json as _json

		try:
			parsed = _json.loads(body)
		except _json.JSONDecodeError:
			# LLM returned something the validator can't accept — fall
			# back to canonical and let the caller see an empty diff.
			return dict(strings)
		if not isinstance(parsed, dict):
			return dict(strings)
		# Keep only string-typed values to stay schema-clean.
		out: dict[str, str] = {}
		for k, v in parsed.items():
			if isinstance(k, str) and isinstance(v, str):
				out[k] = v
		# Never drop keys the LLM omitted — substitute canonical instead.
		for k, v in strings.items():
			out.setdefault(k, v)
		return out

	return _anthropic_polish, "anthropic API key detected — running LLM polish"


def _diff_lines(
	old: dict[str, str],
	new: dict[str, str],
) -> list[str]:
	"""Return human-readable diff lines (``+``/``-``/``~``)."""

	out: list[str] = []
	keys = sorted(set(old) | set(new))
	for k in keys:
		o = old.get(k)
		n = new.get(k)
		if o == n:
			continue
		if o is None:
			out.append(f"  + {k}: {n!r}")
		elif n is None:
			out.append(f"  - {k}: {o!r}")
		else:
			out.append(f"  ~ {k}: {o!r} → {n!r}")
	return out


def polish_copy_cmd(
	bundle: Annotated[
		Path,
		typer.Option(
			"--bundle",
			exists=True,
			file_okay=True,
			dir_okay=False,
			readable=True,
			help="Path to the JTBD bundle (the sidecar lands at <bundle>.overrides.json).",
		),
	],
	tone: Annotated[
		str,
		typer.Option(
			"--tone",
			help=f"Tone profile — one of: {', '.join(TONE_PROFILES)}.",
		),
	] = "formal-professional",
	overrides_path: Annotated[
		Path | None,
		typer.Option(
			"--overrides",
			help=(
				"Override sidecar source path (defaults to <bundle>.overrides.json). "
				"Used to read existing overrides for the diff baseline."
			),
		),
	] = None,
	dry_run: Annotated[
		bool,
		typer.Option(
			"--dry-run/--no-dry-run",
			help="Print the diff vs the existing sidecar; do not write to disk.",
		),
	] = True,
	commit: Annotated[
		bool,
		typer.Option(
			"--commit",
			help="Write the sidecar to disk. Mutually exclusive with --dry-run.",
		),
	] = False,
) -> None:
	"""Polish user-facing strings (labels / helper text / buttons / notifs / errors).

	Per ADR-002: writes a *sidecar* at ``<bundle>.overrides.json``;
	leaves the canonical bundle and ``spec_hash`` untouched. The LLM
	run is authoring-time only — ``jtbd-generate`` reads the sidecar
	deterministically.
	"""

	# Validate tone before doing any work — Typer doesn't enforce
	# Literal[...] choices through plain str options.
	if tone not in TONE_PROFILES:
		raise typer.BadParameter(
			f"tone must be one of {list(TONE_PROFILES)!r}, got {tone!r}"
		)
	tone_profile: ToneProfile = tone  # type: ignore[assignment]

	if commit and dry_run:
		# Explicit ``--commit`` overrides the default ``--dry-run=True``;
		# treat ``--commit`` as the authoritative intent.
		dry_run = False

	raw_bundle = load_structured(bundle)

	# Baseline: existing sidecar (per --overrides flag if set, else
	# co-located). The diff is computed against this baseline so two
	# runs of polish-copy without intervening edits produce no diff.
	existing = resolve_sidecar(bundle, overrides_path)
	existing_strings: dict[str, str] = dict(existing.strings) if existing else {}

	canonical = build_canonical_strings(raw_bundle)

	polish_fn, reason = _detect_polish_fn()
	typer.echo(f"flowforge polish-copy: {reason}")

	# Polish the canonical map. The LLM sees only the canonical strings
	# — we never feed it the existing overrides because authors may have
	# hand-edited them and we don't want a second LLM pass to overwrite
	# manual polish.
	polished = polish_fn(canonical, tone_profile)

	# Cross-check every polished key resolves to a real bundle target —
	# catches a bug in the polish function that emits a stray key.
	for key in polished:
		err = validate_key_against_bundle(key, raw_bundle)
		if err is not None:
			raise typer.BadParameter(f"polish output rejected: {err}")

	# A polish that returns the canonical map verbatim is a no-op.
	# Skip writing the sidecar so the CI ``git status --porcelain``
	# gate stays clean when no LLM is wired up.
	is_noop = polished == canonical

	# Diff baseline:
	# * If a sidecar already exists, diff polished vs that sidecar so an
	#   author can see what the LLM proposes on top of their last commit.
	# * Else diff against canonical.
	baseline = existing_strings if existing_strings else canonical
	lines = _diff_lines(baseline, polished)

	if dry_run:
		typer.echo(f"flowforge polish-copy: tone={tone_profile} bundle={bundle}")
		if lines:
			typer.echo("flowforge polish-copy: proposed changes")
			for ln in lines:
				typer.echo(ln)
		else:
			typer.echo("flowforge polish-copy: no diff — canonical strings unchanged.")
		return

	# --commit path
	sidecar = (
		overrides_path if overrides_path is not None
		else sidecar_path_for(bundle)
	)

	if is_noop and existing is None:
		typer.echo(
			"flowforge polish-copy: no-op (canonical strings unchanged, no existing "
			f"sidecar) — not writing {sidecar} so git status stays clean."
		)
		return

	model = JtbdCopyOverrides(
		version=SCHEMA_VERSION,
		tone_profile=tone_profile,
		strings=polished,
		generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
		generator_version=_GENERATOR_VERSION,
	)
	# Write deterministically (sorted keys, 2-space indent, trailing newline).
	new_text = dump_sidecar(model)

	# If the on-disk file is byte-identical (after stripping the
	# generated_at timestamp), skip the rewrite so we don't churn the
	# git tree purely to update a timestamp.
	if existing is not None:
		existing_text_stable = dump_sidecar(
			JtbdCopyOverrides(
				version=existing.version,
				tone_profile=existing.tone_profile,
				strings=existing.strings,
				generated_at=None,
				generator_version=None,
			)
		)
		new_text_stable = dump_sidecar(
			JtbdCopyOverrides(
				version=model.version,
				tone_profile=model.tone_profile,
				strings=model.strings,
				generated_at=None,
				generator_version=None,
			)
		)
		if existing_text_stable == new_text_stable:
			typer.echo(
				f"flowforge polish-copy: no semantic change vs {sidecar} — "
				"skipping write to keep git status clean."
			)
			return

	sidecar.write_text(new_text, encoding="utf-8")
	typer.echo(f"flowforge polish-copy: wrote {sidecar}")
	if lines:
		typer.echo("flowforge polish-copy: applied changes")
		for ln in lines:
			typer.echo(ln)


def register(app: typer.Typer) -> None:
	"""Mount ``flowforge polish-copy`` on the root app."""

	app.command(
		"polish-copy",
		help=(
			"Opt-in LLM polish over user-facing copy. Writes a sidecar at "
			"<bundle>.overrides.json per ADR-002 (item 22 of "
			"docs/improvements.md). No-op without an API key."
		),
	)(polish_copy_cmd)
