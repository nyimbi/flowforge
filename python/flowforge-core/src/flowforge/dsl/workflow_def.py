"""Pydantic models for workflow definitions.

Mirrors ``docs/workflow-framework-portability.md`` §6.2.d. Lives in pure
data — no behaviour. The compiler validates instances; the engine reads
them.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field as PField


# audit-2026 C-11: shape-validate Guard.expr at parse time. The expression
# evaluator already rejects malformed shapes at runtime (E-35 ArityMismatch)
# but a dict with two keys is structurally meaningless — caught here it
# fails fast with a useful error rather than surviving until guard
# evaluation.
def _validate_expr_shape(value: Any) -> Any:
	"""Validate the AST shape of a Guard.expr.

	Allowed shapes:
	* literals (str, int, float, bool, None)
	* arrays (recursively validated)
	* single-key dicts (the op-call form ``{"<op>": <args>}``); the args
	  payload is recursively validated
	* the special path-ref string form is permitted as-is

	Multi-key dicts are rejected — they're never valid op calls and
	never literal expressions in the JTBD/workflow DSL.
	"""

	if value is None or isinstance(value, (bool, int, float, str)):
		return value
	if isinstance(value, list):
		for child in value:
			_validate_expr_shape(child)
		return value
	if isinstance(value, dict):
		if len(value) != 1:
			raise ValueError(
				f"Guard.expr dict must have exactly one key (op-call form), "
				f"got {len(value)} keys: {sorted(value)!r}"
			)
		(_, raw), = value.items()
		_validate_expr_shape(raw)
		return value
	raise ValueError(f"Guard.expr value of unsupported type {type(value).__name__}")

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
	# audit-2026 C-11: shape-validate at parse time so multi-key dict
	# expressions fail with a useful error before the engine touches them.
	expr: Annotated[Any, AfterValidator(_validate_expr_shape)] = True


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
