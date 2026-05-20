from __future__ import annotations

import json
import urllib.error

import pytest
import typer
from typer.testing import CliRunner

from flowforge_cli.commands import audit_2026_health
from flowforge_cli.commands.audit_2026_health import _Probe, _TicketHealth
from flowforge_cli.main import app


runner = CliRunner()


class _Response:
	def __init__(self, payload: str) -> None:
		self._payload = payload

	def __enter__(self) -> "_Response":
		return self

	def __exit__(self, *_args: object) -> None:
		return None

	def read(self) -> bytes:
		return self._payload.encode("utf-8")


@pytest.mark.parametrize(
	("payload", "expected"),
	[
		("not json", (False, None, "prometheus response not JSON")),
		(json.dumps({"status": "error", "error": "bad query"}), (False, None, "prometheus query failed")),
		(json.dumps({"status": "success", "data": {"result": []}}), (True, None, "no series")),
		(
			json.dumps(
				{
					"status": "success",
					"data": {
						"result": [
							{"value": [1, "2.5"]},
							{"value": [1, "3.5"]},
						]
					},
				}
			),
			(True, 6.0, ""),
		),
		(
			json.dumps({"status": "success", "data": {"result": [{"value": [1]}]}}),
			(False, None, "prometheus series unparseable"),
		),
	],
)
def test_query_prom_handles_prometheus_response_shapes(
	monkeypatch: pytest.MonkeyPatch,
	payload: str,
	expected: tuple[bool, float | None, str],
) -> None:
	def fake_urlopen(url: str, *, timeout: float) -> _Response:
		assert url == "http://prom/api/v1/query?query=up"
		assert timeout == 2.5
		return _Response(payload)

	monkeypatch.setattr(audit_2026_health.urllib.request, "urlopen", fake_urlopen)

	ok, value, message = audit_2026_health._query_prom("http://prom/", "up", timeout=2.5)

	assert (ok, value) == expected[:2]
	assert expected[2] in message


def test_query_prom_reports_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
	def fake_urlopen(_url: str, *, timeout: float) -> _Response:
		assert timeout == 10.0
		raise urllib.error.URLError("down")

	monkeypatch.setattr(audit_2026_health.urllib.request, "urlopen", fake_urlopen)

	ok, value, message = audit_2026_health._query_prom("http://prom", "up")

	assert ok is False
	assert value is None
	assert "prometheus query transport error" in message


@pytest.mark.parametrize(
	("probe", "query_result", "expected_verdict", "expected_text"),
	[
		(_Probe("up", "required metric", required=True), (False, None, "boom"), "fail", "[FAIL]"),
		(_Probe("up", "optional metric", required=False), (False, None, "boom"), "warn", "[WARN]"),
		(_Probe("up", "empty metric", max_value=0), (True, None, "no series"), "pass", "no data"),
		(_Probe("up", "over threshold", max_value=0, required=True), (True, 1.0, ""), "fail", "exceeds"),
		(_Probe("up", "optional threshold", max_value=0, required=False), (True, 1.0, ""), "warn", "exceeds"),
		(_Probe("up", "under threshold", max_value=1), (True, 1.0, ""), "pass", "value=1.0"),
	],
)
def test_evaluate_probe_maps_query_results_to_verdicts(
	monkeypatch: pytest.MonkeyPatch,
	probe: _Probe,
	query_result: tuple[bool, float | None, str],
	expected_verdict: str,
	expected_text: str,
) -> None:
	monkeypatch.setattr(audit_2026_health, "_query_prom", lambda *_args, **_kwargs: query_result)

	verdict, line = audit_2026_health._evaluate_probe("http://prom", probe)

	assert verdict == expected_verdict
	assert expected_text in line


def test_evaluate_ticket_keeps_worst_probe_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
	results = iter(
		[
			("pass", "  [PASS] first"),
			("warn", "  [WARN] second"),
			("fail", "  [FAIL] third"),
		]
	)
	ticket = _TicketHealth("E-X", "Synthetic ticket", [_Probe("a", "a"), _Probe("b", "b"), _Probe("c", "c")])
	monkeypatch.setattr(audit_2026_health, "_evaluate_probe", lambda *_args, **_kwargs: next(results))

	verdict, lines = audit_2026_health._evaluate_ticket("http://prom", ticket)

	assert verdict == "fail"
	assert lines == ["E-X \u2014 Synthetic ticket", "  [PASS] first", "  [WARN] second", "  [FAIL] third"]


def test_audit_2026_health_rejects_unknown_ticket() -> None:
	r = runner.invoke(app, ["audit-2026", "health", "--ticket", "NOPE"])

	assert r.exit_code == 2
	assert "unknown ticket 'NOPE'" in r.output


def test_audit_2026_health_json_exits_nonzero_on_required_failure(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_evaluate_ticket(_prom_url: str, ticket: _TicketHealth) -> tuple[str, list[str]]:
		return ("fail", [ticket.ticket, "  [FAIL] broken"])

	monkeypatch.setattr(audit_2026_health, "_evaluate_ticket", fake_evaluate_ticket)

	r = runner.invoke(app, ["audit-2026", "health", "--ticket", "E-32", "--json", "--prom-url", "http://prom"])

	assert r.exit_code == 1
	payload = json.loads(r.output)
	assert payload["prom_url"] == "http://prom"
	assert payload["tickets"][0]["ticket"] == "E-32"
	assert payload["tickets"][0]["verdict"] == "fail"


def test_audit_2026_health_json_exits_zero_when_all_required_probes_pass(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_evaluate_ticket(_prom_url: str, ticket: _TicketHealth) -> tuple[str, list[str]]:
		return ("pass", [ticket.ticket, "  [PASS] ok"])

	monkeypatch.setattr(audit_2026_health, "_evaluate_ticket", fake_evaluate_ticket)

	r = runner.invoke(app, ["audit-2026", "health", "--ticket", "E-32", "--json"])

	assert r.exit_code == 0
	payload = json.loads(r.output)
	assert payload["tickets"][0]["verdict"] == "pass"


def test_audit_2026_health_human_output_reports_ok(monkeypatch: pytest.MonkeyPatch) -> None:
	def fake_evaluate_ticket(_prom_url: str, ticket: _TicketHealth) -> tuple[str, list[str]]:
		return ("warn", [ticket.ticket, "  [WARN] optional probe unavailable"])

	monkeypatch.setattr(audit_2026_health, "_evaluate_ticket", fake_evaluate_ticket)

	r = runner.invoke(app, ["audit-2026", "health", "--ticket", "E-36", "--prom-url", "http://prom"])

	assert r.exit_code == 0
	assert "audit-2026 release-health: prom=http://prom" in r.output
	assert "-> WARN" in r.output
	assert "audit-2026 health: OK" in r.output


def test_audit_2026_health_human_output_fails_on_required_failure(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_evaluate_ticket(_prom_url: str, ticket: _TicketHealth) -> tuple[str, list[str]]:
		return ("fail", [ticket.ticket, "  [FAIL] required probe above threshold"])

	monkeypatch.setattr(audit_2026_health, "_evaluate_ticket", fake_evaluate_ticket)

	r = runner.invoke(app, ["audit-2026", "health", "--ticket", "E-41", "--prom-url", "http://prom"])

	assert r.exit_code == 1
	assert "-> FAIL" in r.output
	assert "audit-2026 health: FAIL" in r.output


def test_register_mounts_audit_2026_group() -> None:
	local_app = typer.Typer(add_completion=False)

	audit_2026_health.register(local_app)
	r = runner.invoke(local_app, ["audit-2026", "--help"])

	assert r.exit_code == 0
	assert "health" in r.output
