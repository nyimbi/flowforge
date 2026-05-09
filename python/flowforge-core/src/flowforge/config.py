"""Mutable global configuration object.

Hosts wire port implementations into ``flowforge.config`` at startup. The
engine reads from this object — never from constructor arguments — so the
core stays ABC-only and the wiring is a single source of truth.

The config defaults to in-memory port fakes from
:mod:`flowforge.testing.port_fakes` so tests and simulators run without
any external setup. Production hosts overwrite the relevant attributes
during their FastAPI / Litestar / etc. startup hook.

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

from typing import Any

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
