"""Property test: ``frontend_admin`` generator (W2 / item 15).

Per-bundle tenant-scoped admin console (React tree under
``frontend-admin/<pkg>/``). Property: determinism plus a non-empty
emission floor.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import frontend_admin

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("frontend_admin")


@settings(
	derandomize=True,
	max_examples=30,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_frontend_admin_is_deterministic(b) -> None:
	a = list(frontend_admin.generate(b))
	c = list(frontend_admin.generate(b))
	assert a == c, "frontend_admin regen drift"
	assert a, "frontend_admin emitted no files"
	for f in a:
		assert f.path.startswith(f"frontend-admin/{b.project.package}/"), f.path
		assert f.content, f"empty admin file: {f.path}"
