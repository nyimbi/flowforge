"""flowforge-outbox-pg — transactional outbox with PG FOR UPDATE SKIP LOCKED.

Public API
----------
- ``HandlerRegistry`` — register/dispatch handlers across named backends
- ``DrainWorker`` — poll-and-drain loop with retry + DLQ logic
- ``DrainWorkerHealth`` — observable health/counter snapshot
- ``readiness_payload`` / ``prometheus_text`` — host endpoint/collector helpers
- ``OutboxRow`` — dataclass representing a single outbox table row
- ``OutboxStatus`` — enum of row lifecycle states

For testing without PostgreSQL, pass a ``sqlite_compat=True`` connection;
the worker falls back to a simple advisory-lock-free claim query.
"""

from __future__ import annotations

from .health import prometheus_text, readiness_payload
from .registry import HandlerRegistry
from .worker import DrainWorker, DrainWorkerHealth, OutboxRow, OutboxStatus

__all__ = [
    "DrainWorker",
    "DrainWorkerHealth",
    "HandlerRegistry",
    "OutboxRow",
    "OutboxStatus",
    "prometheus_text",
    "readiness_payload",
]
