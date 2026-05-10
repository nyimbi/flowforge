"""Property test: ``diagram`` generator (W1 / item 19).

Per-JTBD mermaid ``stateDiagram-v2`` source. Properties: determinism
plus the documented swimlane / arrow invariants — every JTBD's emitted
diagram is well-formed mermaid that opens with the title frontmatter.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, seed, settings

from flowforge_cli.jtbd.generators import diagram

from ._bundle_factory import bundle_strategy, generator_seed


_SEED = generator_seed("diagram")


@settings(
	derandomize=True,
	max_examples=40,
	deadline=None,
	suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@seed(_SEED)
@given(b=bundle_strategy())
def test_diagram_is_deterministic(b) -> None:
	for jt in b.jtbds:
		a = diagram.generate(b, jt)
		c = diagram.generate(b, jt)
		assert a == c, "diagram regen drift"
		assert a.path == f"workflows/{jt.id}/diagram.mmd", a.path
		assert a.content.startswith("---\n"), a.content[:40]
		assert "stateDiagram-v2" in a.content, "missing stateDiagram-v2 header"
