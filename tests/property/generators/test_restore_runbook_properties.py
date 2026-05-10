"""Property test: ``restore_runbook`` generator (W2 / item 7).

Per-bundle restore runbook at ``docs/ops/<package>/restore-runbook.md``.
Property: determinism plus path/content stability (the runbook lists
the bundle's tables — every JTBD's table_name appears at least once).
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import restore_runbook

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("restore_runbook")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_restore_runbook_is_deterministic(b) -> None:
	a = restore_runbook.generate(b)
	c = restore_runbook.generate(b)
	assert a == c, "restore_runbook regen drift"
	assert a.path == f"docs/ops/{b.project.package}/restore-runbook.md", a.path
	for jt in b.jtbds:
		assert jt.table_name in a.content, f"missing table {jt.table_name}"
