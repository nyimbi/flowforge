"""W4a / item 3 retrofit — per-generator hypothesis property suite.

Each ``test_<generator>_properties.py`` covers one generator from W0-W3
with at least one hypothesis-driven property. The properties cover the
generator's *generation-time* contract (determinism, output schema,
path stability); per-JTBD *runtime* properties are emitted by the W4a
``property_tests`` generator into ``backend/tests/<jtbd>/`` of each
generated app.

Pinned seed contract (mirrors ADR-003 for emitted suites): every test
module pins its own ``@hypothesis.seed(N)`` at module scope so
counter-examples reproduce byte-for-byte across hosts. The seed value
is the leading 8 hex chars of ``sha256(generator_name)`` decoded as a
32-bit int, computed and rendered as a literal in each file.
"""
