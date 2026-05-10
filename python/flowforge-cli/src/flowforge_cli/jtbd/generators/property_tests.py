"""Per-JTBD generator: hypothesis property suite.

W4a / item 3 of :doc:`docs/improvements`. Emits
``backend/tests/<jtbd>/test_<jtbd>_properties.py`` per JTBD — a hypothesis
property bank that explores the synthesised state machine and asserts
the four invariants documented in ADR-003:

1. Any legal event sequence terminates in a known workflow state.
2. The simulator's audit chain stays monotonic.
3. Every fire commits effects atomically or no-ops cleanly.
4. No orphan entities (every created entity is paired with a fired
   ``create_entity`` effect).

The pinned seed contract (ADR-003): every emitted file pins
``@settings(seed=N, derandomize=True, max_examples=200)`` where
``N = int(sha256(jtbd_id)[:8], 16)``. The seed is computed *here* at
generation time and rendered as a literal int in the source so it shows
up under grep + so the test runs the same input space on every host.

Hypothesis is pinned to ``>=6.100,<7.0`` in the ``flowforge-cli``
project metadata; cross-version shrink-behaviour drift is the dominant
remaining non-determinism source for property tests.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].module_name",
	"jtbds[].states",
	"jtbds[].transitions",
)


# Per ADR-003 — the seed is the leading 8 hex chars of sha256(jtbd_id),
# decoded as a 32-bit int. Stable across hosts, distinct per JTBD,
# unaffected by file/test renames.
def compute_seed(jtbd_id: str) -> int:
	"""Return the ADR-003 pinned seed for *jtbd_id* (32-bit int)."""

	assert isinstance(jtbd_id, str) and jtbd_id, "jtbd_id must be a non-empty string"
	digest = hashlib.sha256(jtbd_id.encode("utf-8")).hexdigest()
	return int(digest[:8], 16)


def compute_seed_hex(jtbd_id: str) -> str:
	"""Return the lowercase 8-char hex form of :func:`compute_seed`."""

	assert isinstance(jtbd_id, str) and jtbd_id, "jtbd_id must be a non-empty string"
	return hashlib.sha256(jtbd_id.encode("utf-8")).hexdigest()[:8]


def _extract_guard_vars(transitions: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
	"""Collect the per-transition ``context.<name>`` guard suffixes.

	The synthesiser only ever emits ``{kind: "expr", expr: {var: "context.<x>"}}``
	guards (cross-runtime parity invariant 5), so we strip the ``context.``
	prefix and keep ``<x>`` for the strategy. Sorted, deduplicated; empty
	tuple when the JTBD has no guarded transitions.
	"""

	out: set[str] = set()
	for t in transitions:
		for g in t.get("guards") or ():
			if g.get("kind") != "expr":
				continue
			expr = g.get("expr") or {}
			var = expr.get("var")
			if not isinstance(var, str):
				continue
			# Only handle the canonical ``context.<name>`` shape; anything
			# else is left out of the strategy so the test stays focused.
			if var.startswith("context."):
				suffix = var[len("context.") :]
				if suffix:
					out.add(suffix)
	return tuple(sorted(out))


def _extract_workflow_events(transitions: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
	"""Sorted, deduplicated event names declared on any transition."""

	events: set[str] = set()
	for t in transitions:
		ev = t.get("event")
		if isinstance(ev, str) and ev:
			events.add(ev)
	return tuple(sorted(events))


def _extract_states(jtbd: NormalizedJTBD) -> tuple[tuple[str, ...], tuple[str, ...]]:
	"""Return ``(all_states_sorted, terminal_states_sorted)``.

	Both sorted by name for byte-stable rendering.
	"""

	all_names = sorted(s["name"] for s in jtbd.states)
	terminals = sorted(
		s["name"]
		for s in jtbd.states
		if s.get("kind") in {"terminal_success", "terminal_fail"}
	)
	return tuple(all_names), tuple(terminals)


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	"""Emit the per-JTBD hypothesis property suite for *jtbd*."""

	pinned_seed = compute_seed(jtbd.id)
	pinned_seed_hex = compute_seed_hex(jtbd.id)
	all_states, terminal_states = _extract_states(jtbd)
	workflow_events = _extract_workflow_events(jtbd.transitions)
	guard_vars = _extract_guard_vars(jtbd.transitions)

	content = render(
		"tests/test_property.py.j2",
		project=bundle.project,
		jtbd=jtbd,
		pinned_seed=pinned_seed,
		pinned_seed_hex=pinned_seed_hex,
		all_states=all_states,
		terminal_states=terminal_states,
		workflow_events=workflow_events,
		guard_vars=guard_vars,
	)
	return GeneratedFile(
		path=f"backend/tests/{jtbd.module_name}/test_{jtbd.module_name}_properties.py",
		content=content,
	)
