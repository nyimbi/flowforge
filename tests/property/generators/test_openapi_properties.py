"""Property test: ``openapi`` generator (W1 / item 8).

Bundle-derived OpenAPI 3.1 spec at ``openapi.yaml``. Property:
determinism plus a structural minimum (the emitted YAML contains
``openapi:`` and at least one operation tag per JTBD).
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import openapi

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("openapi")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_openapi_is_deterministic(b) -> None:
	a = openapi.generate(b)
	c = openapi.generate(b)
	assert a == c, "openapi regen drift"
	assert a.path == "openapi.yaml", a.path
	# YAML keys are sorted, so the document doesn't start with ``openapi:`` —
	# but the OpenAPI 3.1 spec marker is always present.
	assert "openapi: 3.1" in a.content, a.content[:200]
	for jt in b.jtbds:
		assert jt.id in a.content, f"openapi missing tag for {jt.id}"
