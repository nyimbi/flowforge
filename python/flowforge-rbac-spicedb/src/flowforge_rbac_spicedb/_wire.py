"""Tiny wire-format dataclasses mirroring the authzed v1 message shape.

We intentionally do not import ``authzed`` here. The real
``authzed.api.v1`` messages duck-type onto these (attribute names match),
so the resolver works against either the live client or the in-memory
fake without an installed dependency. The ``spicedb`` extra pulls in
``authzed`` for production wiring; tests stay dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ``permissionship`` enum codes that mirror authzed.api.v1.CheckPermissionResponse.
PERMISSIONSHIP_UNSPECIFIED = 0
PERMISSIONSHIP_NO_PERMISSION = 1
PERMISSIONSHIP_HAS_PERMISSION = 2
PERMISSIONSHIP_CONDITIONAL_PERMISSION = 3

# RelationshipUpdate.operation codes.
OPERATION_UNSPECIFIED = 0
OPERATION_CREATE = 1
OPERATION_TOUCH = 2
OPERATION_DELETE = 3


@dataclass(frozen=True)
class ObjectReference:
	object_type: str
	object_id: str


@dataclass(frozen=True)
class SubjectReference:
	object: ObjectReference
	optional_relation: str = ""


@dataclass(frozen=True)
class Relationship:
	resource: ObjectReference
	relation: str
	subject: SubjectReference


@dataclass(frozen=True)
class RelationshipUpdate:
	operation: int
	relationship: Relationship


@dataclass(frozen=True)
class Consistency:
	"""Mirror of ``authzed.api.v1.Consistency``.

	E-55 / RB-02: ``at_least_as_fresh`` carries the most-recently-observed
	Zedtoken (``written_at_token`` from a previous ``WriteRelationships``)
	so SpiceDB serves reads at-or-after that revision. Without this, the
	default ``minimize_latency`` setting can serve a stale revision and
	miss a relation that was written nanoseconds earlier.
	"""

	at_least_as_fresh: str = ""


@dataclass(frozen=True)
class CheckPermissionRequest:
	resource: ObjectReference
	permission: str
	subject: SubjectReference
	consistency: Consistency | None = None


@dataclass(frozen=True)
class CheckPermissionResponse:
	permissionship: int


@dataclass(frozen=True)
class WriteRelationshipsRequest:
	updates: list[RelationshipUpdate] = field(default_factory=list)


@dataclass(frozen=True)
class WriteRelationshipsResponse:
	written_at_token: str = ""


@dataclass(frozen=True)
class LookupSubjectsRequest:
	resource: ObjectReference
	permission: str
	subject_object_type: str
	consistency: Consistency | None = None


@dataclass(frozen=True)
class LookupSubjectsResponse:
	subject_object_id: str
