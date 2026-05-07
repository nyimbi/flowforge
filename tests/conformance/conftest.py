"""Pytest configuration for the audit-2026 architectural-invariant suite.

Markers are registered here so `make audit-2026-conformance-p0` can filter on
`@invariant_p0` without raising `PytestUnknownMarkWarning`. Each invariant
test in `test_arch_invariants.py` carries one of these markers + the audit
finding it covers; CI gates on the P0 set per audit-fix-plan §F-3 / R-3.
"""

from __future__ import annotations


def pytest_configure(config):
	config.addinivalue_line(
		"markers",
		"invariant_p0: P0 architectural invariant — required green on every PR (audit-fix-plan §F-3)",
	)
	config.addinivalue_line(
		"markers",
		"invariant_p1: P1 architectural invariant — required green by end of S1",
	)
	config.addinivalue_line(
		"markers",
		"placeholder: invariant scaffold — fixed by the named ticket (xfail strict)",
	)
