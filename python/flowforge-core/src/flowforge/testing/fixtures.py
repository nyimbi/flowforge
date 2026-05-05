"""Pytest helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..dsl import WorkflowDef


def load_def(path: str | Path) -> WorkflowDef:
	"""Read a JSON file and parse into :class:`WorkflowDef`."""
	p = Path(path)
	data: dict[str, Any] = json.loads(p.read_text())
	return WorkflowDef.model_validate(data)
