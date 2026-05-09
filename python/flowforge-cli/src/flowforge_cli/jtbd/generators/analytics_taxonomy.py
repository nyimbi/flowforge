"""Per-bundle generator: closed analytics-event taxonomy.

Item 16 of :doc:`docs/improvements`, W2 sub-batch 2b of
:doc:`docs/v0.3.0-engineering-plan`. Emits two parallel artifacts that
enumerate every analytics event the bundle's JTBD step components may
fire, locked to the same closed taxonomy on both sides of the wire:

* ``backend/src/<pkg>/analytics.py`` — Python ``StrEnum`` of every
  ``<jtbd_id>.<lifecycle>`` event. Hosts wire ``flowforge.ports.analytics.AnalyticsPort``
  to a real provider (Segment / Mixpanel / Amplitude / a noop sink);
  the StrEnum is what the generated server-side code references.
* ``frontend/src/<pkg>/analytics.ts`` — TypeScript string-literal type
  derived from the same set, so Step.tsx's lifecycle hooks can be
  type-checked against the closed enum at compile time.

Lifecycle suffixes are fixed and identical across runtimes (per-bundle
aggregation per Principle 2 of the v0.3.0 engineering plan).

The fixture-registry primer at :mod:`._fixture_registry` records the
attribute paths this generator reads; the bidirectional coverage test
(Pre-mortem Scenario 1) cross-checks generator and registry.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].id",
	"project.name",
	"project.package",
)


# Closed lifecycle suffix list. Adding an entry here is a taxonomy
# expansion: it lands in both the Python StrEnum and the TS literal
# union and downstream dashboards must be updated. Removal is breaking
# (closed enums are append-only between minor versions).
LIFECYCLE_SUFFIXES: tuple[str, ...] = (
	"field_focused",
	"field_completed",
	"validation_failed",
	"submission_started",
	"submission_succeeded",
	"form_abandoned",
)


def _events_for_bundle(bundle: NormalizedBundle) -> tuple[tuple[str, str], ...]:
	"""Return ``(member_name, event_name)`` pairs sorted for stable emission.

	* ``member_name`` is the upper-snake key used as the StrEnum / TS
	  const member identifier.
	* ``event_name`` is the dotted ``<jtbd_id>.<suffix>`` string that
	  the analytics provider sees.
	"""

	pairs: list[tuple[str, str]] = []
	# Sort JTBDs by id; suffix order is fixed by ``LIFECYCLE_SUFFIXES``.
	# Together this gives a deterministic emission order independent of
	# bundle declaration order.
	for jt in sorted(bundle.jtbds, key=lambda j: j.id):
		for suffix in LIFECYCLE_SUFFIXES:
			member = f"{jt.id}_{suffix}".upper()
			event = f"{jt.id}.{suffix}"
			pairs.append((member, event))
	return tuple(pairs)


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the bundle-level analytics taxonomy pair.

	Two files, regardless of how many JTBDs the bundle declares — per
	Principle 2 of the v0.3.0 engineering plan (per-bundle generators
	must be aggregations).
	"""

	pairs = _events_for_bundle(bundle)
	py = render(
		"analytics_taxonomy.py.j2",
		project=bundle.project,
		bundle=bundle,
		events=pairs,
	)
	ts = render(
		"analytics_taxonomy.ts.j2",
		project=bundle.project,
		bundle=bundle,
		events=pairs,
	)
	return [
		GeneratedFile(
			path=f"backend/src/{bundle.project.package}/analytics.py",
			content=py,
		),
		GeneratedFile(
			path=f"frontend/src/{bundle.project.package}/analytics.ts",
			content=ts,
		),
	]
