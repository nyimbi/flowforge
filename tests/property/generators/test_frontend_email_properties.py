"""Property test: ``frontend_email`` generator (W3 / item 9).

Per-bundle email-driven adapter shell at ``frontend-email/<package>/``.
Property: determinism plus a non-empty emission floor scoped to the
package tree.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import frontend_email

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("frontend_email")


@settings(
	derandomize=True,
	max_examples=30,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_frontend_email_is_deterministic(b) -> None:
	a = list(frontend_email.generate(b))
	c = list(frontend_email.generate(b))
	assert a == c, "frontend_email regen drift"
	assert a, "frontend_email emitted no files"
	for f in a:
		assert f.path.startswith(f"frontend-email/{b.project.package}/"), f.path
