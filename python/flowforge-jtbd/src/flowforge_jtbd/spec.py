"""Lint-facing JTBD spec models.

The full ``JtbdSpec`` (with its rich storage / lockfile representation)
is owned by ticket E-1. The linter only needs a small subset of those
fields — those that drive lifecycle, dependency, and actor analyses.

This module defines that subset. When E-1 lands, an adapter converts
the canonical ``JtbdSpec`` to ``JtbdLintSpec`` so the linter does not
have to track schema churn.

The models keep ``extra='allow'`` so that an evolving canonical schema
can be pushed through ``model_validate`` without breaking the linter.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import (
	AfterValidator,
	BaseModel,
	ConfigDict,
	Field,
)


# Canonical default stage names (per docs/jtbd-editor-arch.md §2.1).
# Per-domain packs may extend this set (e.g., ``consent_capture``).
DEFAULT_REQUIRED_STAGES: tuple[str, ...] = (
	"discover",
	"execute",
	"error_handle",
	"report",
	"audit",
)
DEFAULT_OPTIONAL_STAGES: tuple[str, ...] = ("undo",)


def _non_empty(value: str) -> str:
	if not value or not value.strip():
		raise ValueError("must be a non-empty string")
	return value


NonEmptyStr = Annotated[str, AfterValidator(_non_empty)]


class StageDecl(BaseModel):
	"""A single lifecycle stage entry on a JTBD.

	A spec either lists the stages it implements directly, or delegates
	a stage to another JTBD via ``handled_by``. Delegation is how a
	bundle keeps completeness without forcing every JTBD to redeclare
	cross-cutting concerns like audit.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	name: NonEmptyStr
	handled_by: str | None = None


class ActorRef(BaseModel):
	"""Reference to the role acting on a JTBD.

	``capacity`` describes how the role engages with the JTBD's primary
	entity (creator, approver, reviewer, operator, delegate, …). Two
	JTBDs in the same bundle that pin the same role to incompatible
	capacities on the same entity are flagged by
	:class:`ActorConsistencyAnalyzer`.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	role: NonEmptyStr
	tier: int | None = None
	capacity: str | None = None
	context: str | None = None


class RoleDef(BaseModel):
	"""Shared role definition for a bundle.

	Carries the default authority tier and the capacities the role
	holds across the bundle. Per-JTBD ``ActorRef`` instances may
	override capacity for that JTBD's context.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	name: NonEmptyStr
	default_tier: int = 0
	capacities: list[str] = Field(default_factory=list)


class JtbdLintSpec(BaseModel):
	"""Lint-facing view of a single JTBD.

	Holds only the fields the linter consumes. The full canonical spec
	may carry many more fields; ``extra='allow'`` keeps this model
	forward-compatible with whatever E-1 produces.
	"""

	model_config = ConfigDict(
		extra="allow",
		validate_by_name=True,
		validate_by_alias=True,
	)

	jtbd_id: NonEmptyStr
	version: NonEmptyStr
	actor: ActorRef | None = None
	requires: list[str] = Field(default_factory=list)
	stages: list[StageDecl] = Field(default_factory=list)
	compliance: list[str] = Field(default_factory=list)
	data_sensitivity: list[str] = Field(default_factory=list)
	domain: str | None = None

	def stage_names(self) -> set[str]:
		"""Return the set of stage names this spec declares directly
		(i.e., excludes delegated stages where ``handled_by`` is set
		to another JTBD id — the resolver below handles delegation)."""
		return {
			stage.name
			for stage in self.stages
			if stage.handled_by is None
		}

	def stage_delegations(self) -> dict[str, str]:
		"""Map of ``stage_name -> handled_by_jtbd_id``."""
		return {
			stage.name: stage.handled_by
			for stage in self.stages
			if stage.handled_by is not None
		}


class JtbdBundle(BaseModel):
	"""A composed set of JTBDs being validated together.

	A bundle is the unit of linting: dependency-graph, actor-consistency,
	and conflict analyses all operate at this scope.
	"""

	model_config = ConfigDict(
		extra="allow",
		validate_by_name=True,
		validate_by_alias=True,
	)

	bundle_id: NonEmptyStr
	jtbds: list[JtbdLintSpec] = Field(default_factory=list)
	shared_roles: dict[str, RoleDef] = Field(default_factory=dict)

	def by_id(self) -> dict[str, JtbdLintSpec]:
		return {spec.jtbd_id: spec for spec in self.jtbds}

	def find(self, jtbd_id: str) -> JtbdLintSpec | None:
		for spec in self.jtbds:
			if spec.jtbd_id == jtbd_id:
				return spec
		return None


__all__ = [
	"DEFAULT_OPTIONAL_STAGES",
	"DEFAULT_REQUIRED_STAGES",
	"ActorRef",
	"JtbdBundle",
	"JtbdLintSpec",
	"NonEmptyStr",
	"RoleDef",
	"StageDecl",
]


# Forward-compat helper to keep static type checkers happy when a
# caller hands us a plain ``dict``-shaped spec produced by E-1.
def coerce_bundle(obj: JtbdBundle | dict[str, Any]) -> JtbdBundle:
	"""Normalise a bundle input to :class:`JtbdBundle`.

	Accepts either a ``JtbdBundle`` instance or a plain ``dict`` (e.g.,
	parsed YAML / JSON from the canonical E-1 schema). The dict path
	uses ``model_validate`` so unknown keys are preserved (``extra=
	'allow'``) and rejected fields surface as Pydantic errors.
	"""
	if isinstance(obj, JtbdBundle):
		return obj
	return JtbdBundle.model_validate(obj)
