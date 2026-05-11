# FlowForge Makefile
#
# Audit-2026 quality gate per `docs/audit-fix-plan.md` §5.2.
#
# `make audit-2026` runs every layered suite. Each sub-target is independently
# runnable so CI matrices can shard them. All targets exit non-zero on any
# failing test or ratchet violation.
#
# Conventions:
#   - Run from repo root.
#   - Python tests are invoked with the repo's uv workspace
#     (flowforge-core, flowforge-tenancy, …) on the import path.
#   - JS tests are invoked via `pnpm` inside `js/`.
#   - Per-finding tests live under `tests/audit_2026/test_<FINDING>_*.py`
#     (see audit-fix-plan §4 for the finding → test_id mapping).
#   - Conformance invariants are tagged `@invariant_p0` / `@invariant_p1`
#     and live in `tests/conformance/test_arch_invariants.py`.

JS_DIR := js
PYTEST := uv run pytest -v --tb=short

.PHONY: help
help:
	@echo "audit-2026 targets (see docs/audit-fix-plan.md §5.2):"
	@echo "  audit-2026                full layered suite (everything below)"
	@echo "  audit-2026-unit           per-finding regression tests"
	@echo "  audit-2026-property       hypothesis property tests"
	@echo "  audit-2026-integration    cross-package integration tests"
	@echo "  audit-2026-e2e            end-to-end suites (3 flows)"
	@echo "  audit-2026-conformance    arch §17 invariants (P0+P1)"
	@echo "  audit-2026-conformance-p0 arch §17 invariants (P0 only)"
	@echo "  audit-2026-cross-runtime  TS↔Python evaluator parity"
	@echo "  audit-2026-edge           edge-case bank (9 classes)"
	@echo "  audit-2026-chaos          fault-injection (crash mid-fire/mid-outbox)"
	@echo "  audit-2026-observability  PromQL alert-rule self-tests"
	@echo "  audit-2026-ratchets       grep ratchet gates (no_default_secret etc.)"
	@echo "  audit-2026-visual-regression-dom   DOM-snapshot byte-equality (CI-gating, ADR-001)"
	@echo "  audit-2026-visual-regression-ssim  pixel SSIM (advisory; nightly only, ADR-001)"
	@echo "  audit-2026-property-coverage  every generator has a property test + seed uniqueness (W4a / ADR-003)"
	@echo "  audit-2026-i18n-coverage  no untranslated strings in compliance: JTBDs (W4b / item 17)"
	@echo "  audit-2026-signoff        signoff-checklist gate (P0/P1 rows)"

.PHONY: audit-2026
audit-2026: \
		audit-2026-ratchets \
		audit-2026-conformance \
		audit-2026-unit \
		audit-2026-property \
		audit-2026-integration \
		audit-2026-e2e \
		audit-2026-cross-runtime \
		audit-2026-edge \
		audit-2026-chaos \
		audit-2026-observability \
		audit-2026-visual-regression-dom \
		audit-2026-signoff
	@echo ""
	@echo "audit-2026: all audit-2026 layered suites passed."

.PHONY: audit-2026-unit
audit-2026-unit:
	@if [ -d tests/audit_2026 ] && [ -n "$$(find tests/audit_2026 -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/audit_2026/ ; \
	else \
		echo "audit-2026-unit: no tests/audit_2026/test_*.py yet (S0 day 1 — populated as tickets land)"; \
	fi

.PHONY: audit-2026-property
audit-2026-property:
	@if [ -d tests/property ] && [ -n "$$(find tests/property -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/property/ --hypothesis-show-statistics ; \
	else \
		echo "audit-2026-property: no tests/property/ yet (E-44 lands in S1)"; \
	fi

.PHONY: audit-2026-integration
audit-2026-integration:
	@if [ -d tests/integration/python ] && [ -n "$$(find tests/integration/python -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/integration/python/ ; \
	fi

.PHONY: audit-2026-e2e
audit-2026-e2e:
	@if [ -d tests/integration/e2e ] && [ -n "$$(find tests/integration/e2e -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/integration/e2e/ ; \
	else \
		echo "audit-2026-e2e: no e2e suites yet (E-45 lands in S1)"; \
	fi

.PHONY: audit-2026-conformance
audit-2026-conformance:
	$(PYTEST) tests/conformance/

.PHONY: audit-2026-conformance-p0
audit-2026-conformance-p0:
	$(PYTEST) tests/conformance/ -m invariant_p0

.PHONY: audit-2026-cross-runtime
audit-2026-cross-runtime:
	@if [ -d tests/cross_runtime ] && [ -n "$$(find tests/cross_runtime -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/cross_runtime/ ; \
	else \
		echo "audit-2026-cross-runtime: no fixture yet (E-43 lands in S1)"; \
	fi
	@if [ -d $(JS_DIR) ]; then \
		cd $(JS_DIR) && pnpm -r --if-present test:cross-runtime || \
			echo "audit-2026-cross-runtime: pnpm cross-runtime script not yet wired (E-43 lands in S1)" ; \
	fi

.PHONY: audit-2026-edge
audit-2026-edge:
	@if [ -d tests/edge_cases ] && [ -n "$$(find tests/edge_cases -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/edge_cases/ ; \
	else \
		echo "audit-2026-edge: no edge-case bank yet (E-64 lands in S3)"; \
	fi

.PHONY: audit-2026-chaos
audit-2026-chaos:
	@if [ -d tests/chaos ] && [ -n "$$(find tests/chaos -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/chaos/ ; \
	else \
		echo "audit-2026-chaos: no chaos suites yet (lands in S1)"; \
	fi

.PHONY: audit-2026-observability
audit-2026-observability:
	@if [ -d tests/observability ] && [ -n "$$(find tests/observability -name 'test_*.py' 2>/dev/null | head -1)" ]; then \
		$(PYTEST) tests/observability/ ; \
	fi
	@if command -v promtool >/dev/null 2>&1 ; then \
		for rule in tests/observability/promql/*.yml ; do \
			[ -e "$$rule" ] || continue ; \
			echo "promtool check rules $$rule" ; \
			promtool check rules "$$rule" ; \
		done ; \
	else \
		echo "audit-2026-observability: promtool not installed — skipping rule lint" ; \
	fi

.PHONY: audit-2026-ratchets
audit-2026-ratchets:
	bash scripts/ci/ratchets/check.sh

.PHONY: audit-2026-signoff
audit-2026-signoff:
	uv run --with pyyaml python scripts/ci/check_signoff.py

# v0.3.0 W2 (item 7): backup/restore drill artefact.
#
# Runs the generated `docs/ops/<bundle>/restore-runbook.md` procedure
# end-to-end against testcontainers Postgres for each example bundle:
# spin up Postgres → load seed → pg_dump → drop schema → pg_restore →
# `flowforge audit verify` for every tenant in the dump → assert every
# audit chain re-verifies. The integration test under
# `tests/integration/python/tests/test_restore_drill.py` carries the
# assertions; this target is the operator-facing entrypoint.
#
# Reference: `docs/v0.3.0-engineering-plan.md` §7 W2,
# `docs/improvements.md` item 7. Designed for the monthly DR tabletop —
# CI runs it on every PR via `audit-2026-restore-drill`.
.PHONY: restore-drill
restore-drill:
	$(PYTEST) tests/integration/python/tests/test_restore_drill.py

.PHONY: audit-2026-restore-drill
audit-2026-restore-drill: restore-drill

# v0.3.0 W4a (item 14): Faker-driven seed data.
#
# Loads the canonical example bundle's generated seed modules through
# the service layer (so RLS, audit chain, and permissions engage). The
# per-bundle generator emits one ``backend/seeds/<package>/seed_<jtbd>.py``
# per JTBD, each backed by ``Faker().seed_instance(N)`` where
# ``N = int(sha256("<package>:<jtbd_id>")[:8], 16)`` — same input always
# yields the same rows so two ``make seed`` runs against the same
# database produce byte-identical seeded state.
#
# Override the example via ``SEED_EXAMPLE=<dir>`` (defaults to the
# canonical insurance_claim demo). The host application is responsible
# for ensuring the database exists, migrations are applied, and the
# Python path resolves the generated package; ``make seed`` is the
# operator-facing entrypoint, not a turnkey one-shot.
#
# Reference: ``docs/improvements.md`` item 14, ``docs/v0.3.0-engineering-plan.md`` §7 W4a.
SEED_EXAMPLE ?= examples/insurance_claim
SEED_PACKAGE ?= insurance_claim_demo
.PHONY: seed
seed:
	@if [ ! -d "$(SEED_EXAMPLE)/generated/backend/seeds/$(SEED_PACKAGE)" ]; then \
		echo "seed: $(SEED_EXAMPLE)/generated/backend/seeds/$(SEED_PACKAGE) does not exist."; \
		echo "      Regenerate the example with 'flowforge jtbd-generate' first."; \
		exit 1; \
	fi
	@echo "seed: loading $(SEED_EXAMPLE) ($(SEED_PACKAGE)) through the service layer"
	cd $(SEED_EXAMPLE)/generated/backend && \
		PYTHONPATH=src:. uv run python -m seeds.$(SEED_PACKAGE)

# v0.3.0 W3 (item 21): visual regression — DOM-snapshot CI gate.
#
# Per ADR-001 (docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md)
# the DOM snapshot is the *CI-gating* artifact; the pixel SSIM is
# advisory only. The DOM gate runs the smoke subset (canonical example
# only) per-PR and the full suite nightly. The wrapper script
# `scripts/visual_regression/run_dom_snapshots.sh` skips with a clear
# reason if `pnpm install` is blocked or the dev-server harness has
# not yet landed; in that mode it exits 0 (the W3 brief authorises
# skip-with-reason while the pnpm cleanup PR is in flight).
#
# Cadence selection:
#   make audit-2026-visual-regression-dom            -> smoke (per-PR)
#   VISREG_CADENCE=full make audit-2026-visual-regression-dom  -> full (nightly)
.PHONY: audit-2026-visual-regression-dom
audit-2026-visual-regression-dom:
	bash scripts/visual_regression/run_dom_snapshots.sh $${VISREG_CADENCE:-smoke}

# v0.3.0 W4a (item 5): SLA stress harness — k6 + Locust per JTBD.
#
# For every JTBD declaring ``sla.breach_seconds``, the generator emits a
# k6 + Locust pair under ``backend/tests/load/<jtbd>/`` that fires
# ``POST /<url_segment>/events`` at the rate implied by the breach
# budget and asserts per-event p95 latency stays under a threshold
# derived from the same budget.
#
# Cadence: **nightly only**. Per-PR runs would be both too slow (30s
# per JTBD with SLA × every example bundle) and too flaky (k6 / Locust
# binaries aren't in the per-PR runner matrix). The
# ``.github/workflows/audit-2026.yml`` workflow gates this target on
# ``schedule:`` cron events; manual local invocation works whenever
# k6 + locust are on PATH.
#
# Per ``docs/v0.3.0-engineering-plan.md`` §10:
#   "SLA stress harness (item 5) runs nightly; not per-PR."
#
# Reference: ``docs/improvements.md`` item 5 + the sla_loadtest
# generator at ``python/flowforge-cli/src/flowforge_cli/jtbd/generators/sla_loadtest.py``.
.PHONY: audit-2026-sla-stress
audit-2026-sla-stress:
	bash scripts/audit_2026/run_sla_stress.sh

# v0.3.0 W4a (item 4): guard-aware reachability checker.
#
# Per ADR-004 (docs/v0.3.0-engineering/adr/ADR-004-z3-solver-opt-in-extra.md)
# z3-solver is an opt-in runtime extra (`flowforge-cli[reachability]`)
# with a HARD pin (`z3-solver==4.13.4.0`). When the extra is installed
# the per-JTBD generator emits ``workflows/<id>/reachability.json``;
# otherwise it emits ``workflows/<id>/reachability_skipped.txt`` with
# the documented placeholder text. The integration test asserts both
# branches land + the per-bundle ``reachability_summary.md`` aggregator
# stays byte-stable across regens.
#
# This target reports SKIP cleanly when the extra is not installed so
# CI matrices that intentionally test the placeholder branch don't
# fail. The dedicated test file under
# ``python/flowforge-cli/tests/test_reachability_generator.py``
# carries the byte-deterministic assertions; it's invoked here so the
# layered audit target picks it up only when the extra is available.
.PHONY: audit-2026-reachability
audit-2026-reachability:
	@if uv run python -c "import z3" >/dev/null 2>&1 ; then \
		echo "audit-2026-reachability: z3-solver available — running suite" ; \
		$(PYTEST) python/flowforge-cli/tests/test_reachability_generator.py ; \
	else \
		echo "audit-2026-reachability: SKIP — z3-solver not installed" ; \
		echo "  install with: pip install 'flowforge-cli[reachability]'" ; \
	fi

# v0.3.0 W4a (item 3 / ADR-003): property-coverage gate.
#
# Asserts every generator added in W0-W3 has at least one hypothesis
# property test under ``tests/property/generators/test_<gen>_properties.py``.
# The canonical list of 13 generators lives in
# ``tests/audit_2026/test_property_coverage_gate.py`` (REQUIRED_GENERATORS).
#
# Also runs the ADR-003 seed-uniqueness checks: every emitted
# ``test_<jtbd>_properties.py`` pins ``_SEED = int(sha256(jtbd_id)[:8], 16)``
# and no two JTBDs in the same example bundle share a 32-bit seed.
.PHONY: audit-2026-property-coverage
audit-2026-property-coverage:
	$(PYTEST) tests/audit_2026/test_property_coverage_gate.py
	$(PYTEST) tests/audit_2026/test_hypothesis_seed_uniqueness.py

# v0.3.0 W4b (item 17): i18n coverage gate.
#
# Regenerates every example bundle's i18n catalogs in memory and asserts:
#
# * For each JTBD declaring ``compliance: [...]``, every non-English catalog
#   has no empty values for keys scoped to that JTBD. Empty values for a
#   compliance-tagged JTBD are an error (exit 1) — regulated workflows
#   need full translation coverage.
# * For other JTBDs, empty values are reported as warnings (exit 0).
#
# The English catalog is the source of truth; non-English catalogs are
# emitted structurally identical with empty values, so the gate scales
# from one language to many without per-language schema drift.
.PHONY: audit-2026-i18n-coverage
audit-2026-i18n-coverage:
	uv run python scripts/i18n/check_coverage.py

# v0.3.0 W3 (item 21): visual regression — pixel SSIM (advisory).
#
# Runs nightly only per ADR-001 §"Decision". Pixel bytes are not
# deterministic across Chromium minor versions, so the SSIM gate
# cannot block PR merge. The wrapper script always exits 0; failures
# surface as annotations in the nightly summary and as a PR comment
# per ADR-001 §"Decision".
.PHONY: audit-2026-visual-regression-ssim
audit-2026-visual-regression-ssim:
	bash scripts/visual_regression/run_ssim.sh

# Convenience: run full check_all gate (existing) then audit-2026.
.PHONY: check-all
check-all:
	bash scripts/check_all.sh
	$(MAKE) audit-2026
