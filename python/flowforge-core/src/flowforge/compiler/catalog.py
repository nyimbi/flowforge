"""Entity-catalog projection.

A catalog summarises every entity referenced by a set of WorkflowDefs:
which subjects exist, which states they pass through, which permissions
gate their transitions. Hosts use this for navigation, RBAC seeding, and
designer auto-suggest.
"""

from __future__ import annotations

from typing import Any

from ..dsl import WorkflowDef
from ..ports.entity import EntityAdapter, EntityRegistry  # re-export for config

__all__ = ["EntityRegistry", "build_catalog"]


def build_catalog(defs: list[WorkflowDef]) -> dict[str, Any]:
	"""Return a JSON-serialisable catalog describing the workflows in *defs*."""

	subjects: dict[str, dict[str, Any]] = {}
	for wd in defs:
		entry = subjects.setdefault(
			wd.subject_kind,
			{"states": set(), "permissions": set(), "workflows": []},
		)
		entry["workflows"].append({"key": wd.key, "version": wd.version})
		for s in wd.states:
			entry["states"].add(s.name)
		for t in wd.transitions:
			for g in t.gates:
				if g.kind == "permission" and g.permission:
					entry["permissions"].add(g.permission)

	# Convert sets -> sorted lists for determinism
	for entry in subjects.values():
		entry["states"] = sorted(entry["states"])
		entry["permissions"] = sorted(entry["permissions"])

	return {"subjects": subjects}


# Make the registry importable from ``flowforge.compiler.catalog`` for
# config bootstrapping convenience.
_ = EntityAdapter  # silence pyflakes about re-export
