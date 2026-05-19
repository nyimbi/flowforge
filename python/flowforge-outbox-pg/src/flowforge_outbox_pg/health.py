"""Readiness and metrics helpers for :class:`DrainWorker` health snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .worker import DrainWorker, DrainWorkerHealth


def _snapshot(worker_or_health: DrainWorker | DrainWorkerHealth) -> DrainWorkerHealth:
    if isinstance(worker_or_health, DrainWorkerHealth):
        return worker_or_health
    return worker_or_health.health()


def readiness_payload(
    worker_or_health: DrainWorker | DrainWorkerHealth,
) -> tuple[int, dict[str, Any]]:
    """Return ``(http_status, payload)`` for host readiness endpoints.

    Hosts can mount this directly in FastAPI, Flask, Django, or another
    framework without depending on a Flowforge-provided web stack. ``200`` means
    the worker's last run was healthy; ``503`` means the worker reports degraded
    health and the payload includes its counters plus last error.
    """

    health = _snapshot(worker_or_health)
    status_code = 200 if health.status == "ok" else 503
    return status_code, health.as_dict()


def prometheus_text(
    worker_or_health: DrainWorker | DrainWorkerHealth,
    *,
    prefix: str = "flowforge_outbox_worker",
    labels: Mapping[str, str] | None = None,
) -> str:
    """Render a small Prometheus text exposition for worker health.

    The helper intentionally avoids importing ``prometheus_client`` so critical
    hosts can expose the counters from their existing metrics stack or serve this
    string from a lightweight route.
    """

    health = _snapshot(worker_or_health)
    label_text = _format_labels(labels or {})
    degraded = 1 if health.status != "ok" else 0
    lines = [
        f"# HELP {prefix}_degraded 1 when the outbox worker reports degraded health.",
        f"# TYPE {prefix}_degraded gauge",
        f"{prefix}_degraded{label_text} {degraded}",
        f"# HELP {prefix}_reconnects_total Total worker reconnects.",
        f"# TYPE {prefix}_reconnects_total counter",
        f"{prefix}_reconnects_total{label_text} {health.reconnects}",
        f"# HELP {prefix}_run_errors_total Total run_once errors.",
        f"# TYPE {prefix}_run_errors_total counter",
        f"{prefix}_run_errors_total{label_text} {health.run_errors}",
        f"# HELP {prefix}_dispatched_total Total dispatched outbox rows.",
        f"# TYPE {prefix}_dispatched_total counter",
        f"{prefix}_dispatched_total{label_text} {health.total_dispatched}",
        f"# HELP {prefix}_retried_total Total retried outbox rows.",
        f"# TYPE {prefix}_retried_total counter",
        f"{prefix}_retried_total{label_text} {health.total_retried}",
        f"# HELP {prefix}_dead_total Total dead-lettered outbox rows.",
        f"# TYPE {prefix}_dead_total counter",
        f"{prefix}_dead_total{label_text} {health.total_dead}",
        f"# HELP {prefix}_no_handler_total Total rows dead-lettered because no handler was registered.",
        f"# TYPE {prefix}_no_handler_total counter",
        f"{prefix}_no_handler_total{label_text} {health.total_no_handler}",
    ]
    return "\n".join(lines) + "\n"


def _format_labels(labels: Mapping[str, str]) -> str:
    if not labels:
        return ""
    parts = [
        f'{key}="{_escape_label_value(value)}"'
        for key, value in sorted(labels.items())
    ]
    return "{" + ",".join(parts) + "}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
