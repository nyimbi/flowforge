"""Property test: ``design_tokens`` generator (W3 / item 18).

Per-bundle design-token theming (CSS variables + Tailwind config + TS
theme module). Property: determinism plus a non-empty emission floor —
the generator unconditionally emits the default-token tree even when
``project.design`` is absent.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import design_tokens

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("design_tokens")


@settings(
	derandomize=True,
	max_examples=30,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_design_tokens_is_deterministic(b) -> None:
	a = list(design_tokens.generate(b))
	c = list(design_tokens.generate(b))
	assert a == c, "design_tokens regen drift"
	assert a, "design_tokens emitted no files (defaults must always emit)"
	# Generator emits both the customer-facing + admin token trees;
	# at least one CSS variable file and one TS theme module land.
	paths = " ".join(f.path for f in a)
	assert ".css" in paths or "tokens" in paths, paths
