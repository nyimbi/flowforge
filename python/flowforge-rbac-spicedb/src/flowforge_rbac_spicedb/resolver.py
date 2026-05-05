"""SpiceDBRbac — RBAC resolver wrapping an authzed-py async client.

The resolver implements :class:`flowforge.ports.RbacResolver` by issuing
``CheckPermission``, ``WriteRelationships``, and ``LookupSubjects`` RPCs
against SpiceDB. The client itself is duck-typed via
:class:`SpiceDBClientProtocol` so that:

* production code passes ``authzed.api.v1.AsyncClient``,
* tests pass :class:`flowforge_rbac_spicedb.testing.FakeSpiceDBClient`,
* and we never import ``authzed`` at module load.

Mapping conventions
-------------------

* Subject:  ``user:<principal.user_id>``
* Resource: ``<scope.resource_kind or 'tenant'>:<scope.resource_id or scope.tenant_id>``
* Permission: the bare ``PermissionName`` string. Hosts pre-define these in
  their SpiceDB schema (``permission claim_create = …`` etc.) — the
  resolver assumes the schema names match the catalogue exactly.

Permission catalogue
--------------------

SpiceDB has no first-class permission registry. We therefore maintain a
synthetic catalogue object — ``permission_catalog:<schema_prefix>`` — and
write a ``defined`` relation per permission name. ``assert_seed`` reads
the catalogue back via ``LookupSubjects``.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from flowforge.ports import PermissionName, Principal, Scope

from . import _wire


class CatalogDriftError(RuntimeError):
	"""Raised in strict mode when seeded permissions are not in the catalogue."""


@runtime_checkable
class SpiceDBClientProtocol(Protocol):
	"""Subset of the ``authzed.api.v1.AsyncClient`` surface we depend on.

	Both the real client and :class:`FakeSpiceDBClient` satisfy this
	Protocol. Methods are async and return either a single response or
	an async iterator of streamed responses (``LookupSubjects``).
	"""

	async def CheckPermission(self, request: Any) -> Any: ...

	async def WriteRelationships(self, request: Any) -> Any: ...

	def LookupSubjects(self, request: Any) -> AsyncIterator[Any]: ...


class SpiceDBRbac:
	"""SpiceDB-backed implementation of :class:`flowforge.ports.RbacResolver`.

	Parameters
	----------
	client:
		An async SpiceDB client. ``authzed.api.v1.AsyncClient`` works in
		production; :class:`FakeSpiceDBClient` works in tests.
	schema_prefix:
		Logical namespace used for the permission catalogue object.
		Defaults to ``"flowforge"``.
	subject_object_type:
		SpiceDB object type for principals. Defaults to ``"user"``.
	default_resource_type:
		Object type used when ``Scope.resource_kind`` is ``None``.
		Defaults to ``"tenant"`` — i.e. tenant-wide checks resolve to
		``tenant:<tenant_id>``.
	strict:
		When ``True``, :meth:`assert_seed` raises
		:class:`CatalogDriftError` instead of returning the missing list.
	"""

	def __init__(
		self,
		client: SpiceDBClientProtocol,
		*,
		schema_prefix: str = "flowforge",
		subject_object_type: str = "user",
		default_resource_type: str = "tenant",
		strict: bool = False,
	) -> None:
		assert client is not None, "SpiceDBRbac requires a client"
		assert schema_prefix, "schema_prefix must be non-empty"
		assert subject_object_type, "subject_object_type must be non-empty"
		assert default_resource_type, "default_resource_type must be non-empty"
		self._client = client
		self._schema_prefix = schema_prefix
		self._subject_type = subject_object_type
		self._default_resource_type = default_resource_type
		self._strict = strict
		# Local mirror of the description text — SpiceDB only stores the
		# fact that a permission is *defined*, not its prose.
		self._descriptions: dict[str, str] = {}

	# ----------------------------------------------------------------- helpers

	def _subject(self, principal: Principal) -> _wire.SubjectReference:
		return _wire.SubjectReference(
			object=_wire.ObjectReference(
				object_type=self._subject_type,
				object_id=principal.user_id,
			)
		)

	def _resource(self, scope: Scope) -> _wire.ObjectReference:
		object_type = scope.resource_kind or self._default_resource_type
		object_id = scope.resource_id or scope.tenant_id
		return _wire.ObjectReference(object_type=object_type, object_id=object_id)

	def _catalog_resource(self) -> _wire.ObjectReference:
		return _wire.ObjectReference(
			object_type="permission_catalog",
			object_id=self._schema_prefix,
		)

	def _permission_subject(self, name: PermissionName) -> _wire.SubjectReference:
		return _wire.SubjectReference(
			object=_wire.ObjectReference(
				object_type="permission_name",
				object_id=name,
			)
		)

	# --------------------------------------------------------- RbacResolver

	async def has_permission(
		self,
		principal: Principal,
		permission: PermissionName,
		scope: Scope,
	) -> bool:
		assert isinstance(permission, str) and permission, "permission name required"
		if principal.is_system:
			return True
		req = _wire.CheckPermissionRequest(
			resource=self._resource(scope),
			permission=permission,
			subject=self._subject(principal),
		)
		resp = await self._client.CheckPermission(req)
		return getattr(resp, "permissionship", _wire.PERMISSIONSHIP_NO_PERMISSION) == \
			_wire.PERMISSIONSHIP_HAS_PERMISSION

	async def list_principals_with(
		self,
		permission: PermissionName,
		scope: Scope,
	) -> list[Principal]:
		assert isinstance(permission, str) and permission, "permission name required"
		req = _wire.LookupSubjectsRequest(
			resource=self._resource(scope),
			permission=permission,
			subject_object_type=self._subject_type,
		)
		out: list[Principal] = []
		async for item in self._client.LookupSubjects(req):
			# Real responses expose ``subject.subject_object_id``; the fake
			# returns a flat ``subject_object_id`` for simplicity.
			subject = getattr(item, "subject", None)
			user_id = getattr(subject, "subject_object_id", None) if subject is not None \
				else getattr(item, "subject_object_id", None)
			if user_id:
				out.append(Principal(user_id=user_id))
		return out

	async def register_permission(
		self,
		name: PermissionName,
		description: str,
		deprecated_aliases: list[str] | None = None,
	) -> None:
		assert isinstance(name, str) and name, "permission name required"
		self._descriptions[name] = description
		updates: list[_wire.RelationshipUpdate] = [
			_wire.RelationshipUpdate(
				operation=_wire.OPERATION_TOUCH,
				relationship=_wire.Relationship(
					resource=self._catalog_resource(),
					relation="defined",
					subject=self._permission_subject(name),
				),
			),
		]
		for alias in deprecated_aliases or []:
			updates.append(
				_wire.RelationshipUpdate(
					operation=_wire.OPERATION_TOUCH,
					relationship=_wire.Relationship(
						resource=self._catalog_resource(),
						relation="alias",
						subject=self._permission_subject(alias),
					),
				)
			)
		await self._client.WriteRelationships(
			_wire.WriteRelationshipsRequest(updates=updates),
		)

	async def assert_seed(self, names: list[PermissionName]) -> list[PermissionName]:
		assert isinstance(names, list), "names must be a list"
		req = _wire.LookupSubjectsRequest(
			resource=self._catalog_resource(),
			permission="defined",
			subject_object_type="permission_name",
		)
		known: set[str] = set()
		async for item in self._client.LookupSubjects(req):
			subject = getattr(item, "subject", None)
			pname = getattr(subject, "subject_object_id", None) if subject is not None \
				else getattr(item, "subject_object_id", None)
			if pname:
				known.add(pname)
		missing = [n for n in names if n not in known]
		if missing and self._strict:
			raise CatalogDriftError(f"missing permissions: {missing}")
		return missing
