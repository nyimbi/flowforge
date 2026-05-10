"""Property test: ``migration_safety`` generator (W0 / item 1).

Per-bundle generator emitting safety reports per migration. The
property: regenerating against the same bundle returns the same set of
file paths and bytes. Pinned seed = ``int(sha256("migration_safety")[:8], 16)``.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import migration_safety

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("migration_safety")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_migration_safety_is_deterministic(b) -> None:
	"""Two regens of ``migration_safety`` produce identical files."""

	a = list(migration_safety.generate(b) or [])
	c = list(migration_safety.generate(b) or [])
	assert a == c, "migration_safety regen drift"
	for f in a:
		assert f.path.startswith("backend/migrations/safety/"), f.path
		assert f.content, f"empty safety report: {f.path}"
