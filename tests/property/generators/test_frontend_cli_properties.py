"""Property test: ``frontend_cli`` generator (W3 / item 9).

Per-bundle Typer CLI client at ``frontend-cli/<package>/``. Property:
determinism plus a non-empty emission floor scoped to the package tree.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import frontend_cli

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("frontend_cli")


@settings(
	derandomize=True,
	max_examples=30,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_frontend_cli_is_deterministic(b) -> None:
	a = list(frontend_cli.generate(b))
	c = list(frontend_cli.generate(b))
	assert a == c, "frontend_cli regen drift"
	assert a, "frontend_cli emitted no files"
	for f in a:
		assert f.path.startswith(f"frontend-cli/{b.project.package}/"), f.path
