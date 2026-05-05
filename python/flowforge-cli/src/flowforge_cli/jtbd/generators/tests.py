"""Emit a simulation pytest module per JTBD.

The generated test loads the workflow_def JSON, runs three canonical
events (``submit`` happy path; one edge_case branch if any; ``approve``
to terminal_success) and asserts state names. Importing flowforge is
all the test does — no DB, no FS, no network.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	# Pre-compute branch event names + target states for the template.
	branches: list[tuple[str, str]] = []
	for t in jtbd.transitions:
		# The "happy path" + edge transitions both fire on `submit` from
		# `intake`; we surface non-default-priority branches so the test
		# can exercise edge_cases without LLM input.
		if t["from_state"] == "intake" and t["priority"] > 0:
			branches.append((t["id"], t["to_state"]))

	content = render(
		"tests/test_simulation.py.j2",
		project=bundle.project,
		jtbd=jtbd,
		branches=branches,
	)
	return GeneratedFile(
		path=f"backend/tests/{jtbd.module_name}/test_simulation.py",
		content=content,
	)
