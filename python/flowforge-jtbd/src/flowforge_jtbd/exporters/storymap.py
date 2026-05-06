"""User-story-map exporter (E-21, reference).

Converts a :class:`~flowforge_jtbd.dsl.spec.JtbdSpec` to a user-story-map
JSON format compatible with tools like StoriesOnBoard, Jira Epic/Story
structure, or the open *USM* spec.

Output structure::

    {
      "epic": {
        "id": "<jtbd_id>",
        "title": "<title or id>",
        "situation": "...",
        "motivation": "...",
        "outcome": "..."
      },
      "stories": [
        {
          "id": "story_<field_id>",
          "title": "Capture <field_label>",
          "kind": "data_capture",
          "field_kind": "<text|money|...>",
          "pii": true/false,
          "acceptance_criteria": []
        },
        ...
        {
          "id": "story_approval_<role>",
          "title": "Approval: <role> (<policy>)",
          "kind": "approval",
          "acceptance_criteria": ["<success_criterion>", ...]
        }
      ],
      "edge_cases": [
        {"id": "...", "condition": "...", "handle": "..."},
        ...
      ]
    }
"""

from __future__ import annotations

import json
from typing import Any

from ..dsl.spec import JtbdBundle, JtbdSpec


class StorymapExporter:
	"""Exports a JtbdSpec to a user-story-map JSON string."""

	exporter_id = "storymap"

	def export(self, spec: JtbdSpec, bundle: JtbdBundle | None = None) -> str:
		"""Return a user-story-map JSON string."""
		stories: list[dict[str, Any]] = []

		for field in spec.data_capture:
			story: dict[str, Any] = {
				"id": f"story_{field.id}",
				"title": f"Capture {field.label or field.id}",
				"kind": "data_capture",
				"field_kind": field.kind,
				"pii": field.pii,
				"acceptance_criteria": [],
			}
			if field.sensitivity:
				story["sensitivity"] = list(field.sensitivity)
			stories.append(story)

		for i, approval in enumerate(spec.approvals):
			stories.append({
				"id": f"story_approval_{approval.role}_{i}",
				"title": f"Approval: {approval.role} ({approval.policy})",
				"kind": "approval",
				"acceptance_criteria": list(spec.success_criteria),
			})

		for criterion in spec.success_criteria:
			stories.append({
				"id": f"story_criterion_{len(stories)}",
				"title": criterion,
				"kind": "acceptance",
				"acceptance_criteria": [criterion],
			})

		output: dict[str, Any] = {
			"epic": {
				"id": spec.id,
				"title": spec.title or spec.id,
				"situation": spec.situation,
				"motivation": spec.motivation,
				"outcome": spec.outcome,
			},
			"stories": stories,
			"edge_cases": [
				{
					"id": ec.id,
					"condition": ec.condition,
					"handle": ec.handle,
					"branch_to": ec.branch_to,
				}
				for ec in spec.edge_cases
			],
		}

		return json.dumps(output, indent=2, sort_keys=False, ensure_ascii=False)


__all__ = ["StorymapExporter"]
