"""Emit ``workflows/<jtbd>/definition.json`` (the JSON DSL workflow_def).

Pure data construction — no jinja, just deterministic dict building.
The output is validated against ``workflow_def.schema.json`` by the
generator tests.
"""

from __future__ import annotations

import json
from typing import Any

from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(_bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	wf: dict[str, Any] = {
		"key": jtbd.id,
		"version": "1.0.0",
		"subject_kind": jtbd.id,
		"initial_state": jtbd.initial_state,
		"metadata": {
			"generated_from": "jtbd",
			"title": jtbd.title,
			"actor": jtbd.actor_role,
		},
		"states": [dict(s) for s in jtbd.states],
		"transitions": [dict(t) for t in jtbd.transitions],
	}
	if jtbd.sla_breach_seconds is not None:
		wf["metadata"]["sla_breach_seconds"] = jtbd.sla_breach_seconds
	content = json.dumps(wf, indent=2, sort_keys=True) + "\n"
	return GeneratedFile(path=f"workflows/{jtbd.id}/definition.json", content=content)
