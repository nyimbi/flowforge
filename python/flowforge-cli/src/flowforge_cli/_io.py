"""Small IO helpers — JTBD/workflow file loading shared by commands.

Kept private (underscore-prefixed) so the surface stays the typer commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_structured(path: Path) -> dict[str, Any]:
	"""Load a JSON or YAML file into a plain Python dict.

	YAML support is optional — we import :mod:`yaml` lazily so a missing
	``pyyaml`` install only breaks YAML callers, never JSON ones. Pure
	JSON paths short-circuit before importing yaml at all.
	"""

	assert path is not None, "path is required"
	suffix = path.suffix.lower()
	text = path.read_text(encoding="utf-8")
	if suffix in (".json", ".jsonc"):
		data = json.loads(text)
	elif suffix in (".yaml", ".yml"):
		try:
			import yaml  # type: ignore[import-untyped]
		except ModuleNotFoundError as exc:  # pragma: no cover - dep is required
			raise RuntimeError(
				f"YAML input requires pyyaml; install flowforge-cli with full deps. ({exc})"
			) from exc
		data = yaml.safe_load(text)
	else:
		# Best effort — treat unknown suffix as JSON first, then YAML.
		try:
			data = json.loads(text)
		except json.JSONDecodeError:
			import yaml  # type: ignore[import-untyped]

			data = yaml.safe_load(text)
	if not isinstance(data, dict):
		raise ValueError(f"{path}: expected a mapping at the top level, got {type(data).__name__}")
	return data


def write_json(path: Path, data: Any) -> None:
	"""Write *data* as deterministic JSON (sorted keys, 2-space indent, trailing newline)."""

	assert path is not None
	path.parent.mkdir(parents=True, exist_ok=True)
	payload = json.dumps(data, indent=2, sort_keys=True)
	path.write_text(payload + "\n", encoding="utf-8")


def discover_workflow_defs(root: Path) -> list[Path]:
	"""Return every ``definition.json`` under ``root`` in deterministic order."""

	assert root is not None
	if not root.exists():
		return []
	return sorted(root.rglob("definition.json"))
