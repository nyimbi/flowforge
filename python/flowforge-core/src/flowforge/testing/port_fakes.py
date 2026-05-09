"""In-memory port impls.

Every port has a default impl here so config defaults wire to a working
fake. Hosts replace these with real adapters at startup.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, AsyncIterator, Mapping

from ..ports.audit import AuditSink, Verdict
from ..ports.types import (
	AuditEvent,
	NotificationSpec,
	OutboxEnvelope,
	PermissionName,
	Principal,
	Scope,
)


# ---- tenancy ----------------------------------------------------------


class InMemoryTenancy:
	def __init__(self, tenant_id: str = "default") -> None:
		self._tenant_id = tenant_id
		self._elevated = False

	async def current_tenant(self) -> str:
		return self._tenant_id

	async def bind_session(self, session: Any, tenant_id: str) -> None:
		# noop for in-memory hosts
		self._tenant_id = tenant_id

	@asynccontextmanager
	async def elevated_scope(self) -> AsyncIterator[None]:
		prior = self._elevated
		self._elevated = True
		try:
			yield
		finally:
			self._elevated = prior


# ---- rbac -------------------------------------------------------------


class InMemoryRbac:
	def __init__(self, grants: dict[str, set[str]] | None = None) -> None:
		self._grants: dict[str, set[str]] = grants or {}
		self._catalog: dict[str, str] = {}

	async def has_permission(self, principal: Principal, permission: PermissionName, scope: Scope) -> bool:
		# Simulator-friendly default: allow everything for system principals.
		if principal.is_system:
			return True
		return permission in self._grants.get(principal.user_id, set())

	async def list_principals_with(self, permission: PermissionName, scope: Scope) -> list[Principal]:
		out = []
		for user, perms in self._grants.items():
			if permission in perms:
				out.append(Principal(user_id=user))
		return out

	async def register_permission(
		self,
		name: PermissionName,
		description: str,
		deprecated_aliases: list[str] | None = None,
	) -> None:
		self._catalog[name] = description

	async def assert_seed(self, names: list[PermissionName]) -> list[PermissionName]:
		return [n for n in names if n not in self._catalog]


# ---- audit ------------------------------------------------------------


class InMemoryAuditSink:
	def __init__(self) -> None:
		self.events: list[AuditEvent] = []

	async def record(self, event: AuditEvent) -> str:
		self.events.append(event)
		return f"evt-{len(self.events)}"

	async def verify_chain(self, since: str | None = None) -> Verdict:
		return Verdict.supported_ok(len(self.events))

	async def redact(self, paths: list[str], reason: str) -> int:
		# Tombstone: replace path values with "[redacted: <reason>]"
		count = 0
		for ev in self.events:
			for p in paths:
				if p in ev.payload:
					ev.payload[p] = f"[redacted:{reason}]"
					count += 1
		return count


# ---- outbox -----------------------------------------------------------


class InMemoryOutbox:
	def __init__(self) -> None:
		self._handlers: dict[tuple[str, str], Any] = {}
		self.dispatched: list[OutboxEnvelope] = []

	def register(self, kind: str, handler: Any, backend: str = "default") -> None:
		self._handlers[(backend, kind)] = handler

	async def dispatch(self, envelope: OutboxEnvelope, backend: str = "default") -> None:
		self.dispatched.append(envelope)
		handler = self._handlers.get((backend, envelope.kind))
		if handler is not None:
			await handler(envelope)

	def list_kinds(self, backend: str = "default") -> list[str]:
		return [k for (b, k) in self._handlers.keys() if b == backend]


# ---- documents --------------------------------------------------------


class InMemoryDocuments:
	def __init__(self) -> None:
		self._docs: dict[str, list[dict[str, Any]]] = {}

	async def list_for_subject(self, subject_id: str, kinds: list[str] | None = None) -> list[dict[str, Any]]:
		rows = self._docs.get(subject_id, [])
		if kinds is None:
			return list(rows)
		return [r for r in rows if r.get("kind") in set(kinds)]

	async def attach(self, subject_id: str, doc_id: str) -> None:
		self._docs.setdefault(subject_id, []).append({"id": doc_id, "kind": "unknown"})

	async def get_classification(self, doc_id: str) -> str | None:
		return None

	async def freshness_days(self, doc_id: str) -> int | None:
		return 0


# ---- money ------------------------------------------------------------


class InMemoryMoney:
	def __init__(self, rates: dict[tuple[str, str], Decimal] | None = None) -> None:
		self._rates = rates or {}

	async def convert(
		self,
		amount: Decimal,
		from_currency: str,
		to_currency: str,
		at: datetime,
	) -> tuple[Decimal, Decimal]:
		if from_currency == to_currency:
			return amount, Decimal("1")
		rate = self._rates.get((from_currency, to_currency)) or Decimal("1")
		return amount * rate, rate

	async def format(self, amount: Decimal, currency: str, locale: str = "en") -> str:
		return f"{amount} {currency}"


# ---- settings ---------------------------------------------------------


class InMemorySettings:
	def __init__(self) -> None:
		self._vals: dict[str, Any] = {}

	async def get(self, key: str) -> Any:
		return self._vals.get(key)

	async def set(self, key: str, value: Any, signed_by: str | None = None) -> None:
		self._vals[key] = value

	async def register(self, spec: Any) -> None:
		# spec.key, spec.default
		key = getattr(spec, "key", None) or spec["key"]
		default = getattr(spec, "default", None)
		if default is not None:
			self._vals.setdefault(key, default)


# ---- signing ----------------------------------------------------------


class InMemorySigning:
	def __init__(self, key_id: str = "test-key") -> None:
		self._key = key_id

	async def sign_payload(self, payload: bytes) -> bytes:
		import hashlib
		return hashlib.sha256(self._key.encode() + payload).digest()

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		import hashlib
		return signature == hashlib.sha256(key_id.encode() + payload).digest()

	def current_key_id(self) -> str:
		return self._key


# ---- notification -----------------------------------------------------


class InMemoryNotifications:
	def __init__(self) -> None:
		self._templates: dict[str, NotificationSpec] = {}
		self.sent: list[dict[str, Any]] = []

	async def render(self, template_id: str, locale: str, ctx: dict[str, Any]) -> tuple[str, str]:
		spec = self._templates.get(template_id)
		if spec is None:
			return (template_id, "")
		# extremely simple {var} interpolation
		def interp(s: str) -> str:
			out = s
			for k, v in ctx.items():
				out = out.replace(f"{{{k}}}", str(v))
			return out
		return interp(spec.subject_template), interp(spec.body_template)

	async def send(self, channel: str, recipient: str, rendered: tuple[str, str]) -> None:
		self.sent.append({"channel": channel, "to": recipient, "subject": rendered[0], "body": rendered[1]})

	async def register_template(self, spec: NotificationSpec) -> None:
		self._templates[spec.template_id] = spec


# ---- rls --------------------------------------------------------------


class NoopRls:
	async def bind(self, session: Any, ctx: Any) -> None:
		return None

	@asynccontextmanager
	async def elevated(self, session: Any) -> AsyncIterator[None]:
		yield


# ---- metrics ----------------------------------------------------------


class InMemoryMetrics:
	def __init__(self) -> None:
		self.points: list[tuple[str, float, dict[str, str]]] = []
		self.histograms: list[tuple[str, float, dict[str, str]]] = []

	def emit(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
		self.points.append((name, value, dict(labels or {})))

	def record_histogram(
		self,
		name: str,
		value: float,
		labels: Mapping[str, str] | None = None,
	) -> None:
		"""Record a histogram observation. Tests inspect ``histograms``."""

		self.histograms.append((name, value, dict(labels or {})))


# ---- tracing ----------------------------------------------------------


class _NoopSpan:
	"""Span fake that captures attributes for test assertions."""

	def __init__(self, name: str, attributes: dict[str, Any]) -> None:
		self.name = name
		self.attributes: dict[str, Any] = dict(attributes)
		self.exceptions: list[BaseException] = []

	def set_attribute(self, key: str, value: Any) -> None:
		self.attributes[key] = value

	def record_exception(self, exc: BaseException) -> None:
		self.exceptions.append(exc)


class NoopTracing:
	"""In-memory :class:`flowforge.ports.tracing.TracingPort` fake.

	Records every span started, including its attributes; tests inspect
	``spans`` to assert on the OTel attribute coverage of generated host
	code without booting a real OpenTelemetry exporter.
	"""

	def __init__(self) -> None:
		self.spans: list[_NoopSpan] = []

	def start_span(
		self,
		name: str,
		attributes: Mapping[str, Any] | None = None,
	) -> "_NoopSpanCtx":
		span = _NoopSpan(name, dict(attributes or {}))
		self.spans.append(span)
		return _NoopSpanCtx(span)


class _NoopSpanCtx:
	"""Async context manager that yields a :class:`_NoopSpan`."""

	def __init__(self, span: _NoopSpan) -> None:
		self._span = span

	async def __aenter__(self) -> _NoopSpan:
		return self._span

	async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
		if exc is not None and isinstance(exc, BaseException):
			self._span.record_exception(exc)
		return None


# ---- tasks ------------------------------------------------------------


class InMemoryTaskTracker:
	def __init__(self) -> None:
		self.tasks: list[dict[str, str]] = []

	async def create_task(self, kind: str, ref: str, note: str) -> str:
		row = {"id": f"t-{len(self.tasks)+1}", "kind": kind, "ref": ref, "note": note}
		self.tasks.append(row)
		return row["id"]


# ---- access grants ----------------------------------------------------


class InMemoryAccessGrant:
	def __init__(self) -> None:
		self.grants: dict[str, datetime | None] = {}

	async def grant(self, relation: str, until: datetime | None = None) -> None:
		self.grants[relation] = until

	async def revoke(self, relation: str) -> None:
		self.grants.pop(relation, None)


# ---- analytics --------------------------------------------------------


class InMemoryAnalytics:
	"""In-memory :class:`flowforge.ports.analytics.AnalyticsPort` fake.

	Captures every ``track`` invocation in declaration order so tests
	can assert on the closed taxonomy emitted by the
	``analytics_taxonomy`` generator (item 16 of
	:doc:`docs/improvements`). Mirrors :class:`InMemoryAuditSink` and
	:class:`NoopTracing` in shape — no I/O, no provider SDK.
	"""

	def __init__(self) -> None:
		self.events: list[tuple[str, dict[str, Any]]] = []

	async def track(self, event_name: str, properties: dict[str, Any]) -> None:
		assert isinstance(event_name, str), "event_name must be a string"
		assert isinstance(properties, dict), "properties must be a dict"
		# Defensive copy so callers mutating the dict afterwards don't
		# rewrite history in our captured ledger.
		self.events.append((event_name, dict(properties)))


__all__ = [
	"InMemoryAccessGrant",
	"InMemoryAnalytics",
	"InMemoryAuditSink",
	"InMemoryDocuments",
	"InMemoryMetrics",
	"InMemoryMoney",
	"InMemoryNotifications",
	"InMemoryOutbox",
	"InMemoryRbac",
	"InMemorySettings",
	"InMemorySigning",
	"InMemoryTaskTracker",
	"InMemoryTenancy",
	"NoopRls",
	"NoopTracing",
]
