"""Property test: ``operator_manual`` generator (W4b / item 20).

Per-JTBD MDX manual. Property: determinism plus path/content anchors
that must stay tied to the JTBD id and authored title.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import operator_manual

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("operator_manual")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_operator_manual_is_deterministic(b) -> None:
	for jt in b.jtbds:
		a = operator_manual.generate(b, jt)
		c = operator_manual.generate(b, jt)
		assert a == c, "operator_manual regen drift"
		assert a.path == f"docs/jtbd/{jt.id}.mdx", a.path
		assert jt.title in a.content
		assert f"workflows/{jt.id}/diagram.mmd" in a.content
