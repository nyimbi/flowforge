"""Tests for the SLA stress harness generator (W4a / item 5).

Verifies:

* Per-JTBD output paths land at ``backend/tests/load/<jtbd>/{k6_test.js,
  locust_test.py}`` exactly when ``sla.breach_seconds`` is set.
* JTBDs without ``sla.breach_seconds`` emit nothing (skip silently).
* Output is byte-deterministic across two consecutive renders.
* Both flag values of ``project.frontend.form_renderer`` produce the
  same SLA harness output (the SLA harness is invariant to the form
  renderer flag).
* k6 script syntax sanity: imports k6 modules, declares a stage block,
  carries a thresholds map.
* Locust script syntax sanity: imports locust, declares an HttpUser
  class, registers a test_stop listener.
* Derived load parameters (``vus``, ``p95_ms``) follow the budget-
  bucketed schedule documented in
  :func:`flowforge_cli.jtbd.generators.sla_loadtest._derive_load_params`.
* The generator's ``CONSUMES`` tuple matches the registry primer.
* Tabs (not spaces) in the emitted Locust script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import sla_loadtest as gen
from flowforge_cli.jtbd.normalize import normalize


_INSURANCE_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "insurance_claim"
	/ "jtbd-bundle.json"
)
_BUILDING_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "building-permit"
	/ "jtbd-bundle.json"
)
_HIRING_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "hiring-pipeline"
	/ "jtbd-bundle.json"
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


# ---------------------------------------------------------------------------
# emission shape — paths + skip-silently behaviour
# ---------------------------------------------------------------------------


def test_emits_pair_for_jtbd_with_sla() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	# claim_intake declares sla.breach_seconds=86400.
	assert jt.sla_breach_seconds == 86400
	files = gen.generate(bundle, jt)
	paths = sorted(f.path for f in files)
	assert paths == [
		"backend/tests/load/claim_intake/k6_test.js",
		"backend/tests/load/claim_intake/locust_test.py",
	]


def test_skips_silently_for_jtbd_without_sla() -> None:
	"""A JTBD without ``sla.breach_seconds`` emits no harness files.

	Every example bundle currently declares ``sla.breach_seconds`` on
	every JTBD (the building-permit / hiring-pipeline / insurance bundles
	all set the budget), so the skip-silently path is exercised by
	dropping the SLA block from a parsed example before re-normalizing.
	"""

	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	# Drop the SLA block from the only JTBD so sla_breach_seconds is None.
	raw["jtbds"][0].pop("sla", None)
	bundle = normalize(raw)
	(jt,) = bundle.jtbds
	assert jt.sla_breach_seconds is None
	files = gen.generate(bundle, jt)
	assert files == []


def test_pipeline_emits_pair_for_every_sla_jtbd() -> None:
	"""End-to-end: every JTBD with SLA gets a load-test pair, none extra."""

	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		bundle = _load_normalized(path)
		all_files = generate(raw)
		load_files = [f for f in all_files if f.path.startswith("backend/tests/load/")]
		# Two files per JTBD with SLA, zero for those without.
		expected = sum(2 for j in bundle.jtbds if j.sla_breach_seconds is not None)
		assert len(load_files) == expected, f"{path.name}: {len(load_files)} files (expected {expected})"
		# Skip-silently: no JTBD without SLA contributes.
		for j in bundle.jtbds:
			if j.sla_breach_seconds is None:
				assert all(j.module_name not in f.path for f in load_files), (
					f"{path.name}: {j.id} (no SLA) leaked a load-test file"
				)


# ---------------------------------------------------------------------------
# determinism + flag-flip invariance
# ---------------------------------------------------------------------------


def test_build_k6_is_byte_deterministic_per_jtbd() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		bundle = _load_normalized(path)
		for jt in bundle.jtbds:
			if jt.sla_breach_seconds is None:
				continue
			a = gen.build_k6(bundle, jt)
			b = gen.build_k6(bundle, jt)
			assert a == b, f"non-deterministic k6: {path.name}/{jt.id}"


def test_build_locust_is_byte_deterministic_per_jtbd() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		bundle = _load_normalized(path)
		for jt in bundle.jtbds:
			if jt.sla_breach_seconds is None:
				continue
			a = gen.build_locust(bundle, jt)
			b = gen.build_locust(bundle, jt)
			assert a == b, f"non-deterministic locust: {path.name}/{jt.id}"


def test_pipeline_is_byte_deterministic_for_examples() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		first = generate(raw)
		second = generate(raw)
		first_load = [f for f in first if f.path.startswith("backend/tests/load/")]
		second_load = [f for f in second if f.path.startswith("backend/tests/load/")]
		assert [f.path for f in first_load] == [f.path for f in second_load]
		for fa, fb in zip(first_load, second_load, strict=True):
			assert fa.content == fb.content, f"{path.name}: {fa.path} non-deterministic"


def test_form_renderer_flag_does_not_affect_sla_harness() -> None:
	"""Both ``form_renderer`` flag values produce identical SLA output.

	The SLA harness is invariant to the frontend Step.tsx emission path;
	this test pins that invariant so the regen-flag-flip gate
	(``scripts/ci/regen_flag_flip.sh``) keeps producing 6/6 byte-identical
	matches across the three examples × two flag values.
	"""

	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		# Skeleton form-renderer (default).
		raw_skel = json.loads(json.dumps(raw))
		raw_skel.setdefault("project", {}).setdefault("frontend", {})["form_renderer"] = "skeleton"
		# Real form-renderer.
		raw_real = json.loads(json.dumps(raw))
		raw_real.setdefault("project", {}).setdefault("frontend", {})["form_renderer"] = "real"
		skel_files = {
			f.path: f.content
			for f in generate(raw_skel)
			if f.path.startswith("backend/tests/load/")
		}
		real_files = {
			f.path: f.content
			for f in generate(raw_real)
			if f.path.startswith("backend/tests/load/")
		}
		assert skel_files == real_files, f"{path.name}: SLA harness drifted across form_renderer flag"


# ---------------------------------------------------------------------------
# k6 script syntax sanity
# ---------------------------------------------------------------------------


def test_k6_script_imports_required_modules() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	k6 = gen.build_k6(bundle, jt)
	assert "import http from 'k6/http';" in k6
	assert "import { check, sleep } from 'k6';" in k6
	assert "import { Counter, Trend } from 'k6/metrics';" in k6


def test_k6_script_declares_options_and_thresholds() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	k6 = gen.build_k6(bundle, jt)
	assert "export const options = {" in k6
	assert "thresholds: {" in k6
	assert "http_req_failed: ['rate<0.01']" in k6
	assert "http_req_duration: ['p(95)<" in k6
	assert "sla_breaches: ['count<1']" in k6


def test_k6_script_posts_to_correct_url_segment() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	k6 = gen.build_k6(bundle, jt)
	# url_segment for claim_intake is kebab-cased (matches existing router).
	assert f"/{jt.url_segment}/events" in k6
	assert "http.post(url, payload, params)" in k6


def test_k6_script_carries_idempotency_key_header() -> None:
	"""The harness must carry an Idempotency-Key so the stress run doesn't
	itself trigger ConcurrentFireRejected through the engine's per-instance
	serialisation."""

	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	k6 = gen.build_k6(bundle, jt)
	assert "'Idempotency-Key': `k6-${__VU}-${__ITER}`" in k6


def test_k6_script_default_target_is_in_memory_fakes() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	k6 = gen.build_k6(bundle, jt)
	# Default target points at the in-memory port-fakes harness; staging
	# repoint via the TARGET env var.
	assert "const TARGET = __ENV.TARGET || 'http://127.0.0.1:8765';" in k6


def test_k6_script_ends_with_newline() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	assert gen.build_k6(bundle, jt).endswith("\n")


# ---------------------------------------------------------------------------
# Locust script syntax sanity
# ---------------------------------------------------------------------------


def test_locust_script_imports_required_modules() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	loc = gen.build_locust(bundle, jt)
	assert "from locust import HttpUser, between, events, task" in loc


def test_locust_script_declares_httpuser_class() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	loc = gen.build_locust(bundle, jt)
	# Class name is JTBD class_name + SlaUser suffix.
	assert f"class {jt.class_name}SlaUser(HttpUser):" in loc
	assert "@task" in loc
	assert "wait_time = between(0.5, 1.5)" in loc


def test_locust_script_registers_test_stop_listener() -> None:
	"""The harness asserts p95 < threshold via a test_stop listener and
	exits non-zero on breach so a CI run captures the failure."""

	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	loc = gen.build_locust(bundle, jt)
	assert "@events.test_stop.add_listener" in loc
	assert "def _assert_p95(environment, **_kwargs: object) -> None:" in loc
	assert "environment.process_exit_code = 1" in loc
	assert "stats.get_response_time_percentile(0.95)" in loc


def test_locust_script_uses_tabs_not_spaces() -> None:
	"""Project Python convention: tabs, not spaces."""

	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	loc = gen.build_locust(bundle, jt)
	# Find at least one indented line inside the class body and confirm
	# it starts with a tab. The first indented line after ``class … :``
	# is the docstring or `wait_time`.
	lines = loc.splitlines()
	in_class = False
	saw_indented = False
	for ln in lines:
		if ln.startswith("class "):
			in_class = True
			continue
		if in_class and ln and ln[0].isspace():
			# First indented line in the class body — must lead with tab.
			assert ln.startswith("\t"), f"non-tab indent: {ln!r}"
			saw_indented = True
			break
	assert saw_indented, "no indented lines found inside the class body"
	# No four-space indents anywhere in the file.
	assert "\n    " not in loc, "four-space indent leaked into Locust script"


def test_locust_script_ends_with_newline() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	assert gen.build_locust(bundle, jt).endswith("\n")


# ---------------------------------------------------------------------------
# derived load parameters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
	"breach_seconds,expected_vus",
	[
		(30, 50),  # short budget — most pressure
		(60, 50),  # bucket boundary (still in short-budget bucket)
		(61, 25),  # next bucket
		(3600, 25),  # bucket boundary
		(3601, 10),  # long budget bucket
		(86400, 10),  # 24h
		(259200, 10),  # 72h
	],
)
def test_derive_load_params_vus_buckets(breach_seconds: int, expected_vus: int) -> None:
	vus, _, _ = gen._derive_load_params(breach_seconds)
	assert vus == expected_vus


@pytest.mark.parametrize(
	"breach_seconds,expected_p95_ms",
	[
		(30, 300),  # 30s budget × 1% = 300ms
		(60, 600),  # 60s budget × 1% = 600ms
		(120, 1200),  # under cap
		(200, 2000),  # at cap
		(86400, 2000),  # cap dominates for long budgets
		# Floor: a very short budget would compute below 100ms; clamp.
		(5, 100),
	],
)
def test_derive_load_params_p95_ms_clamp(
	breach_seconds: int, expected_p95_ms: int
) -> None:
	_, p95_ms, _ = gen._derive_load_params(breach_seconds)
	assert p95_ms == expected_p95_ms


def test_derive_load_params_budget_ms_passthrough() -> None:
	for s in (30, 60, 120, 86400, 259200):
		_, _, budget_ms = gen._derive_load_params(s)
		assert budget_ms == s * 1000


def test_format_budget_picks_largest_unit() -> None:
	assert gen._format_budget(86400) == "24h"
	assert gen._format_budget(3600) == "1h"
	assert gen._format_budget(60) == "1m"
	assert gen._format_budget(90) == "90s"
	assert gen._format_budget(259200) == "72h"


# ---------------------------------------------------------------------------
# fixture-registry coverage
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("sla_loadtest")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_sla_loadtest() -> None:
	assert "sla_loadtest" in _fixture_registry.all_generators()


# ---------------------------------------------------------------------------
# header content
# ---------------------------------------------------------------------------


def test_k6_header_carries_jtbd_id_and_budget() -> None:
	"""Operator-facing breadcrumb: the script header must name the JTBD id
	and the workflow budget so a 3am pager-out has the context."""

	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	k6 = gen.build_k6(bundle, jt)
	# claim_intake / 86400s / 24h.
	assert "SLA stress harness for claim_intake" in k6
	assert "86400s" in k6
	assert "24h" in k6


def test_locust_header_carries_jtbd_id_and_budget() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	loc = gen.build_locust(bundle, jt)
	assert "SLA stress harness for claim_intake" in loc
	assert "86400s" in loc
	assert "24h" in loc
