"""Property test: ``analytics_taxonomy`` generator (W2 / item 16).

Per-bundle closed analytics-event taxonomy in Python + TypeScript.
Property: determinism plus both files present in the emitted list.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import analytics_taxonomy

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("analytics_taxonomy")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_analytics_taxonomy_is_deterministic(b) -> None:
	a = list(analytics_taxonomy.generate(b))
	c = list(analytics_taxonomy.generate(b))
	assert a == c, "analytics_taxonomy regen drift"
	paths = {f.path for f in a}
	# Both runtime siblings must land — Python enum + TS enum, per item 16.
	assert any(p.endswith("analytics.py") for p in paths), paths
	assert any(p.endswith("analytics.ts") for p in paths), paths
