"""Property test: ``lineage`` generator (W3 / item 11).

Per-bundle data-lineage / provenance graph at ``lineage.json``.
Property: determinism plus JSON validity + each JTBD id appearing at
least once in the emitted graph.
"""

from __future__ import annotations

import json

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import lineage

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("lineage")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_lineage_is_deterministic(b) -> None:
	a = lineage.generate(b)
	c = lineage.generate(b)
	assert a == c, "lineage regen drift"
	assert a.path == "lineage.json", a.path
	parsed = json.loads(a.content)
	assert isinstance(parsed, dict), "lineage.json must be an object"
	# Every JTBD id must appear somewhere in the serialised graph (
	# either as a key, a stage value, or a node id).
	dumped = json.dumps(parsed)
	for jt in b.jtbds:
		assert jt.id in dumped, f"lineage graph missing JTBD {jt.id}"
