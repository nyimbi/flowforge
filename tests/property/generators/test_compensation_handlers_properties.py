"""Property test: ``compensation_handlers`` generator (W0 / item 2).

The generator returns ``None`` when the JTBD declares no ``compensate``
edge_case and a populated :class:`GeneratedFile` otherwise. The
property below covers both branches: the strategy alternates between a
compensating and non-compensating bundle so hypothesis exercises the
silent + emitting paths against the same deterministic helper code.

Pinned seed mirrors ADR-003: ``int(sha256("compensation_handlers")[:8], 16)``.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings, strategies as st

from flowforge_cli.jtbd.generators import compensation_handlers

from ._bundle_factory import (
	bundle_strategy,
	compensating_bundle_strategy,
	generator_seed,
)


_SEED = generator_seed("compensation_handlers")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=st.one_of(bundle_strategy(), compensating_bundle_strategy()))
def test_compensation_handlers_is_deterministic(b) -> None:
	"""``generate(b, jt) == generate(b, jt)`` — same NormalizedBundle, same bytes."""

	for jt in b.jtbds:
		a = compensation_handlers.generate(b, jt)
		c = compensation_handlers.generate(b, jt)
		assert a == c, "compensation_handlers regen drift"
		if a is None:
			# Non-compensating bundle: the silent-return path stays silent
			# in both invocations; nothing else to assert.
			continue
		assert a.path.endswith("/compensation_handlers.py"), a.path
		assert "compensate" in a.content.lower(), "compensation map missing"
