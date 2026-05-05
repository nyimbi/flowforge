"""Pydantic models for workflow definitions.

Mirrors ``docs/workflow-framework-portability.md`` §6.2.d. Lives in pure
data — no behaviour. The compiler validates instances; the engine reads
them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field as PField

StateKind = Literal[
	"manual_review",
	"automatic",
	"parallel_fork",
	"parallel_join",
	"timer",
	"signal_wait",
	"subworkflow",
	"terminal_success",
	"terminal_fail",
]

GateKind = Literal[
	"permission",
	"documents_complete",
	"checklist_complete",
	"approval",
	"co_signature",
	"compliance",
	"custom_webhook",
	"expr",
]

EffectKind = Literal[
	"create_entity",
	"update_entity",
	"set",
	"notify",
	"audit",
	"emit_signal",
	"start_subworkflow",
	"compensate",
	"http_call",
]


class Guard(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: Literal["expr"] = "expr"
	expr: Any = True


class Gate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: GateKind
	permission: str | None = None
	policy: str | None = None
	tier: int | None = None


class Effect(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: EffectKind
	entity: str | None = None
	target: str | None = None
	expr: Any = None
	values: dict[str, Any] | None = None
	template: str | None = None
	signal: str | None = None
	subworkflow_key: str | None = None
	compensation_kind: str | None = None
	url: str | None = None


class Sla(BaseModel):
	model_config = ConfigDict(extra="forbid")

	warn_pct: int | None = None
	breach_seconds: int | None = None
	pause_aware: bool = True


class State(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: str
	kind: StateKind
	swimlane: str | None = None
	form_spec_id: str | None = None
	documents: list[dict[str, Any]] = PField(default_factory=list)
	sla: Sla | None = None
	subworkflow_key: str | None = None


class Transition(BaseModel):
	model_config = ConfigDict(extra="forbid")

	id: str
	event: str
	from_state: str
	to_state: str
	priority: int = 0
	guards: list[Guard] = PField(default_factory=list)
	gates: list[Gate] = PField(default_factory=list)
	effects: list[Effect] = PField(default_factory=list)


class EscalationTrigger(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: Literal["sla_breach", "manual"]
	state: str | None = None


class EscalationAction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: str
	role: str | None = None
	template: str | None = None


class Escalation(BaseModel):
	model_config = ConfigDict(extra="forbid")

	trigger: EscalationTrigger
	actions: list[EscalationAction] = PField(default_factory=list)
	cooldown_seconds: int = 600


class WorkflowDef(BaseModel):
	model_config = ConfigDict(extra="forbid")

	key: str
	version: str
	subject_kind: str
	initial_state: str
	metadata: dict[str, Any] = PField(default_factory=dict)
	states: list[State]
	transitions: list[Transition] = PField(default_factory=list)
	escalations: list[Escalation] = PField(default_factory=list)
