"""Runtime port configuration.

Hosts wire port implementations into ``flowforge.config`` at startup. The
engine reads from this object — never from constructor arguments — so the
core stays ABC-only and the wiring is a single source of truth.

The config defaults to in-memory port fakes from
:mod:`flowforge.testing.port_fakes` so tests and simulators run without
any external setup. Production hosts overwrite the relevant attributes
during their FastAPI / Litestar / etc. startup hook.

For multi-app processes, hosts can install a scoped
:class:`RuntimeConfig` with :func:`use_runtime_config`; engine code that
uses :func:`current` reads the scoped ports instead of the module globals.
Production startup should call :func:`validate_production_config` after
wiring ports so test fakes and noop RLS do not reach a live host.

Example::

    from flowforge import config
    from flowforge.testing.port_fakes import (
        InMemoryAuditSink, InMemoryOutbox, InMemoryRbac, InMemoryTenancy,
    )

    config.tenancy = InMemoryTenancy("tenant-1")
    config.rbac = InMemoryRbac()
    config.audit = InMemoryAuditSink()
    config.outbox = InMemoryOutbox()
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


PORT_NAMES: tuple[str, ...] = (
	"tenancy",
	"rbac",
	"audit",
	"outbox",
	"documents",
	"money",
	"settings",
	"signing",
	"notification",
	"rls",
	"metrics",
	"tasks",
	"grants",
	"entity_registry",
	"tracing",
)

DEFAULT_PRODUCTION_REQUIRED_PORTS: tuple[str, ...] = (
	"tenancy",
	"rbac",
	"audit",
	"outbox",
	"rls",
)


class ProductionConfigError(RuntimeError):
	"""Raised when production startup validation finds unsafe port wiring."""

	def __init__(self, errors: list[str]) -> None:
		self.errors = errors
		super().__init__("invalid flowforge production config: " + "; ".join(errors))


@dataclass(slots=True)
class RuntimeConfig:
	"""App-scoped flowforge port wiring."""

	tenancy: Any = None
	rbac: Any = None
	audit: Any = None
	outbox: Any = None
	documents: Any = None
	money: Any = None
	settings: Any = None
	signing: Any = None
	notification: Any = None
	rls: Any = None
	metrics: Any = None
	tasks: Any = None
	grants: Any = None
	entity_registry: Any = None
	tracing: Any = None
	snapshot_interval: int = 100
	max_nesting_depth: int = 5
	lookup_rate_limit_per_minute: int = 600


_ACTIVE_CONFIG: ContextVar[RuntimeConfig | None] = ContextVar(
	"flowforge_runtime_config", default=None
)

# Ports are typed as ``Any`` here to avoid a circular import; the
# concrete ABCs live in :mod:`flowforge.ports`. Tooling sees the right
# types via ``flowforge.config:set_*`` helpers below.
tenancy: Any = None
rbac: Any = None
audit: Any = None
outbox: Any = None
documents: Any = None
money: Any = None
settings: Any = None
signing: Any = None
notification: Any = None
rls: Any = None
metrics: Any = None
tasks: Any = None
grants: Any = None
entity_registry: Any = None
# v0.3.0 W2 / item 12 — TracingPort wiring. Generated host code reads
# this attribute through ``flowforge.config.tracing`` and falls back to
# a NoopTracing if the host hasn't wired an OTel-backed adapter.
tracing: Any = None

# Tunables (see portability §7 customisation table)
snapshot_interval: int = 100
max_nesting_depth: int = 5
lookup_rate_limit_per_minute: int = 600


def snapshot_runtime_config() -> RuntimeConfig:
	"""Return a copy of the current module-global config values."""

	return RuntimeConfig(
		tenancy=tenancy,
		rbac=rbac,
		audit=audit,
		outbox=outbox,
		documents=documents,
		money=money,
		settings=settings,
		signing=signing,
		notification=notification,
		rls=rls,
		metrics=metrics,
		tasks=tasks,
		grants=grants,
		entity_registry=entity_registry,
		tracing=tracing,
		snapshot_interval=snapshot_interval,
		max_nesting_depth=max_nesting_depth,
		lookup_rate_limit_per_minute=lookup_rate_limit_per_minute,
	)


def current() -> RuntimeConfig:
	"""Return the active scoped config or a snapshot of module globals."""

	scoped = _ACTIVE_CONFIG.get()
	if scoped is not None:
		return scoped
	return snapshot_runtime_config()


@contextmanager
def use_runtime_config(runtime_config: RuntimeConfig):
	"""Temporarily use *runtime_config* for engine code in this context."""

	token = _ACTIVE_CONFIG.set(runtime_config)
	try:
		yield runtime_config
	finally:
		_ACTIVE_CONFIG.reset(token)


def _is_testing_fake(value: Any) -> bool:
	if value is None:
		return False
	typ = type(value)
	if typ.__module__ == "flowforge.testing.port_fakes":
		return True
	return typ.__name__ in {
		"InMemoryTenancy",
		"InMemoryRbac",
		"InMemoryAuditSink",
		"InMemoryOutbox",
		"InMemoryDocuments",
		"InMemoryMoney",
		"InMemorySettings",
		"InMemorySigning",
		"InMemoryNotifications",
		"InMemoryMetrics",
		"InMemoryTaskTracker",
		"InMemoryAccessGrant",
		"InMemoryAnalytics",
		"NoopRls",
		"NoopTracing",
	}


def production_config_errors(
	runtime_config: RuntimeConfig | None = None,
	*,
	required_ports: tuple[str, ...] = DEFAULT_PRODUCTION_REQUIRED_PORTS,
	allow_testing_fakes: bool = False,
) -> list[str]:
	"""Return production-safety wiring errors without raising."""

	cfg = runtime_config or current()
	errors: list[str] = []
	for name in required_ports:
		if name not in PORT_NAMES:
			errors.append(f"unknown required port {name!r}")
			continue
		value = getattr(cfg, name)
		if value is None:
			errors.append(f"{name} is not configured")
		elif not allow_testing_fakes and _is_testing_fake(value):
			errors.append(f"{name} uses testing fake {type(value).__name__}")
	return errors


def validate_production_config(
	runtime_config: RuntimeConfig | None = None,
	*,
	required_ports: tuple[str, ...] = DEFAULT_PRODUCTION_REQUIRED_PORTS,
	allow_testing_fakes: bool = False,
) -> None:
	"""Fail closed if production-critical ports are missing or fake."""

	errors = production_config_errors(
		runtime_config,
		required_ports=required_ports,
		allow_testing_fakes=allow_testing_fakes,
	)
	if errors:
		raise ProductionConfigError(errors)


def reset_to_fakes() -> None:
	"""Re-initialise every port to its in-memory fake. Tests use this in fixtures."""

	# Imported lazily to avoid a hard dependency cycle.
	from .testing import port_fakes as _f
	from .compiler.catalog import EntityRegistry as _Reg

	global tenancy, rbac, audit, outbox, documents, money, settings, signing
	global notification, rls, metrics, tasks, grants, entity_registry, tracing

	tenancy = _f.InMemoryTenancy()
	rbac = _f.InMemoryRbac()
	audit = _f.InMemoryAuditSink()
	outbox = _f.InMemoryOutbox()
	documents = _f.InMemoryDocuments()
	money = _f.InMemoryMoney()
	settings = _f.InMemorySettings()
	signing = _f.InMemorySigning()
	notification = _f.InMemoryNotifications()
	rls = _f.NoopRls()
	metrics = _f.InMemoryMetrics()
	tasks = _f.InMemoryTaskTracker()
	grants = _f.InMemoryAccessGrant()
	entity_registry = _Reg()
	tracing = _f.NoopTracing()
