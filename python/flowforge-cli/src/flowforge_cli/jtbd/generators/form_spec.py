"""Emit ``workflows/<jtbd>/form_spec.json`` from JTBD ``data_capture``."""

from __future__ import annotations

import json
from typing import Any

from .. import transforms as T
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(_bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	fields: list[dict[str, Any]] = []
	for f in jtbd.fields:
		entry: dict[str, Any] = {
			"id": f.id,
			"kind": f.kind,
			"label": f.label,
			"required": f.required,
			"pii": f.pii,
		}
		if f.validation:
			entry["validation"] = dict(f.validation)
		fields.append(entry)

	# Always include at least one field so the schema's minItems holds —
	# JTBDs without data_capture get a single notes field.
	if not fields:
		fields.append(
			{
				"id": "notes",
				"kind": "textarea",
				"label": "Notes",
				"required": False,
				"pii": False,
			}
		)

	spec: dict[str, Any] = {
		"id": f"{jtbd.id}_intake",
		"version": "1.0.0",
		"title": f"{jtbd.title} — Intake",
		"fields": fields,
		"layout": [
			{
				"kind": "section",
				"title": "Details",
				"field_ids": [f["id"] for f in fields],
			}
		],
	}
	# Avoid an unused-import lint warning; T may be useful for future
	# layout heuristics keyed off field kinds.
	_ = T
	content = json.dumps(spec, indent=2, sort_keys=True) + "\n"
	return GeneratedFile(path=f"workflows/{jtbd.id}/form_spec.json", content=content)
