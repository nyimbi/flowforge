"""Shared NormalizedBundle factory + seed helper for W4a generator property tests.

The generators under ``flowforge_cli.jtbd.generators`` accept a
``NormalizedBundle`` (and, for per-JTBD generators, a ``NormalizedJTBD``)
and emit ``GeneratedFile`` records. The property tests in this directory
exercise that contract with hypothesis-driven variation: they shape a
small parsed-bundle dict, pipe it through the real parse + normalize
helpers, and hand the resulting NormalizedBundle to the generator under
test.

Two hypothesis strategies are exposed:

* :func:`bundle_strategy` — minimal bundle, one JTBD, baseline shape.
* :func:`compensating_bundle_strategy` — same baseline plus an
  ``edge_case`` declaring ``handle: "compensate"`` so generators that
  early-return on a non-compensating workflow (e.g. ``compensation_handlers``)
  actually exercise their emission path.

Determinism is the universal property: ``gen(b) == gen(b)`` for every
generator. Each test file pins its own ``@hypothesis.seed(N)`` so
counter-examples reproduce across hosts.
"""

from __future__ import annotations

import hashlib
from typing import Any

from hypothesis import strategies as st

from flowforge_cli.jtbd.normalize import NormalizedBundle, normalize
from flowforge_cli.jtbd.parse import parse_bundle


# Identifier alphabet that survives the generator's snake_case + pascal_case
# transforms without collapsing to empty. We prefix with a stable letter so
# hypothesis can't shrink into something that starts with a digit.
_ID_RAW = st.text(
	alphabet="abcdefghijklmnopqrstuvwxyz_",
	min_size=2,
	max_size=8,
).filter(lambda s: "__" not in s and not s.startswith("_") and not s.endswith("_"))

JTBD_ID_STRATEGY = _ID_RAW.map(lambda s: "j_" + s)
PACKAGE_STRATEGY = _ID_RAW.map(lambda s: "pkg_" + s)


def _baseline_jtbd(jid: str, *, with_compensate: bool = False) -> dict[str, Any]:
	"""Return the minimal-but-realistic JTBD dict the generators are happy with."""

	jtbd: dict[str, Any] = {
		"id": jid,
		"title": jid.replace("_", " ").title(),
		"actor": {"role": "applicant", "external": False},
		"situation": "demo situation",
		"motivation": "demo motivation",
		"outcome": "demo outcome",
		"success_criteria": ["demo criterion"],
		"data_capture": [
			{"id": "name", "kind": "text", "label": "Name", "required": True, "pii": True},
			{"id": "amount", "kind": "money", "label": "Amount", "required": False, "pii": False},
		],
		"edge_cases": [],
		"notifications": [
			{"trigger": "state_enter", "channel": "email", "audience": "applicant"},
		],
	}
	if with_compensate:
		jtbd["edge_cases"] = [
			{"id": "rollback", "condition": "needs rollback", "handle": "compensate"},
		]
	return jtbd


def _baseline_bundle(jid: str, pkg: str, *, with_compensate: bool = False) -> dict[str, Any]:
	return {
		"project": {
			"name": "demo",
			"package": pkg,
			"domain": "demo",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
			"frontend_framework": "nextjs",
		},
		"shared": {"roles": ["applicant", "reviewer"], "permissions": []},
		"jtbds": [_baseline_jtbd(jid, with_compensate=with_compensate)],
	}


@st.composite
def bundle_strategy(draw) -> NormalizedBundle:
	"""NormalizedBundle drawn from a hypothesis-shaped baseline."""

	jid = draw(JTBD_ID_STRATEGY)
	pkg = draw(PACKAGE_STRATEGY)
	raw = _baseline_bundle(jid, pkg)
	parse_bundle(raw)
	return normalize(raw)


@st.composite
def compensating_bundle_strategy(draw) -> NormalizedBundle:
	"""NormalizedBundle whose single JTBD declares a ``compensate`` edge_case."""

	jid = draw(JTBD_ID_STRATEGY)
	pkg = draw(PACKAGE_STRATEGY)
	raw = _baseline_bundle(jid, pkg, with_compensate=True)
	parse_bundle(raw)
	return normalize(raw)


def generator_seed(generator_name: str) -> int:
	"""Per-generator 32-bit hypothesis seed; mirrors ADR-003's per-JTBD pattern.

	Each retrofit test pins ``@hypothesis.seed(generator_seed("<name>"))``
	so the input space is reproducible across hosts.
	"""

	assert isinstance(generator_name, str) and generator_name
	return int(hashlib.sha256(generator_name.encode("utf-8")).hexdigest()[:8], 16)
