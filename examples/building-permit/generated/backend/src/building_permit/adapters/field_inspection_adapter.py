"""Workflow adapter for Conduct Field Inspection.

Wraps :func:`flowforge.engine.fire.fire` for the ``field_inspection`` workflow.
The host service constructs an instance, then calls :func:`fire_event`
with each user/system event.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import FireResult, fire as _fire, new_instance
from flowforge.ports.types import Principal


WORKFLOW_KEY = "field_inspection"
_DEF_PATH = Path(__file__).resolve().parents[3] / "workflows" / WORKFLOW_KEY / "definition.json"


def load_definition() -> WorkflowDef:
	"""Read + parse the JSON DSL definition once per import."""

	raw = json.loads(_DEF_PATH.read_text(encoding="utf-8"))
	return WorkflowDef.model_validate(raw)


_DEF: WorkflowDef | None = None


def _definition() -> WorkflowDef:
	global _DEF
	if _DEF is None:
		_DEF = load_definition()
	return _DEF


async def fire_event(
	event: str,
	*,
	payload: dict[str, Any] | None = None,
	principal: Principal,
	tenant_id: str = "default",
) -> FireResult:
	"""Fire one event against a fresh instance (testing default).

	Production callers replace this shim with a snapshot-store-backed
	instance lookup; the signature stays stable.
	"""

	wd = _definition()
	instance = new_instance(wd)
	return await _fire(
		wd,
		instance,
		event,
		payload=payload or {},
		principal=principal,
		tenant_id=tenant_id,
	)
