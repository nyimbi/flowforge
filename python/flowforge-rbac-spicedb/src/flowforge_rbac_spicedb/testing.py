"""In-memory FakeSpiceDBClient for tests.

The fake mirrors enough of ``authzed.api.v1.AsyncClient`` for
:class:`flowforge_rbac_spicedb.SpiceDBRbac` to round-trip in CI without
spinning up a real SpiceDB. It is deliberately minimal:

* ``CheckPermission`` is exact-match. There is no schema engine — grant
  the literal ``(subject, permission, resource)`` tuple via
  :meth:`grant`, and the fake returns ``HAS_PERMISSION``.
* ``WriteRelationships`` records relations keyed by
  ``(resource, relation, subject)``. ``OPERATION_DELETE`` removes them.
* ``LookupSubjects`` enumerates all subjects of a given object_type that
  hold *either* a literal grant for the requested ``(resource,
  permission)`` *or* the matching catalogue relation written via
  :meth:`SpiceDBRbac.register_permission`.

Use the high-level :meth:`grant` helper for the common case.
"""

from __future__ import annotations

from typing import AsyncIterator

from . import _wire


class _LookupSubjectsItem:
	"""Minimal struct matching ``LookupSubjectsResponse`` shape."""

	__slots__ = ("subject",)

	def __init__(self, subject_object_id: str) -> None:
		# Mimic the ``response.subject.subject_object_id`` attribute path
		# the real client exposes.
		self.subject = _LookupSubjectsSubject(subject_object_id)


class _LookupSubjectsSubject:
	__slots__ = ("subject_object_id",)

	def __init__(self, subject_object_id: str) -> None:
		self.subject_object_id = subject_object_id


_RelKey = tuple[str, str, str, str, str]
"""(resource_type, resource_id, relation, subject_type, subject_id)"""


class FakeSpiceDBClient:
	"""In-memory stand-in for ``authzed.api.v1.AsyncClient``."""

	def __init__(self) -> None:
		self._relations: set[_RelKey] = set()
		# Every (resource, permission, subject) triple the fake should
		# answer ``HAS_PERMISSION`` for. Granted via :meth:`grant`.
		self._grants: set[tuple[str, str, str]] = set()
		# Counters so tests can assert RPC fan-out.
		self.check_calls: int = 0
		self.write_calls: int = 0
		self.lookup_calls: int = 0

	# ------------------------------------------------- public test helpers

	def grant(self, subject: str, permission: str, resource: str) -> None:
		"""Record an explicit ``HAS_PERMISSION`` triple.

		``subject`` and ``resource`` are ``"<type>:<id>"`` strings, e.g.
		``"user:alice"`` and ``"tenant:t-1"``.
		"""

		assert ":" in subject and ":" in resource, "use '<type>:<id>' form"
		self._grants.add((resource, permission, subject))

	def revoke(self, subject: str, permission: str, resource: str) -> None:
		self._grants.discard((resource, permission, subject))

	# ----------------------------------------------- authzed-py interface

	async def CheckPermission(
		self,
		request: _wire.CheckPermissionRequest,
	) -> _wire.CheckPermissionResponse:
		self.check_calls += 1
		key = (
			f"{request.resource.object_type}:{request.resource.object_id}",
			request.permission,
			f"{request.subject.object.object_type}:{request.subject.object.object_id}",
		)
		ok = key in self._grants
		return _wire.CheckPermissionResponse(
			permissionship=(
				_wire.PERMISSIONSHIP_HAS_PERMISSION if ok
				else _wire.PERMISSIONSHIP_NO_PERMISSION
			),
		)

	async def WriteRelationships(
		self,
		request: _wire.WriteRelationshipsRequest,
	) -> _wire.WriteRelationshipsResponse:
		self.write_calls += 1
		for upd in request.updates:
			rel = upd.relationship
			key: _RelKey = (
				rel.resource.object_type,
				rel.resource.object_id,
				rel.relation,
				rel.subject.object.object_type,
				rel.subject.object.object_id,
			)
			if upd.operation == _wire.OPERATION_DELETE:
				self._relations.discard(key)
			else:  # CREATE | TOUCH | anything else => upsert
				self._relations.add(key)
		return _wire.WriteRelationshipsResponse(written_at_token="fake-zedtoken")

	def LookupSubjects(
		self,
		request: _wire.LookupSubjectsRequest,
	) -> AsyncIterator[_LookupSubjectsItem]:
		self.lookup_calls += 1
		return self._lookup(request)

	# ---------------------------------------------------------- internals

	async def _lookup(
		self,
		request: _wire.LookupSubjectsRequest,
	) -> AsyncIterator[_LookupSubjectsItem]:
		seen: set[str] = set()
		# 1) Literal grants from :meth:`grant`.
		resource_str = f"{request.resource.object_type}:{request.resource.object_id}"
		want_subject_type = request.subject_object_type
		for r, perm, subj in self._grants:
			if r != resource_str or perm != request.permission:
				continue
			s_type, _, s_id = subj.partition(":")
			if s_type == want_subject_type and s_id not in seen:
				seen.add(s_id)
				yield _LookupSubjectsItem(s_id)
		# 2) Relations written via WriteRelationships (used by the
		#    permission-catalogue object).
		for r_type, r_id, relation, s_type, s_id in self._relations:
			if (
				r_type == request.resource.object_type
				and r_id == request.resource.object_id
				and relation == request.permission
				and s_type == want_subject_type
				and s_id not in seen
			):
				seen.add(s_id)
				yield _LookupSubjectsItem(s_id)
