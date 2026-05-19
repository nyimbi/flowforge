"""Property test: ``i18n`` generator (W4b / item 17).

Per-bundle catalogs plus the type-safe ``useT`` hook. Property:
determinism plus closed catalog shape.
"""

from __future__ import annotations

import json

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import i18n

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("i18n")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_i18n_is_deterministic(b) -> None:
	a = list(i18n.generate(b))
	c = list(i18n.generate(b))
	assert a == c, "i18n regen drift"
	paths = {f.path for f in a}
	assert f"frontend/src/{b.project.package}/i18n/en.json" in paths
	assert f"frontend/src/{b.project.package}/i18n/useT.ts" in paths
	en = next(f for f in a if f.path.endswith("/i18n/en.json"))
	catalog = json.loads(en.content)
	assert catalog, "English catalog should not be empty"
	for jt in b.jtbds:
		assert catalog[f"jtbd.{jt.id}.title"] == jt.title
