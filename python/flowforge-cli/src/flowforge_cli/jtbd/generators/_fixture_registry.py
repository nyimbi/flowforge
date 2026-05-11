"""Fixture-registry primer for v0.3.0 W0.

Declares which bundle/normalized fields each generator consumes so the
generator-fixture-coverage test (Pre-mortem Scenario 1 of
:doc:`docs/v0.3.0-engineering-plan` §5) can assert:

* **Forward**: at least one example bundle populates each declared field.
* **Reverse**: every ``bundle.<field>`` / ``jtbd.<field>`` attribute access
  in a generator under ``flowforge_cli/jtbd/generators/`` is declared
  here.

This file is the W0 *primer* — only the W0 generators register here for
now. The full bidirectional AST-walk test lands later (see executor
residual risk #2 in the v0.3.0 engineering plan).

Path grammar:

* ``project.<field>`` — bundle-level project field
* ``jtbds[].<field>`` — repeated per-JTBD field
* ``jtbds[].fields[].<field>`` — repeated field-of-JTBD subfield
* dotted path is matched verbatim against the dataclass attribute path

Adding a new entry: each generator that lands in
:mod:`flowforge_cli.jtbd.generators` MUST also expose a module-level
``CONSUMES: tuple[str, ...]`` re-stating the same paths, so a static
import in the test layer can verify the registry and the generator
agree.
"""

from __future__ import annotations


# Mapping: generator module name → tuple of dotted bundle/JTBD paths consumed.
# Sorted for deterministic iteration in the test layer.
_REGISTRY: dict[str, tuple[str, ...]] = {
	"analytics_taxonomy": (
		"jtbds[].id",
		"project.name",
		"project.package",
	),
	"compensation_handlers": (
		"jtbds[].edge_cases",
		"jtbds[].id",
	),
	"db_migration": (
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].required",
		"jtbds[].fields[].sa_type",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].table_name",
		"jtbds[].title",
		"project.package",
	),
	# v0.3.0 W3 / item 18 — design-token theming. Reads each
	# ``project.design.*`` field plus ``project.package`` to pick the
	# customer-facing + admin tree paths the six emitted files land at.
	# The ``project.design`` block is normalized into ``DEFAULT_DESIGN``
	# when missing, so the registry asserts the dotted access shape; the
	# field-coverage test exercises bundles that exercise both the
	# default and overridden paths.
	"design_tokens": (
		"project.design.accent",
		"project.design.density",
		"project.design.font_family",
		"project.design.primary",
		"project.design.radius_scale",
		"project.package",
	),
	"diagram": (
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].sla_breach_seconds",
		"jtbds[].states",
		"jtbds[].title",
		"jtbds[].transitions",
	),
	# v0.3.0 W2 / item 12 — OTel-by-construction templates pulled the
	# domain_router / domain_service / workflow_adapter generators into
	# the registry.  Span attributes derive from jtbd.id (tracer name +
	# attribute), initial_state (engine span attribute), module_name +
	# class_name + title (generated module identifiers).  The OTel
	# imports themselves are static template text and don't show up
	# here.
	"domain_router": (
		"jtbds[].class_name",
		"jtbds[].id",
		"jtbds[].module_name",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.package",
	),
	"domain_service": (
		"jtbds[].class_name",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].module_name",
		"jtbds[].title",
		"project.package",
	),
	"frontend": (
		"jtbds[].class_name",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].pii",
		"jtbds[].fields[].required",
		"jtbds[].fields[].validation",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.frontend.form_renderer",
		"project.package",
	),
	# v0.3.0 W2 / item 15 — per-bundle tenant-scoped admin console.
	# Reads project name/package/tenancy plus per-JTBD identifiers to
	# synthesize the admin permission catalog and label every page.
	# bundle.all_audit_topics seeds the audit-log viewer's topic list.
	"frontend_admin": (
		"all_audit_topics",
		"jtbds[].class_name",
		"jtbds[].id",
		"jtbds[].permissions",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.name",
		"project.package",
		"project.tenancy",
	),
	# v0.3.0 W3 / item 9 — Typer CLI client (frontend-cli/<package>/).
	# Mirrors the operations declared by the W1 ``openapi.yaml`` so the
	# command tree stays operationally pinned to the spec. Reads
	# ``jtbds[].transitions`` to derive the per-event Typer subcommand
	# tree and ``data_capture`` fields to materialise the per-command
	# Typer ``--`` options.
	"frontend_cli": (
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].required",
		"jtbds[].id",
		"jtbds[].title",
		"jtbds[].transitions",
		"jtbds[].url_segment",
		"project.name",
		"project.package",
	),
	# v0.3.0 W3 / item 9 — email-driven adapter shell
	# (frontend-email/<package>/). Routing skeleton only; hosts wire
	# IMAP/SMTP/SES/SendGrid bridges themselves. Reads
	# ``jtbds[].transitions`` to derive the closed reply-subject route
	# catalog and ``bundle.all_audit_topics`` to seed the outbound email
	# template registry.
	"frontend_email": (
		"all_audit_topics",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].label",
		"jtbds[].fields[].required",
		"jtbds[].id",
		"jtbds[].title",
		"jtbds[].transitions",
		"jtbds[].url_segment",
		"project.name",
		"project.package",
	),
	# v0.3.0 W3 / item 9 — Slack adapter shell
	# (frontend-slack/<package>/). Routing skeleton only; hosts wire
	# the concrete Slack bot (webhook, signing secret, identity bridge)
	# themselves. Reads ``jtbds[].transitions`` to derive the slash-
	# command catalog, ``jtbds[].permissions`` to pin per-command
	# permissions, and ``bundle.all_audit_topics`` to seed the
	# interactive-message template registry.
	"frontend_slack": (
		"all_audit_topics",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].label",
		"jtbds[].fields[].required",
		"jtbds[].id",
		"jtbds[].permissions",
		"jtbds[].title",
		"jtbds[].transitions",
		"jtbds[].url_segment",
		"project.name",
		"project.package",
	),
	# v0.3.0 W4b / item 17 — i18n scaffolding + empty-translation lint.
	# Per-bundle generator that emits ``frontend/src/<pkg>/i18n/<lang>.json``
	# (one per declared ``project.languages`` entry; default ``("en",)``)
	# plus a TS ``useT.ts`` hook bound to a string-literal union of every
	# key path. English catalog is populated; non-English catalogs are
	# structurally identical with empty values — the lint targets for
	# the ``audit-2026-i18n-coverage`` gate. Reads field labels, transition
	# events, audit-topic dotted ids, and SLA budgets to build the closed
	# key namespace.
	"i18n": (
		"jtbds[].audit_topics",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].label",
		"jtbds[].id",
		"jtbds[].sla_breach_seconds",
		"jtbds[].sla_warn_pct",
		"jtbds[].title",
		"jtbds[].transitions",
		"project.languages",
		"project.package",
	),
	"idempotency": (
		"jtbds[].class_name",
		"jtbds[].id",
		"jtbds[].module_name",
		"jtbds[].table_name",
		"project.idempotency.ttl_hours",
		"project.package",
	),
	# v0.3.0 W3 / item 11 — per-bundle data-lineage / provenance graph
	# (lineage.json at the bundle root). Reads every per-JTBD field to
	# trace it across the five generation-pipeline stages, plus the
	# JTBD-level compliance + data_sensitivity tags that drive the PII
	# retention window. ``project.lineage.retention_years`` is the
	# bundle-wide override that pins the retention window when present.
	"lineage": (
		"jtbds[].audit_topics",
		"jtbds[].class_name",
		"jtbds[].compliance",
		"jtbds[].data_sensitivity",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].pii",
		"jtbds[].fields[].sa_type",
		"jtbds[].id",
		"jtbds[].module_name",
		"jtbds[].notifications",
		"jtbds[].permissions",
		"jtbds[].table_name",
		"jtbds[].title",
		"project.lineage.retention_years",
		"project.name",
		"project.package",
	),
	"migration_safety": (
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].required",
		"jtbds[].fields[].sa_type",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].table_name",
		"jtbds[].title",
		"project.package",
	),
	"openapi": (
		"jtbds[].audit_topics",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].required",
		"jtbds[].fields[].validation",
		"jtbds[].id",
		"jtbds[].permissions",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.name",
	),
	# v0.3.0 W4b / item 20 — per-JTBD operator manual emitted as MDX
	# under ``docs/jtbd/<id>.mdx``. Reads the JTBD's authored prose
	# (situation / motivation / outcome / success_criteria) plus the
	# synthesised form fields, audit topics, and permission catalog. The
	# embedded mermaid source is computed through
	# :func:`generators.diagram.build_mmd` so the manual and the W1
	# ``diagram.mmd`` never drift on regen. ``project.name`` +
	# ``project.package`` thread the manual back to the cross-bundle
	# permission + audit-taxonomy artefacts.
	"operator_manual": (
		"jtbds[].actor_role",
		"jtbds[].audit_topics",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].pii",
		"jtbds[].fields[].required",
		"jtbds[].id",
		"jtbds[].motivation",
		"jtbds[].outcome",
		"jtbds[].permissions",
		"jtbds[].situation",
		"jtbds[].success_criteria",
		"jtbds[].title",
		"project.name",
		"project.package",
	),
	# v0.3.0 W4a / item 3 — per-JTBD hypothesis property suite (ADR-003).
	# Reads the JTBD id (seed input + module path), initial state (assertion
	# + context anchor), the synthesised state list (KNOWN_STATES /
	# TERMINAL_STATES) and transition list (event vocabulary + guard
	# variables). The seed contract pins ``@hypothesis.settings(seed=N,
	# derandomize=True, max_examples=200)`` where ``N = int(sha256
	# (jtbds[].id)[:8], 16)`` at generation time, so the seed is visible
	# in the emitted source and reproducible across hosts.
	"property_tests": (
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].module_name",
		"jtbds[].states",
		"jtbds[].transitions",
	),
	# v0.3.0 W4a / item 4 — guard-aware reachability checker. Reads
	# every transition's guards plus every data_capture field id so the
	# unwritable-variable probe can decide which guard reads no field
	# can populate. ``project.package`` is unread; the file path uses
	# ``jtbd.id`` only. The placeholder ``reachability_skipped.txt`` is
	# emitted when ``z3-solver`` is not installed (per ADR-004).
	"reachability": (
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].states",
		"jtbds[].title",
		"jtbds[].transitions",
	),
	# v0.3.0 W4a / item 4 — per-bundle aggregator. Same surface as the
	# per-JTBD generator: it re-derives the summary from the same
	# normalized bundle (no disk re-read), so the CONSUMES set mirrors
	# the per-JTBD generator's.
	"reachability_summary": (
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].states",
		"jtbds[].title",
		"jtbds[].transitions",
	),
	"restore_runbook": (
		"jtbds[].audit_topics",
		"jtbds[].id",
		"jtbds[].table_name",
		"jtbds[].title",
		"project.idempotency_ttl_hours",
		"project.name",
		"project.package",
		"project.tenancy",
	),
	# v0.3.0 W4a / item 14 — Faker-driven seed data. Per-bundle generator
	# that emits ``backend/seeds/<package>/seed_<jtbd>.py`` per JTBD plus
	# the ``__init__.py`` package marker. Faker is seeded deterministically
	# from ``int(sha256("<package>:<jtbd_id>")[:8], 16)`` so two regens
	# against the same bundle produce byte-identical seed modules and
	# byte-identical seed *rows* at runtime. Reads the JTBD identifier
	# surface (id / module_name / class_name / title) plus every
	# ``data_capture`` field (kind + label + validation feed the
	# field-kind → Faker dispatch) plus the synthesised states +
	# transitions (used to BFS each forward state's event path so the
	# seed loop drives entities through the service layer rather than
	# bypassing the engine).
	"seed_data": (
		"jtbds[].class_name",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].validation",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].module_name",
		"jtbds[].states",
		"jtbds[].title",
		"jtbds[].transitions",
		"project.package",
	),
	# v0.3.0 W4a / item 5 — per-JTBD k6 + Locust SLA stress harness.
	# Skips silently for JTBDs without ``sla.breach_seconds`` so existing
	# fixtures regen byte-identically. Reads the JTBD identifier surface
	# (id / module_name / class_name / url_segment / title) plus the SLA
	# budget itself; ``project.package`` is the only bundle-level field
	# (used in the script header comment for traceability). The harness
	# scripts run nightly via ``make audit-2026-sla-stress`` — never on
	# per-PR CI.
	"sla_loadtest": (
		"jtbds[].class_name",
		"jtbds[].id",
		"jtbds[].module_name",
		"jtbds[].sla_breach_seconds",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.package",
	),
	"workflow_adapter": (
		"jtbds[].id",
		"jtbds[].module_name",
		"jtbds[].title",
		"jtbds[].transitions",
		"project.package",
	),
}


def get(generator_name: str) -> tuple[str, ...]:
	"""Return the declared CONSUMES tuple for *generator_name*.

	Returns an empty tuple if the generator hasn't registered yet —
	intentionally permissive while the registry is still primed; the
	W0+ coverage test will harden this into a hard failure once every
	generator declares its CONSUMES.
	"""

	assert isinstance(generator_name, str), "generator_name must be a string"
	return _REGISTRY.get(generator_name, ())


def all_generators() -> tuple[str, ...]:
	"""Return the sorted list of generators registered here."""

	return tuple(sorted(_REGISTRY.keys()))


def register(generator_name: str, consumes: tuple[str, ...]) -> None:
	"""Test-only helper: register a generator's CONSUMES at runtime.

	Production code must declare CONSUMES at module load time. This is
	a hatch for tests that want to validate registry round-trips
	without polluting the global state across processes. Idempotent.
	"""

	assert isinstance(generator_name, str), "generator_name must be a string"
	assert isinstance(consumes, tuple), "consumes must be a tuple"
	_REGISTRY[generator_name] = tuple(sorted(consumes))
