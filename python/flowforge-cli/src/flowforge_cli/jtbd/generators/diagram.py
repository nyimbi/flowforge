"""Per-JTBD generator: mermaid state-diagram source.

W1 / item 19. Emits ``workflows/<jtbd>/diagram.mmd`` — the mermaid
``stateDiagram-v2`` source for the synthesised state machine. The
generator deliberately does **not** invoke ``mermaid-cli`` to render
SVG; pre-rendered SVG bytes are non-deterministic across mermaid-cli
versions and would break the byte-identical regen contract (Principle 1
of :doc:`docs/v0.3.0-engineering-plan`). Hosts that want SVG / PNG
output run ``mmdc -i workflows/<id>/diagram.mmd -o diagram.svg``
themselves on the deterministic ``.mmd`` source.

Encoding choices (all byte-stable):

* **Swimlanes**: each state's ``swimlane`` (actor role) maps to a
  ``classDef swimlane_<role>`` whose colour is picked from a fixed
  palette by the role's position in the sorted-unique-swimlane list.
* **Terminal kinds**: ``terminal_success`` is green, ``terminal_fail``
  is red. The synthesised ``compensated`` state (declared
  ``terminal_fail`` by the engine) is overridden to a distinct
  ``compensation`` blue-dashed class so the compensation lane reads as
  separate from a regular reject.
* **Edge-case priority**: every transition's label carries a priority
  glyph plus ``(P<priority>)`` — solid (●) for priority 0, dashed (┄)
  for 5..9, dotted (┈) for 10+, and a blue saga marker (⤺) for
  compensate transitions. Mermaid's ``stateDiagram-v2`` parser doesn't
  accept the ``linkStyle`` directive (flowcharts only), so the visual
  differentiation is conveyed entirely through the label glyph + the
  parenthesised priority — both render in any mermaid renderer.
* **SLA budgets**: when ``jtbd.sla_breach_seconds`` is set and a
  ``review`` state exists, a ``note right of review`` annotation is
  emitted with the budget formatted in the largest whole-unit string
  (24h, 7d, 30m, …).

Determinism guarantees:

* Transitions sorted by ``(priority, id)`` before emission.
* Class assignments sorted by state name.
* Terminal-exit arrows sorted by terminal-state name.
* ``classDef`` declarations sorted by class name.
* No timestamp, no random ids.

Two regens against the same bundle produce byte-identical ``.mmd``
output, so ``scripts/check_all.sh`` step 8 stays green.
"""

from __future__ import annotations

from typing import Any

from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Fixture-registry primer (executor residual risk #2 in the v0.3.0
# engineering plan). Mirrors the entry in ``_fixture_registry._REGISTRY``;
# the fixture-coverage test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].sla_breach_seconds",
	"jtbds[].states",
	"jtbds[].title",
	"jtbds[].transitions",
)


# ---------------------------------------------------------------------------
# palettes (frozen so the output is byte-stable across runs)
# ---------------------------------------------------------------------------


# Swimlane colours: (fill, stroke, text-colour). The palette has 8 slots so
# typical bundles with 3-5 actor roles never wrap; if a bundle ever needs
# more than 8 we wrap by sorted-position so the assignment is still
# deterministic.
_SWIMLANE_PALETTE: tuple[tuple[str, str, str], ...] = (
	("#e0f2fe", "#0284c7", "#0c4a6e"),  # sky
	("#fef3c7", "#d97706", "#78350f"),  # amber
	("#fce7f3", "#be185d", "#831843"),  # pink
	("#dcfce7", "#16a34a", "#14532d"),  # emerald
	("#ede9fe", "#7c3aed", "#4c1d95"),  # violet
	("#f5d0fe", "#a21caf", "#701a75"),  # fuchsia
	("#cffafe", "#0891b2", "#164e63"),  # cyan
	("#fed7aa", "#ea580c", "#7c2d12"),  # orange
)


# Terminal kinds: green for success, red for fail. The compensation lane
# uses a distinct blue dashed treatment so a saga rollback reads
# differently from a hard reject even though both are ``terminal_fail`` to
# the engine.
_TERMINAL_STYLES: dict[str, tuple[str, str, str]] = {
	"terminal_success": ("#dcfce7", "#16a34a", "#14532d"),
	"terminal_fail": ("#fee2e2", "#dc2626", "#7f1d1d"),
}


_COMPENSATION_STYLE: tuple[str, str, str] = ("#dbeafe", "#2563eb", "#1e3a8a")


# Per-priority glyph rendered into the transition label. Mermaid's
# ``stateDiagram-v2`` parser rejects ``linkStyle`` (flowcharts only) so
# the priority signal lives in the label itself.
#   * priority 0   → ``●``  solid bullet ("happy path")
#   * priority 5+  → ``┄``  dashed glyph ("edge case")
#   * priority 10+ → ``┈``  dotted glyph ("escalation")
#   * compensate   → ``⤺``  curve-back ("saga rollback")
_GLYPH_HAPPY = "●"
_GLYPH_EDGE = "┄"
_GLYPH_ESCALATE = "┈"
_GLYPH_COMPENSATE = "⤺"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _swimlane_class(swimlane: str) -> str:
	"""Stable, mermaid-safe class identifier for a swimlane string."""

	assert isinstance(swimlane, str), "swimlane must be a string"
	safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in swimlane)
	return f"swimlane_{safe or 'default'}"


def _format_sla(seconds: int) -> str:
	"""Render a budget in a human-readable string.

	Prefers hours over days because that's how the v0.3.0 engineering plan
	worked-example annotates it (``review (24h SLA)`` for ``86400``s).
	Days are not introduced as a unit so a 24h budget reads as ``24h
	SLA`` rather than ``1d SLA`` — pre-existing operator dashboards key
	off the hour count and the unit difference would silently mask
	regressions.
	"""

	assert isinstance(seconds, int), "seconds must be an int"
	if seconds <= 0:
		return f"{seconds}s SLA"
	if seconds % 3600 == 0:
		return f"{seconds // 3600}h SLA"
	if seconds % 60 == 0:
		return f"{seconds // 60}m SLA"
	return f"{seconds}s SLA"


def _guard_var(transition: dict[str, Any]) -> str | None:
	"""Return the first ``context.<name>`` variable read by *transition*'s guard.

	The synthesiser only ever emits ``{kind: "expr", expr: {var: ...}}``
	guards (cross-runtime parity invariant 5), so the first hit is also
	the only hit. Returns ``None`` for ungated transitions.
	"""

	for g in transition.get("guards") or ():
		if g.get("kind") == "expr":
			expr = g.get("expr") or {}
			v = expr.get("var")
			if v:
				return str(v)
	return None


# ---------------------------------------------------------------------------
# public api
# ---------------------------------------------------------------------------


def build_mmd(_bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> str:
	"""Build the mermaid ``stateDiagram-v2`` source for *jtbd*.

	Pure function: same input → same output. The ``_bundle`` argument is
	currently unused but kept (with a leading underscore, per PEP 8) so
	the helper signature matches the per-JTBD generator contract — and so
	cross-bundle context (design tokens, theming) can layer in later
	without a signature break.
	"""

	# Sort transitions by (priority, id) so the line ordering survives any
	# upstream reordering in ``derive_transitions``.
	transitions = sorted(
		[dict(t) for t in jtbd.transitions],
		key=lambda t: (int(t.get("priority", 0)), str(t.get("id", ""))),
	)

	# Swimlanes referenced by any state, sorted unique.
	swimlanes = sorted({s["swimlane"] for s in jtbd.states if "swimlane" in s})

	# Terminal kinds referenced by any state, sorted unique.
	terminal_kinds = sorted(
		{s["kind"] for s in jtbd.states if s["kind"] in _TERMINAL_STYLES}
	)

	# Compensation lane present? Only emit the ``compensation`` classDef
	# when at least one transition uses event ``compensate``.
	has_compensation = any(t.get("event") == "compensate" for t in transitions)

	state_kind = {s["name"]: s["kind"] for s in jtbd.states}
	state_swimlane: dict[str, str | None] = {
		s["name"]: s.get("swimlane") for s in jtbd.states
	}
	terminal_state_names = sorted(
		s["name"]
		for s in jtbd.states
		if s["kind"] in {"terminal_success", "terminal_fail"}
	)

	lines: list[str] = []
	lines.append("---")
	lines.append(f"title: {jtbd.id} — {jtbd.title}")
	lines.append("---")
	lines.append("stateDiagram-v2")
	# Direction is fixed for byte-stability across mermaid versions; LR
	# reads naturally for these workflow shapes.
	lines.append("\tdirection LR")
	lines.append("")

	# 1) classDef declarations -------------------------------------------------
	for idx, sw in enumerate(swimlanes):
		fill, stroke, text = _SWIMLANE_PALETTE[idx % len(_SWIMLANE_PALETTE)]
		cls = _swimlane_class(sw)
		lines.append(
			f"\tclassDef {cls} fill:{fill},stroke:{stroke},color:{text},stroke-width:1px"
		)
	for kind in terminal_kinds:
		fill, stroke, text = _TERMINAL_STYLES[kind]
		lines.append(
			f"\tclassDef {kind} fill:{fill},stroke:{stroke},color:{text},stroke-width:2px"
		)
	if has_compensation:
		fill, stroke, text = _COMPENSATION_STYLE
		lines.append(
			f"\tclassDef compensation fill:{fill},stroke:{stroke},color:{text},stroke-width:2px,stroke-dasharray:4 2"
		)
	lines.append("")

	# 2) Arrows -------------------------------------------------------------
	# Mermaid's stateDiagram-v2 parser does not accept ``linkStyle`` —
	# that directive is flowchart-only. Priority differentiation lives in
	# the label itself: a leading glyph (●/┄/┈/⤺) plus a ``(P<n>)`` tag.

	# 2a) initial-state arrow
	lines.append(f"\t[*] --> {jtbd.initial_state}")

	# 2b) workflow transitions, sorted (priority, id)
	for t in transitions:
		event = str(t.get("event", ""))
		prio = int(t.get("priority", 0))
		gv = _guard_var(t)
		guard_tag = f" [{gv}]" if gv else ""
		if event == "compensate":
			glyph = _GLYPH_COMPENSATE
		elif prio >= 10:
			glyph = _GLYPH_ESCALATE
		elif prio >= 5:
			glyph = _GLYPH_EDGE
		else:
			glyph = _GLYPH_HAPPY
		label = f"{glyph} {event}{guard_tag} (P{prio})"
		lines.append(f"\t{t['from_state']} --> {t['to_state']} : {label}")

	# 2c) terminal-exit arrows, sorted by state name
	for term in terminal_state_names:
		lines.append(f"\t{term} --> [*]")
	lines.append("")

	# 3) SLA annotation -------------------------------------------------------
	# Anchor on the canonical long-running ``review`` state (the central
	# wait point in every synthesised flow). If a future bundle shape adds
	# a different long-running state, this is the spot to extend.
	if jtbd.sla_breach_seconds and any(s["name"] == "review" for s in jtbd.states):
		lines.append("\tnote right of review")
		lines.append(f"\t\t{_format_sla(int(jtbd.sla_breach_seconds))}")
		lines.append("\tend note")
		lines.append("")

	# 4) class assignments ----------------------------------------------------
	# Swimlane class first (sorted by state name), then terminal kind /
	# compensation override last so the compensation styling wins on the
	# ``compensated`` state.
	for state_name in sorted(state_swimlane.keys()):
		sw = state_swimlane[state_name]
		if sw is not None:
			lines.append(f"\tclass {state_name} {_swimlane_class(sw)}")
	for state_name in terminal_state_names:
		if state_name == "compensated" and has_compensation:
			lines.append(f"\tclass {state_name} compensation")
		else:
			lines.append(f"\tclass {state_name} {state_kind[state_name]}")

	# Trailing newline keeps the file POSIX-friendly and ``cat``-safe.
	return "\n".join(lines) + "\n"


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	"""Emit ``workflows/<jtbd>/diagram.mmd`` (mermaid source).

	No SVG is rendered: pre-rendered SVG bytes are non-deterministic
	across mermaid-cli versions and would break Principle 1 (determinism).
	Hosts that want raster output run ``mmdc`` themselves on the ``.mmd``
	source — that keeps the generation pipeline's hash-input stable.
	"""

	content = build_mmd(bundle, jtbd)
	return GeneratedFile(
		path=f"workflows/{jtbd.id}/diagram.mmd",
		content=content,
	)
