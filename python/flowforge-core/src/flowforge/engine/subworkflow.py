"""Sub-workflow handle.

A workflow may declare a state of kind ``subworkflow`` whose
``subworkflow_key`` names another workflow. When the engine enters that
state it spawns a child instance; on the child's terminal state, the
parent fires its ``subworkflow_complete`` event.

Full implementation is host-pluggable (because storage of children is a
host concern); this module just provides the data shape the simulator
uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubworkflowHandle:
	parent_instance_id: str
	child_instance_id: str
	subworkflow_key: str
	depth: int = 1
	context: dict[str, Any] = field(default_factory=dict)
