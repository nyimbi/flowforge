"""Per-JTBD SLA stress harness — k6 + Locust scripts.

W4a / item 5 of :doc:`docs/improvements`. For every JTBD that declares
an ``sla.breach_seconds`` budget, emit a sibling pair of load-test
scripts at ``backend/tests/load/<jtbd>/{k6_test.js, locust_test.py}``.
The harnesses fire ``POST /<url_segment>/events`` at the rate implied
by the breach budget and assert per-event p95 latency stays under a
deterministic threshold derived from the same budget. Skip silently
for JTBDs without ``sla.breach_seconds`` so the bundle's existing
generator output stays byte-identical.

Why this generator exists
-------------------------

SLAs declared in bundles are aspirational unless tested. The framework
already produces deterministic synthetic load (the ``simulate``
command); the gap is the harness format. Emitting the harness once per
JTBD makes the budget empirically testable on every bundle revision.
The harnesses default to the in-memory port-fakes harness URL so local
loops are fast; an operator can re-point at a staging URL by setting
``TARGET=https://staging.example.com``.

Cadence
-------

The make target ``audit-2026-sla-stress`` runs **nightly** (the
GitHub Actions workflow's ``schedule:`` cron), not per-PR. Per-PR runs
would be both too slow (the harnesses are 30s each × every JTBD with
SLA) and too flaky (k6 / Locust binaries aren't on the per-PR runner
matrix). See ``docs/v0.3.0-engineering-plan.md`` §10 — "SLA stress
harness (item 5) runs nightly; not per-PR."

Output shape
------------

* ``backend/tests/load/<jtbd>/k6_test.js`` — k6 script. Uses two-space
  indentation per the prevailing JS convention.
* ``backend/tests/load/<jtbd>/locust_test.py`` — Locust script. Uses
  tabs per the project Python convention; emits a
  ``test_stop`` listener that asserts p95 < threshold and exits
  non-zero on breach.

Determinism
-----------

Pure-functional string assembly (no Jinja2 template, no random IDs,
no timestamps). The derived ``(vus, p95_ms, budget_ms)`` triple is a
total deterministic function of ``sla.breach_seconds``. Two regens
against the same bundle produce byte-identical output, so
``scripts/check_all.sh`` step 8 stays green and the regen-diff gate
passes for both ``form_renderer`` flag values (the SLA harness is
invariant to that flag).
"""

from __future__ import annotations

from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the generator-coverage test asserts
# they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].class_name",
	"jtbds[].id",
	"jtbds[].module_name",
	"jtbds[].sla_breach_seconds",
	"jtbds[].title",
	"jtbds[].url_segment",
	"project.package",
)


# ---------------------------------------------------------------------------
# load-parameter derivation
# ---------------------------------------------------------------------------


# Default in-memory port-fakes harness URL. Hosts override via the
# ``TARGET`` env var (``k6 run --env TARGET=https://staging.example.com``,
# ``locust --host https://staging.example.com``).
_DEFAULT_TARGET = "http://127.0.0.1:8765"


def _derive_load_params(breach_seconds: int) -> tuple[int, int, int]:
	"""Return ``(vus, p95_ms, budget_ms)`` from the SLA breach budget.

	* ``vus`` — virtual users / concurrent firers. Short budgets get more
	  pressure (the workflow has less slack), long budgets get less.
	  Bucketed so two adjacent budgets in the same bucket emit the same
	  VU count, keeping the harness easy to reason about.
	* ``p95_ms`` — per-event POST latency ceiling. The workflow budget
	  applies to *workflow completion*, not to a single event POST; the
	  POST itself should be 1% of the budget (one decision evaluation +
	  one outbox enqueue + audit append). Floor at 100ms (k6/Locust
	  noise floor on shared CI runners), ceiling at 2000ms (long-budget
	  workflows still want sub-2s event ingestion).
	* ``budget_ms`` — the workflow budget in milliseconds, recorded in
	  the harness output so an operator inspecting the script can
	  cross-reference the bundle's ``sla.breach_seconds``.
	"""

	assert isinstance(breach_seconds, int), "breach_seconds must be an int"
	assert breach_seconds > 0, "breach_seconds must be positive (skip-silently is the caller's job)"
	budget_ms = breach_seconds * 1000
	if breach_seconds <= 60:
		vus = 50
	elif breach_seconds <= 3600:
		vus = 25
	else:
		vus = 10
	# 1% of budget, clamped to [100ms, 2000ms]. Integer division keeps
	# the threshold deterministic across Python versions.
	p95_ms = max(100, min(2000, budget_ms // 100))
	return vus, p95_ms, budget_ms


def _format_budget(seconds: int) -> str:
	"""Render a budget in the largest whole-unit string ("24h", "5m", "30s")."""

	assert isinstance(seconds, int), "seconds must be an int"
	if seconds % 3600 == 0:
		return f"{seconds // 3600}h"
	if seconds % 60 == 0:
		return f"{seconds // 60}m"
	return f"{seconds}s"


# ---------------------------------------------------------------------------
# k6 emission
# ---------------------------------------------------------------------------


def build_k6(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> str:
	"""Build the k6 script for *jtbd*. Pure: same input → same output.

	The script uses two-space indentation (the prevailing convention in
	k6 docs and in the ``js/`` workspace) and ends with a trailing
	newline so the file is POSIX-friendly.
	"""

	assert jtbd.sla_breach_seconds is not None, "caller must skip JTBDs without SLA"
	breach = int(jtbd.sla_breach_seconds)
	vus, p95_ms, budget_ms = _derive_load_params(breach)
	pretty = _format_budget(breach)
	# Build line-by-line so the indentation stays explicit and the
	# template is easy to audit. Two-space indent for JS.
	lines: list[str] = [
		"// Generated by flowforge — do not edit. Regen with `flowforge jtbd-generate`.",
		"//",
		f"// SLA stress harness for {jtbd.id} ({bundle.project.package}).",
		f"// Workflow breach budget: {breach}s ({pretty}).",
		f"// Per-event p95 ceiling: {p95_ms}ms (1% of budget, clamped to [100, 2000]).",
		"//",
		"// Cadence: nightly via `make audit-2026-sla-stress`. Not per-PR (too slow,",
		"// runner does not have k6 in the per-PR matrix).",
		"//",
		"// Default TARGET points at the in-memory port-fakes harness so local loops",
		"// stay fast. Re-point at a staging URL by setting the TARGET env var:",
		"//   k6 run --env TARGET=https://staging.example.com k6_test.js",
		"",
		"import http from 'k6/http';",
		"import { check, sleep } from 'k6';",
		"import { Counter, Trend } from 'k6/metrics';",
		"",
		f"const TARGET = __ENV.TARGET || '{_DEFAULT_TARGET}';",
		"const TENANT_ID = __ENV.TENANT_ID || 'sla-stress-tenant';",
		f"const BUDGET_MS = {budget_ms};",
		f"const P95_MS = {p95_ms};",
		"",
		"export const options = {",
		f"  vus: {vus},",
		"  duration: '30s',",
		"  thresholds: {",
		"    http_req_failed: ['rate<0.01'],",
		f"    http_req_duration: ['p(95)<{p95_ms}'],",
		"    sla_breaches: ['count<1'],",
		"  },",
		"};",
		"",
		"const breaches = new Counter('sla_breaches');",
		"const fireLatency = new Trend('fire_latency_ms');",
		"",
		"export default function () {",
		f"  const url = `${{TARGET}}/{jtbd.url_segment}/events`;",
		"  const payload = JSON.stringify({",
		"    event: 'submit',",
		"    payload: {},",
		"    tenant_id: TENANT_ID,",
		"  });",
		"  const params = {",
		"    headers: {",
		"      'Content-Type': 'application/json',",
		"      'Idempotency-Key': `k6-${__VU}-${__ITER}`,",
		"    },",
		"  };",
		"  const res = http.post(url, payload, params);",
		"  fireLatency.add(res.timings.duration);",
		"  if (res.timings.duration > P95_MS) {",
		"    breaches.add(1);",
		"  }",
		"  check(res, {",
		"    'status 2xx': (r) => r.status >= 200 && r.status < 300,",
		"  });",
		"  sleep(1);",
		"}",
	]
	return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Locust emission
# ---------------------------------------------------------------------------


def build_locust(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> str:
	"""Build the Locust script for *jtbd*. Pure: same input → same output.

	The script uses tabs (project convention) and ends with a trailing
	newline. ``test_stop`` listener asserts p95 < threshold and sets
	``environment.process_exit_code = 1`` on breach so a CI run captures
	the failure.
	"""

	assert jtbd.sla_breach_seconds is not None, "caller must skip JTBDs without SLA"
	breach = int(jtbd.sla_breach_seconds)
	vus, p95_ms, budget_ms = _derive_load_params(breach)
	pretty = _format_budget(breach)
	cls = f"{jtbd.class_name}SlaUser"
	# Tabs for indentation; explicit list of lines for auditability.
	lines: list[str] = [
		f'"""SLA stress harness for {jtbd.id} ({bundle.project.package}).',
		"",
		"Generated by flowforge — do not edit. Regen with ``flowforge jtbd-generate``.",
		"",
		f"Workflow breach budget: {breach}s ({pretty}).",
		f"Per-event p95 ceiling: {p95_ms}ms (1% of budget, clamped to [100, 2000]).",
		"",
		"Cadence: nightly via ``make audit-2026-sla-stress``. Not per-PR.",
		"",
		"Usage::",
		"",
		f"\tlocust -f locust_test.py --headless -u {vus} -r {max(1, vus // 5)} -t 30s \\",
		f"\t\t--host \"$TARGET\"  # default in-memory: {_DEFAULT_TARGET}",
		'"""',
		"",
		"from __future__ import annotations",
		"",
		"import os",
		"",
		"from locust import HttpUser, between, events, task",
		"",
		"",
		'_TENANT_ID = os.environ.get("TENANT_ID", "sla-stress-tenant")',
		f"_BUDGET_MS = {budget_ms}",
		f"_P95_MS = {p95_ms}",
		"",
		"",
		f"class {cls}(HttpUser):",
		f'\t"""Fires ``POST /{jtbd.url_segment}/events`` at the SLA-implied rate."""',
		"",
		"\twait_time = between(0.5, 1.5)",
		"",
		"\t@task",
		"\tdef fire_event(self) -> None:",
		"\t\tself.client.post(",
		f'\t\t\t"/{jtbd.url_segment}/events",',
		'\t\t\tjson={"event": "submit", "payload": {}, "tenant_id": _TENANT_ID},',
		'\t\t\theaders={"Idempotency-Key": f"locust-{id(self)}-{self.environment.runner.user_count}"},',
		"\t\t)",
		"",
		"",
		"@events.test_stop.add_listener",
		"def _assert_p95(environment, **_kwargs: object) -> None:",
		'\t"""Assert p95 < threshold; exit non-zero on breach so CI captures it."""',
		"",
		"\tstats = environment.stats.total",
		"\tp95 = stats.get_response_time_percentile(0.95)",
		"\tif p95 is None:",
		"\t\treturn",
		"\tif p95 > _P95_MS:",
		"\t\tenvironment.process_exit_code = 1",
		'\t\tprint(f"SLA STRESS FAIL: p95={p95}ms > threshold={_P95_MS}ms (budget={_BUDGET_MS}ms)")',
		"\t\treturn",
		'\tprint(f"SLA STRESS OK: p95={p95}ms <= threshold={_P95_MS}ms (budget={_BUDGET_MS}ms)")',
	]
	return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# public api
# ---------------------------------------------------------------------------


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> list[GeneratedFile]:
	"""Emit ``backend/tests/load/<jtbd>/{k6_test.js,locust_test.py}``.

	Returns an empty list when ``jtbd.sla_breach_seconds`` is not set —
	the harness is meaningless without a budget, and skipping silently
	keeps existing fixtures byte-identical for SLA-less JTBDs.
	"""

	if jtbd.sla_breach_seconds is None:
		return []
	k6_content = build_k6(bundle, jtbd)
	locust_content = build_locust(bundle, jtbd)
	base = f"backend/tests/load/{jtbd.module_name}"
	return [
		GeneratedFile(path=f"{base}/k6_test.js", content=k6_content),
		GeneratedFile(path=f"{base}/locust_test.py", content=locust_content),
	]
