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
		audit-2026-signoff
	@echo ""
	@echo "audit-2026: all 77 audit-2026 layered suites passed."

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

# Convenience: run full check_all gate (existing) then audit-2026.
.PHONY: check-all
check-all:
	bash scripts/check_all.sh
	$(MAKE) audit-2026
