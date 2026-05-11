"""Per-bundle generator: i18n catalogs + type-safe useT() hook.

v0.3.0 W4b / item 17 of :doc:`docs/improvements`. Generates one JSON
catalog per declared ``project.languages`` entry plus a TypeScript
``useT()`` hook with a string-literal union of every key path. The
English catalog is populated from the bundle (field labels, transition
event button text, audit topics rendered human-readable, SLA copy).
Non-English catalogs are emitted STRUCTURALLY IDENTICAL (same keys,
same order) with values left as empty strings — they are the lint
targets for the ``audit-2026-i18n-coverage`` gate.

Determinism: JSON is emitted with ``sort_keys=True`` and a trailing
newline so two regens against the same bundle produce byte-identical
catalogs.

Per-bundle aggregation per Principle 2 of the v0.3.0 engineering plan:
one set of files per bundle regardless of how many JTBDs it declares.

The fixture-registry primer at :mod:`._fixture_registry` records the
attribute paths this generator reads; the bidirectional coverage test
cross-checks generator and registry.
"""

from __future__ import annotations

import json

from ..normalize import NormalizedBundle
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].audit_topics",
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].label",
	"jtbds[].id",
	"jtbds[].sla_breach_seconds",
	"jtbds[].sla_warn_pct",
	"jtbds[].title",
	"jtbds[].transitions",
	"project.languages",
	"project.package",
)


# Default language tuple when ``project.languages`` is missing / empty.
# Mirrors :func:`flowforge_cli.jtbd.normalize.normalize` (which already
# defaults to ``("en",)``) so the generator never sees an empty tuple
# in practice, but kept here for defence-in-depth.
_DEFAULT_LANGUAGES: tuple[str, ...] = ("en",)


# Lifecycle verbs that read naturally as past tense after a subject;
# anything else gets a colon-separated annotation
# (``Claim Intake: large loss`` vs ``Claim Intake submitted``).
_LIFECYCLE_VERBS: frozenset[str] = frozenset(
	{
		"submitted",
		"approved",
		"rejected",
		"escalated",
		"returned",
		"completed",
		"failed",
	}
)


def humanize_topic(topic: str) -> str:
	"""Render an audit topic dotted-id as a human-readable English template.

	Examples:

	* ``claim_intake.submitted`` → ``"Claim Intake submitted"``
	* ``claim_intake.large_loss`` → ``"Claim Intake: large loss"``
	* ``claim_intake.escalated`` → ``"Claim Intake escalated"``

	The exact template is the English-locale string. Other locales
	receive an empty value (the lint target).
	"""

	assert isinstance(topic, str), "topic must be a string"
	if "." not in topic:
		return topic.replace("_", " ").title()
	prefix, _, suffix = topic.partition(".")
	subject = prefix.replace("_", " ").title()
	verb = suffix.replace("_", " ")
	if (
		verb in _LIFECYCLE_VERBS
		or suffix.endswith("_rejected")
		or suffix.endswith("_returned")
	):
		return f"{subject} {verb}"
	return f"{subject}: {verb}"


def humanize_event(event: str) -> str:
	"""Render a transition event verb as button text.

	Examples:

	* ``submit`` → ``"Submit"``
	* ``approve`` → ``"Approve"``
	* ``branch_large_loss`` → ``"Branch large loss"``
	"""

	assert isinstance(event, str), "event must be a string"
	return event.replace("_", " ").strip().capitalize()


def english_catalog(bundle: NormalizedBundle) -> dict[str, str]:
	"""Build the fully-populated English catalog.

	Keys are sorted before emission by the JSON serializer; this function
	just collects them. The key namespace:

	* ``jtbd.<id>.title`` — the JTBD title
	* ``jtbd.<id>.field.<field_id>.label`` — every data-capture field label
	* ``jtbd.<id>.button.<event>`` — every transition event button label
	* ``jtbd.<id>.sla.warn`` — SLA warning copy (only when ``sla.warn_pct`` set)
	* ``jtbd.<id>.sla.breach`` — SLA breach copy (only when ``sla.breach_seconds`` set)
	* ``audit.<topic>`` — human-readable audit-event template, one per
	  ``bundle.all_audit_topics`` entry
	"""

	assert isinstance(bundle, NormalizedBundle), "bundle must be NormalizedBundle"
	catalog: dict[str, str] = {}
	for jt in bundle.jtbds:
		catalog[f"jtbd.{jt.id}.title"] = jt.title
		for field in jt.fields:
			catalog[f"jtbd.{jt.id}.field.{field.id}.label"] = field.label
		seen_events: set[str] = set()
		for tr in jt.transitions:
			event = str(tr.get("event", ""))
			if not event or event in seen_events:
				continue
			seen_events.add(event)
			catalog[f"jtbd.{jt.id}.button.{event}"] = humanize_event(event)
		if jt.sla_warn_pct is not None:
			catalog[f"jtbd.{jt.id}.sla.warn"] = (
				f"SLA approaching ({jt.sla_warn_pct}% elapsed): please act soon."
			)
		if jt.sla_breach_seconds is not None:
			catalog[f"jtbd.{jt.id}.sla.breach"] = (
				"SLA breached: response time exceeded the agreed budget."
			)
	for topic in bundle.all_audit_topics:
		catalog[f"audit.{topic}"] = humanize_topic(topic)
	return catalog


def empty_mirror(catalog: dict[str, str]) -> dict[str, str]:
	"""Return a catalog with the same keys as *catalog* but empty values."""

	return {k: "" for k in catalog}


def _emit_json(payload: dict[str, str]) -> str:
	"""Serialize *payload* to deterministic JSON with a trailing newline.

	``sort_keys=True`` plus an explicit trailing ``\\n`` so two regens
	produce byte-identical output regardless of dict iteration order.
	"""

	return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _render_useT(bundle: NormalizedBundle, english: dict[str, str]) -> str:
	"""Render the TypeScript ``useT()`` hook source.

	The hook is dependency-free; hosts wire it to react-intl / i18next /
	whatever they ship with by replacing the default catalog import in
	their app shell. The hook's TS signature pins the closed set of keys
	so a typo at a call site fails ``tsc`` instead of returning ``undefined``
	at runtime.
	"""

	assert isinstance(bundle, NormalizedBundle), "bundle must be NormalizedBundle"
	keys = sorted(english.keys())
	languages = bundle.project.languages or _DEFAULT_LANGUAGES
	default_lang = languages[0]
	tab = "\t"
	newline = "\n"
	if keys:
		key_union_lines = [f'{tab}| "{k}"' for k in keys]
		key_union = newline.join(key_union_lines)
	else:
		key_union = f'{tab}| ""'
	languages_block = newline.join(f'{tab}"{lang}",' for lang in languages)
	lines: list[str] = []
	lines.append("// Generated by flowforge JTBD generator (W4b / item 17 of docs/improvements.md).")
	lines.append("// Type-safe i18n hook bound to the closed catalog of keys emitted into")
	lines.append("// the sibling `<lang>.json` files. Re-run the generator to regenerate;")
	lines.append("// do not edit by hand.")
	lines.append("")
	lines.append('import * as React from "react";')
	lines.append("")
	lines.append(f'import enCatalog from "./{default_lang}.json";')
	lines.append("")
	lines.append("export type TranslationKey =")
	lines.append(f"{key_union};")
	lines.append("")
	lines.append("export type TranslationCatalog = Record<TranslationKey, string>;")
	lines.append("")
	lines.append("export const AVAILABLE_LANGUAGES: ReadonlyArray<string> = [")
	lines.append(languages_block)
	lines.append("] as const;")
	lines.append("")
	lines.append(f'export const DEFAULT_LANGUAGE = "{default_lang}";')
	lines.append("")
	lines.append("interface I18nContextValue {")
	lines.append(f"{tab}lang: string;")
	lines.append(f"{tab}catalog: TranslationCatalog;")
	lines.append("}")
	lines.append("")
	lines.append("const defaultContext: I18nContextValue = {")
	lines.append(f"{tab}lang: DEFAULT_LANGUAGE,")
	lines.append(f"{tab}catalog: enCatalog as TranslationCatalog,")
	lines.append("};")
	lines.append("")
	lines.append(
		"export const I18nContext: React.Context<I18nContextValue> ="
		" React.createContext<I18nContextValue>(defaultContext);"
	)
	lines.append("")
	lines.append("/**")
	lines.append(" * Translation hook. Falls back to the English catalog when a key is")
	lines.append(" * missing from the active locale — keeps a partially-translated app")
	lines.append(" * usable while the host fills the gaps. The return type is `string`")
	lines.append(" * so call-sites can render directly inside JSX without narrowing.")
	lines.append(" */")
	lines.append("export function useT(): (key: TranslationKey) => string {")
	lines.append(f"{tab}const ctx = React.useContext(I18nContext);")
	lines.append(f"{tab}return React.useCallback(")
	lines.append(f"{tab}{tab}(key: TranslationKey): string => {{")
	lines.append(f"{tab}{tab}{tab}const value = ctx.catalog[key];")
	lines.append(f'{tab}{tab}{tab}if (value != null && value !== "") return value;')
	lines.append(f"{tab}{tab}{tab}const fallback = (enCatalog as TranslationCatalog)[key];")
	lines.append(f"{tab}{tab}{tab}return fallback ?? key;")
	lines.append(f"{tab}{tab}}},")
	lines.append(f"{tab}{tab}[ctx],")
	lines.append(f"{tab});")
	lines.append("}")
	lines.append("")
	return newline.join(lines)


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the i18n catalogs + useT() hook for *bundle*.

	Output paths:

	* ``frontend/src/<pkg>/i18n/<lang>.json`` — one per declared language
	  (English populated; others structurally identical with empty values).
	* ``frontend/src/<pkg>/i18n/useT.ts`` — type-safe hook + context shim.

	Per-bundle aggregation: one ``useT.ts`` per bundle regardless of
	how many JTBDs the bundle declares.
	"""

	assert isinstance(bundle, NormalizedBundle), "bundle must be NormalizedBundle"
	pkg = bundle.project.package
	languages = bundle.project.languages or _DEFAULT_LANGUAGES
	english = english_catalog(bundle)
	files: list[GeneratedFile] = []
	for lang in languages:
		payload = english if lang == languages[0] else empty_mirror(english)
		files.append(
			GeneratedFile(
				path=f"frontend/src/{pkg}/i18n/{lang}.json",
				content=_emit_json(payload),
			)
		)
	files.append(
		GeneratedFile(
			path=f"frontend/src/{pkg}/i18n/useT.ts",
			content=_render_useT(bundle, english),
		)
	)
	return files


__all__ = [
	"CONSUMES",
	"empty_mirror",
	"english_catalog",
	"generate",
	"humanize_event",
	"humanize_topic",
]
