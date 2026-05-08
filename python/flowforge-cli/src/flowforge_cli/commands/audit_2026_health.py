"""``flowforge audit-2026 health`` — release-health probe.

Pivot from the original Grafana-dashboard-per-fix plan: this stack does
not run Grafana. Operators get the same per-ticket release-health view
by running this CLI against any Prometheus endpoint that scrapes a
deployed flowforge process.

Per-ticket SLI thresholds mirror what the audit-2026 close-out criteria
demand (`framework/docs/audit-fix-plan.md` §10.3). Each SLI maps to one
or more PromQL queries; the command prints PASS / WARN / FAIL per
ticket and exits non-zero on any FAIL.

Reference: ``framework/docs/audit-2026/close-out.md`` criterion 8;
``framework/tests/observability/promql/audit-2026.yml`` for the
complementary alert rules that fire automatically in Alertmanager.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import typer


@dataclass
class _Probe:
	"""One PromQL probe with its acceptance threshold."""

	expr: str
	#: Human-readable description shown in the report.
	label: str
	#: Maximum tolerated value. ``None`` means: any non-error value
	#: is acceptable (info probe).
	max_value: float | None = None
	#: When True, the probe FAILs the ticket. When False, it WARNs.
	required: bool = True


@dataclass
class _TicketHealth:
	ticket: str
	title: str
	probes: list[_Probe] = field(default_factory=list)


_TICKETS: list[_TicketHealth] = [
	_TicketHealth(
		ticket="E-32",
		title="Engine hotfix: concurrency + outbox safety",
		probes=[
			_Probe(
				"flowforge_audit_chain_breaks_total",
				"audit chain breaks (must stay 0)",
				max_value=0,
				required=True,
			),
			_Probe(
				"sum(rate(flowforge_engine_fire_rejected_concurrent_total[5m]))",
				"concurrent-fire rejections (informational)",
				required=False,
			),
		],
	),
	_TicketHealth(
		ticket="E-34",
		title="Crypto rotation (HMAC default removal)",
		probes=[
			_Probe(
				"flowforge_signing_secret_default_used_total",
				"hosts using insecure-default secret (must stay 0)",
				max_value=0,
				required=True,
			),
		],
	),
	_TicketHealth(
		ticket="E-35",
		title="Frozen op registry + arity",
		probes=[
			_Probe(
				"sum(flowforge_op_registry_frozen_errors_total)",
				"post-startup register attempts (must stay 0)",
				max_value=0,
				required=True,
			),
		],
	),
	_TicketHealth(
		ticket="E-36",
		title="Tenancy SQL hardening",
		probes=[
			_Probe(
				"sum(flowforge_tenancy_invalid_guc_key_total)",
				"invalid GUC key attempts",
				required=False,
			),
		],
	),
	_TicketHealth(
		ticket="E-37",
		title="Audit-chain hardening",
		probes=[
			_Probe(
				"flowforge_audit_chain_breaks_total",
				"audit chain breaks (must stay 0)",
				max_value=0,
				required=True,
			),
			_Probe(
				"flowforge_audit_record_unique_violation_total",
				"tenant-ordinal unique violations (must stay 0)",
				max_value=0,
				required=True,
			),
		],
	),
	_TicketHealth(
		ticket="E-37b",
		title="Hub trust gate (signed_at_publish)",
		probes=[
			_Probe(
				"sum(rate(flowforge_jtbd_hub_package_install_unsigned_total[5m]))",
				"unsigned-package install attempts (informational)",
				required=False,
			),
		],
	),
	_TicketHealth(
		ticket="E-38",
		title="Migration RLS DDL safety",
		probes=[
			_Probe(
				"flowforge_migration_table_allowlist_rejections_total",
				"migration table-allowlist rejections (must stay 0)",
				max_value=0,
				required=True,
			),
		],
	),
	_TicketHealth(
		ticket="E-41",
		title="FastAPI + WS hardening",
		probes=[
			_Probe(
				"sum(flowforge_fastapi_csrf_config_error_total)",
				"CSRF config errors (must stay 0)",
				max_value=0,
				required=True,
			),
			_Probe(
				"sum(flowforge_fastapi_hub_cross_app_leak_total)",
				"cross-app hub leakage (must stay 0)",
				max_value=0,
				required=True,
			),
		],
	),
	_TicketHealth(
		ticket="E-58",
		title="Hub residual (counter, verify cache, admin rotation)",
		probes=[
			_Probe(
				"max(flowforge_jtbd_hub_admin_legacy_token_uses_total)",
				"legacy admin token uses (informational)",
				required=False,
			),
		],
	),
]


def _query_prom(prom_url: str, expr: str, *, timeout: float = 10.0) -> tuple[bool, float | None, str]:
	"""Execute a PromQL instant-query.

	Returns ``(ok, value, message)`` where ``value`` is the summed scalar
	across all returned series (None if no data) and ``message`` is the
	error text on transport failure.
	"""

	url = f"{prom_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expr})}"
	try:
		with urllib.request.urlopen(url, timeout=timeout) as resp:
			body = resp.read().decode("utf-8")
	except (urllib.error.URLError, TimeoutError) as exc:
		return (False, None, f"prometheus query transport error: {exc}")
	try:
		parsed = json.loads(body)
	except ValueError as exc:
		return (False, None, f"prometheus response not JSON: {exc}")

	if parsed.get("status") != "success":
		return (False, None, f"prometheus query failed: {parsed!r}")

	results = parsed.get("data", {}).get("result", [])
	if not results:
		return (True, None, "no series")

	total = 0.0
	for series in results:
		try:
			total += float(series["value"][1])
		except (KeyError, IndexError, TypeError, ValueError):
			return (False, None, f"prometheus series unparseable: {series!r}")
	return (True, total, "")


def _evaluate_probe(prom_url: str, probe: _Probe) -> tuple[str, str]:
	"""Run one probe, return ``(verdict, line)`` where verdict is
	``"pass"`` / ``"warn"`` / ``"fail"``."""

	ok, value, msg = _query_prom(prom_url, probe.expr)
	if not ok:
		# Transport / parse error — treat as WARN unless probe required.
		verdict = "fail" if probe.required else "warn"
		return (verdict, f"  [{verdict.upper()}] {probe.label}: {msg}")
	if value is None:
		# Empty result. Acceptable for "must stay 0" — no data means no
		# violation. Acceptable for informational probes too.
		return ("pass", f"  [PASS] {probe.label}: no data (acceptable)")
	if probe.max_value is not None and value > probe.max_value:
		verdict = "fail" if probe.required else "warn"
		return (
			verdict,
			f"  [{verdict.upper()}] {probe.label}: value={value} exceeds threshold={probe.max_value}",
		)
	return ("pass", f"  [PASS] {probe.label}: value={value}")


def _evaluate_ticket(prom_url: str, th: _TicketHealth) -> tuple[str, list[str]]:
	"""Return ``(verdict, lines)`` for one ticket."""

	lines = [f"{th.ticket} — {th.title}"]
	worst = "pass"
	for probe in th.probes:
		verdict, line = _evaluate_probe(prom_url, probe)
		lines.append(line)
		if verdict == "fail" or (verdict == "warn" and worst == "pass"):
			worst = verdict
	return (worst, lines)


def audit_2026_health_cmd(
	prom_url: str = typer.Option(
		"http://prometheus.flowforge.local:9090",
		"--prom-url",
		envvar="FLOWFORGE_PROM_URL",
		help="Prometheus base URL (no trailing /api/v1).",
	),
	ticket: str | None = typer.Option(
		None,
		"--ticket",
		help="Restrict the probe to one ticket (e.g. E-32).",
	),
	output_json: bool = typer.Option(
		False,
		"--json",
		help="Emit a structured JSON report instead of human-readable text.",
	),
) -> None:
	"""Probe Prometheus for the audit-2026 release-health SLIs and report PASS/WARN/FAIL per ticket.

	Exits 0 if every required probe passes (warnings allowed); exits 1
	if any required probe FAILs. Designed to run as a periodic ops cron
	or post-deploy gate. Replaces the never-deployed Grafana-dashboard
	approach from plan §10.1.
	"""

	tickets = (
		[t for t in _TICKETS if t.ticket == ticket]
		if ticket
		else _TICKETS
	)
	if not tickets:
		typer.echo(f"unknown ticket {ticket!r}; valid: {[t.ticket for t in _TICKETS]}", err=True)
		raise typer.Exit(code=2)

	if output_json:
		report: dict[str, Any] = {"prom_url": prom_url, "tickets": []}
		any_fail = False
		for th in tickets:
			verdict, lines = _evaluate_ticket(prom_url, th)
			report["tickets"].append({"ticket": th.ticket, "title": th.title, "verdict": verdict, "lines": lines})
			if verdict == "fail":
				any_fail = True
		typer.echo(json.dumps(report, indent="\t"))
		raise typer.Exit(code=1 if any_fail else 0)

	typer.echo(f"audit-2026 release-health: prom={prom_url}\n")
	any_fail = False
	for th in tickets:
		verdict, lines = _evaluate_ticket(prom_url, th)
		for ln in lines:
			typer.echo(ln)
		typer.echo(f"  -> {verdict.upper()}\n")
		if verdict == "fail":
			any_fail = True

	if any_fail:
		typer.echo("audit-2026 health: FAIL — required probe(s) above threshold.", err=True)
		raise typer.Exit(code=1)
	typer.echo("audit-2026 health: OK")


def register(app: typer.Typer) -> None:
	"""Mount ``flowforge audit-2026 health`` on the root app via a sub-typer."""

	# audit-2026 subcommand group; mirrors the existing ``audit`` group
	# from main.py without conflicting (audit-2026 is its own namespace).
	subapp = typer.Typer(
		name="audit-2026",
		help="Audit-2026 release-health tooling (close-out criterion 8).",
		no_args_is_help=True,
	)
	subapp.command("health")(audit_2026_health_cmd)
	app.add_typer(subapp, name="audit-2026")


__all__ = ["register", "audit_2026_health_cmd"]
