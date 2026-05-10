"""Property test: ``frontend_slack`` generator (W3 / item 9).

Per-bundle Slack adapter shell at ``frontend-slack/<package>/``.
Property: determinism plus a non-empty emission floor scoped to the
package tree.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import frontend_slack

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("frontend_slack")


@settings(
	derandomize=True,
	max_examples=30,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_frontend_slack_is_deterministic(b) -> None:
	a = list(frontend_slack.generate(b))
	c = list(frontend_slack.generate(b))
	assert a == c, "frontend_slack regen drift"
	assert a, "frontend_slack emitted no files"
	for f in a:
		assert f.path.startswith(f"frontend-slack/{b.project.package}/"), f.path
