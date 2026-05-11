"""Generator orchestrator.

Runs every generator in :mod:`flowforge_cli.jtbd.generators` against a
normalized bundle, collects their output, and returns a sorted list of
:class:`GeneratedFile` records. The CLI command is a thin wrapper that
writes the records to disk; the tests use the records directly so we
can assert on byte content without touching a filesystem.
"""

from __future__ import annotations

from typing import Any

from ._types import GeneratedFile
from .generators import (
	alembic,
	analytics_taxonomy,
	audit_taxonomy,
	compensation_handlers,
	db_migration,
	design_tokens,
	diagram,
	domain_router,
	domain_service,
	env_example,
	form_spec,
	frontend,
	frontend_admin,
	frontend_cli,
	frontend_email,
	frontend_slack,
	i18n,
	idempotency,
	lineage,
	migration_safety,
	notifications,
	openapi,
	operator_manual,
	permissions,
	property_tests,
	reachability,
	reachability_summary,
	readme,
	restore_runbook,
	sa_model,
	seed_data,
	sla_loadtest,
	tests as test_gen,
	workflow_adapter,
	workflow_def,
)
from .normalize import NormalizedBundle, normalize
from .overrides import JtbdCopyOverrides
from .parse import parse_bundle


__all__ = ["GeneratedFile", "generate", "generate_for_bundle"]


# Per-JTBD generators run once per JTBD; cross-bundle generators run once
# per bundle. The order here is the order the CLI prints when it writes,
# but the public ``generate`` API sorts by path before returning so the
# test snapshots stay stable regardless of dict iteration order.
_PER_JTBD_GENERATORS = (
	workflow_def.generate,
	form_spec.generate,
	sa_model.generate,
	db_migration.generate,
	workflow_adapter.generate,
	domain_service.generate,
	domain_router.generate,
	test_gen.generate,
	frontend.generate,
	compensation_handlers.generate,
	diagram.generate,
	idempotency.generate,
	reachability.generate,
	sla_loadtest.generate,
	property_tests.generate,
	operator_manual.generate,
)

_PER_BUNDLE_GENERATORS = (
	permissions.generate,
	audit_taxonomy.generate,
	analytics_taxonomy.generate,
	notifications.generate,
	alembic.generate,
	env_example.generate,
	readme.generate,
	migration_safety.generate,
	openapi.generate,
	restore_runbook.generate,
	frontend_admin.generate,
	frontend_cli.generate,
	frontend_email.generate,
	frontend_slack.generate,
	lineage.generate,
	design_tokens.generate,
	reachability_summary.generate,
	seed_data.generate,
	i18n.generate,
)


def generate(
	bundle: dict[str, Any],
	overrides: JtbdCopyOverrides | None = None,
) -> list[GeneratedFile]:
	"""End-to-end: parse → normalize → run every generator → sort.

	Returns a list of files sorted by path so two invocations against the
	same bundle return byte-identical output (the snapshot/regen tests
	depend on this).

	*overrides* (v0.3.0 W4b / item 22 / ADR-002) is the optional copy-
	override sidecar. ``None`` (the default) keeps canonical-only output
	so pre-W4b bundles regen byte-identically. When passed in, it is
	applied at normalize time — see :mod:`flowforge_cli.jtbd.overrides`
	for the lookup contract.
	"""

	parse_bundle(bundle)
	norm = normalize(bundle, overrides=overrides)

	files: list[GeneratedFile] = []
	for jt in norm.jtbds:
		for gen in _PER_JTBD_GENERATORS:
			files.extend(_coerce(gen(norm, jt)))

	for gen in _PER_BUNDLE_GENERATORS:
		files.extend(_coerce(gen(norm)))

	# Deduplicate (later wins) on path so per-JTBD generators that touch
	# the same shared file are predictable. None today, but cheap insurance.
	dedup: dict[str, GeneratedFile] = {}
	for f in files:
		dedup[f.path] = f
	return sorted(dedup.values(), key=lambda f: f.path)


def generate_for_bundle(norm: NormalizedBundle) -> list[GeneratedFile]:
	"""Skip parse/validate (callers already normalized). Test-only shortcut."""

	files: list[GeneratedFile] = []
	for jt in norm.jtbds:
		for gen in _PER_JTBD_GENERATORS:
			files.extend(_coerce(gen(norm, jt)))
	for gen in _PER_BUNDLE_GENERATORS:
		files.extend(_coerce(gen(norm)))
	dedup: dict[str, GeneratedFile] = {}
	for f in files:
		dedup[f.path] = f
	return sorted(dedup.values(), key=lambda f: f.path)


def _coerce(result: Any) -> list[GeneratedFile]:
	"""Generators may return a single :class:`GeneratedFile` or a list."""

	if result is None:
		return []
	if isinstance(result, GeneratedFile):
		return [result]
	out: list[GeneratedFile] = []
	for item in result:
		assert isinstance(item, GeneratedFile)
		out.append(item)
	return out
