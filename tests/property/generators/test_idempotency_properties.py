"""Property test: ``idempotency`` generator (W2 / item 6).

Per-JTBD router-level idempotency helper. Property: determinism plus
the documented TTL fallback (no override → ``IDEMPOTENCY_TTL_HOURS = 24``
appears in the emitted source).
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import idempotency

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("idempotency")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_idempotency_is_deterministic(b) -> None:
	for jt in b.jtbds:
		a = idempotency.generate(b, jt)
		c = idempotency.generate(b, jt)
		assert a == c, "idempotency regen drift"
		assert a.path.endswith(f"{jt.module_name}/idempotency.py"), a.path
		assert "IDEMPOTENCY_TTL_HOURS" in a.content
		assert "24" in a.content, "default 24h TTL should appear in source"
