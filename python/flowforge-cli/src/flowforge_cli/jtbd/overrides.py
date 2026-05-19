"""Copy-override sidecar schema + loader (v0.3.0 W4b / item 22 / ADR-002).

The canonical :class:`flowforge_jtbd.dsl.spec.JtbdBundle` stays
content-addressable (its ``spec_hash`` is invariant to copy polish).
LLM-driven last-mile copy polish for field labels lives in a *sidecar*
file co-located with the bundle on disk:

    <bundle_path>.overrides.json

This module owns:

* :class:`JtbdCopyOverrides` — the sidecar schema (Pydantic v2,
  ``extra='forbid'``). Lives here, in the CLI/consumer layer, not in
  ``flowforge-jtbd``'s canonical DSL.
* :func:`sidecar_path_for` — pure function: bundle path → sidecar path.
* :func:`load_sidecar` — load + validate the co-located sidecar; ``None``
  if it does not exist.
* :func:`resolve_sidecar` — apply the ADR-002 lookup precedence
  (``--overrides`` flag wins, then co-located, then ``None``).

Per ADR-002 (``docs/v0.3.0-engineering/adr/ADR-002-copy-override-sidecar.md``)
the override file is a generation-time concern only. ``form_spec.json``
and the frontend ``Step.tsx`` apply overrides at emit time; the canonical
``JtbdBundle.model_validate()`` never sees them and ``spec_hash`` is
untouched.

The string keys follow the namespace pattern:

* ``<jtbd_id>.field.<field_id>.label``

Keys outside the namespace are rejected by a model-level validator so a
hand-edited sidecar can't accidentally introduce a key the consumers
won't recognise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


__all__ = [
	"JtbdCopyOverrides",
	"ToneProfile",
	"TONE_PROFILES",
	"OVERRIDE_KEY_KINDS",
	"SCHEMA_VERSION",
	"sidecar_path_for",
	"load_sidecar",
	"resolve_sidecar",
	"validate_key_against_bundle",
	"build_canonical_strings",
]


# Schema version pin. Bump on any breaking change to the sidecar wire
# format; v0.3.0 ships ``"1.0"``.
SCHEMA_VERSION: Literal["1.0"] = "1.0"


# Canonical tone profiles. The LLM prompt shapes its rewrites from
# whichever profile is passed at authoring time; the sidecar records
# which profile produced the strings so a reviewer can trace intent.
ToneProfile = Literal[
	"formal-professional",
	"friendly-direct",
	"regulator-compliant",
]

TONE_PROFILES: tuple[str, ...] = (
	"formal-professional",
	"friendly-direct",
	"regulator-compliant",
)


# Recognised key namespaces — the suffix after ``<jtbd_id>.``. The
# regex captures the JTBD id (snake_case), the kind (one of these), the
# identifier (field_id / event / topic / code), and the leaf suffix.
OVERRIDE_KEY_KINDS: tuple[str, ...] = (
	"field",
)


# Strict per-kind suffix grammar. Each pattern is anchored. Identifiers
# accept snake_case + digits (matches the bundle's id grammar). The
# leaf suffix is fixed per kind so a typo (``label`` ↔ ``labels``)
# fails validation.
_KEY_PATTERN = re.compile(
	r"^"
	r"(?P<jtbd>[a-z][a-z0-9_]*)"
	r"\.field\.(?P<field>[a-z][a-z0-9_]*)\.label"
	r"$"
)


class JtbdCopyOverrides(BaseModel):
	"""Sidecar payload that pairs with a bundle on disk.

	The model is locked down: ``extra='forbid'`` on the top-level + a
	model validator that walks every key in ``strings`` and asserts it
	matches the documented namespace grammar. A hand-edited sidecar
	cannot smuggle keys past the validator.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	version: Literal["1.0"] = "1.0"
	tone_profile: ToneProfile
	strings: dict[str, str]
	# Metadata (audit trail; intentionally not part of the override
	# payload). ``flowforge polish-copy --commit`` stamps these on
	# write; consumers read them only for debugging.
	generated_at: str | None = None
	generator_version: str | None = None
	llm_provider: str | None = None
	llm_model: str | None = None
	prompt_sha256: str | None = None

	@model_validator(mode="after")
	def _validate_string_keys(self) -> JtbdCopyOverrides:
		"""Reject any key that does not match the documented namespace."""

		bad: list[str] = []
		for key in self.strings:
			if not isinstance(key, str) or not _KEY_PATTERN.match(key):
				bad.append(key)
		if bad:
			rendered = ", ".join(repr(k) for k in bad[:5])
			suffix = "" if len(bad) <= 5 else f" (+{len(bad) - 5} more)"
			raise ValueError(
				"copy-override keys must match "
				"'<jtbd_id>.field.<field_id>.label'; "
				f"rejected: {rendered}{suffix}"
			)
		return self

	# ------------------------------------------------------------------
	# Convenience accessor — narrow the call surface in generators so
	# they don't reach into ``strings`` directly. Returns the override
	# when present, else ``fallback``.
	# ------------------------------------------------------------------

	def field_label(self, jtbd_id: str, field_id: str, fallback: str) -> str:
		key = f"{jtbd_id}.field.{field_id}.label"
		return self.strings.get(key, fallback)


# ---------------------------------------------------------------------------
# Sidecar resolution — pure path math + filesystem I/O
# ---------------------------------------------------------------------------


def sidecar_path_for(bundle_path: Path) -> Path:
	"""Return the canonical sidecar path for *bundle_path*.

	Always ``<bundle_path>.overrides.json`` — the suffix is appended
	verbatim, not substituted, so ``foo.json`` becomes
	``foo.json.overrides.json``. The repetition is deliberate: it keeps
	two unrelated example bundles in the same directory from
	cross-pollinating because the sidecar carries the full bundle
	filename, not just the stem.
	"""

	assert isinstance(bundle_path, Path), "bundle_path must be a Path"
	return bundle_path.with_name(bundle_path.name + ".overrides.json")


def load_sidecar(bundle_path: Path) -> JtbdCopyOverrides | None:
	"""Load the co-located sidecar for *bundle_path*, or ``None``.

	Raises :class:`pydantic.ValidationError` if the file exists but is
	malformed — callers should let that bubble up so a bad sidecar
	fails noisily rather than silently dropping overrides.
	"""

	assert isinstance(bundle_path, Path), "bundle_path must be a Path"
	sidecar = sidecar_path_for(bundle_path)
	if not sidecar.exists():
		return None
	raw = sidecar.read_text(encoding="utf-8")
	return JtbdCopyOverrides.model_validate_json(raw)


def resolve_sidecar(
	bundle_path: Path,
	explicit: Path | None = None,
) -> JtbdCopyOverrides | None:
	"""Apply the ADR-002 lookup precedence and return the sidecar (or ``None``).

	1. ``explicit`` (the ``--overrides <path>`` flag) wins when present.
	2. Else the co-located ``<bundle_path>.overrides.json`` is used.
	3. Else ``None`` — generators fall back to canonical strings.
	"""

	assert isinstance(bundle_path, Path), "bundle_path must be a Path"
	if explicit is not None:
		assert isinstance(explicit, Path), "explicit must be a Path"
		raw = explicit.read_text(encoding="utf-8")
		return JtbdCopyOverrides.model_validate_json(raw)
	return load_sidecar(bundle_path)


# ---------------------------------------------------------------------------
# Cross-check helpers — used by ``flowforge polish-copy`` to ensure the
# sidecar keys resolve to real bundle fields before we write the file.
# Keeps a typo in a hand-edited sidecar from silently producing dead
# overrides that the generator will never look up.
# ---------------------------------------------------------------------------


def validate_key_against_bundle(
	key: str,
	bundle: dict[str, object],
) -> str | None:
	"""Return ``None`` if *key* resolves to a real bundle target, else an error.

	The bundle is the raw parsed JSON (pre-normalize). Only ``field.*``
	keys are accepted by the sidecar schema today, and every accepted key
	is cross-checked against the bundle before the release gate can pass.
	"""

	assert isinstance(key, str), "key must be a string"
	assert isinstance(bundle, dict), "bundle must be a dict"

	match = _KEY_PATTERN.match(key)
	if match is None:
		return f"{key!r}: does not match the override namespace grammar"

	jtbd_id = match.group("jtbd")
	jtbds = bundle.get("jtbds")
	if not isinstance(jtbds, list):
		return f"{key!r}: bundle has no `jtbds` list"
	jtbd = next(
		(j for j in jtbds if isinstance(j, dict) and j.get("id") == jtbd_id),
		None,
	)
	if jtbd is None:
		return f"{key!r}: no JTBD with id {jtbd_id!r} in bundle"

	field_id = match.group("field")

	captures = jtbd.get("data_capture")
	if not isinstance(captures, list):
		return f"{key!r}: JTBD {jtbd_id!r} has no `data_capture` list"
	if not any(
		isinstance(f, dict) and f.get("id") == field_id for f in captures
	):
		return (
			f"{key!r}: JTBD {jtbd_id!r} has no data_capture field "
			f"with id {field_id!r}"
		)
	return None


def build_canonical_strings(bundle: dict[str, object]) -> dict[str, str]:
	"""Walk a parsed bundle and emit the canonical-string key→value map.

	The result is what ``flowforge polish-copy`` would write to disk if
	the LLM produced verbatim copies of the source strings. This is the
	deterministic input the LLM rewrite is applied on top of, and the
	identity vs the rewrite is what ``--dry-run`` diffs against.

	Covers field labels — the only sidecar namespace that generators
	apply today. Other user-facing string surfaces must be wired into
	generated artifacts before the schema accepts them.
	"""

	assert isinstance(bundle, dict), "bundle must be a dict"

	out: dict[str, str] = {}
	jtbds = bundle.get("jtbds")
	if not isinstance(jtbds, list):
		return out
	for jtbd in jtbds:
		if not isinstance(jtbd, dict):
			continue
		jtbd_id = jtbd.get("id")
		if not isinstance(jtbd_id, str):
			continue
		captures = jtbd.get("data_capture")
		if not isinstance(captures, list):
			continue
		for field in captures:
			if not isinstance(field, dict):
				continue
			field_id = field.get("id")
			if not isinstance(field_id, str):
				continue
			label = field.get("label")
			if isinstance(label, str) and label:
				out[f"{jtbd_id}.field.{field_id}.label"] = label
			else:
				# Derive a sensible default the same way normalize.py does
				# so the LLM has something concrete to polish.
				out[f"{jtbd_id}.field.{field_id}.label"] = (
					field_id.replace("_", " ").title()
				)
	return out


def dump_sidecar(overrides: JtbdCopyOverrides) -> str:
	"""Render *overrides* as deterministic JSON (sorted keys, trailing newline).

	Used by ``flowforge polish-copy --commit`` so two writes of the same
	logical override set produce byte-identical sidecars.
	"""

	assert isinstance(overrides, JtbdCopyOverrides)
	payload = json.loads(overrides.model_dump_json(exclude_none=True))
	return json.dumps(payload, indent=2, sort_keys=True) + "\n"
