"""Per-bundle generator: design tokens for the customer + admin trees.

Item 18 of :doc:`docs/improvements`, W3 of :doc:`docs/v0.3.0-engineering-plan`.
Emits three artifacts that share a single design-token source of truth,
mirrored into both the customer-facing ``frontend/`` tree and the admin
``frontend-admin/`` tree so a single bundle change re-themes the whole
generated app on regen:

* ``design_tokens.css`` — CSS variable palette. Source of truth for
  every token; loaded via a side-effect ``import`` in the Step component
  (real-path) and the admin entry point so every layout reads the same
  tokens.
* ``tailwind.config.ts`` — Tailwind theme config in *extend* mode that
  binds Tailwind colour utilities to the CSS variables. Authors keep
  Tailwind utilities; the runtime values flow through CSS variables.
* ``theme.ts`` — TypeScript theme module exporting the same tokens as
  ``var(...)`` references plus density / radius typing aids. SSR or
  Node-side consumers that cannot read CSS variables can still pin the
  type contract.

Per-bundle aggregation (Principle 2 of the v0.3.0 plan): exactly six
files per bundle, regardless of how many JTBDs the bundle declares.

Determinism: the same five tokens render to the same six files. Bundles
that omit ``project.design`` get :data:`flowforge_cli.jtbd.normalize.DEFAULT_DESIGN`
so existing examples regen byte-identically as long as they don't
declare an override.

Hexagonal note: design tokens are *not* a runtime port — they're a
generation-time emission. Hosts read them like any other generated
asset. No new ``DesignPort`` or adapter package needed.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"project.design.accent",
	"project.design.density",
	"project.design.font_family",
	"project.design.primary",
	"project.design.radius_scale",
	"project.package",
)


# Templates emitted into BOTH the customer-facing and admin trees. The
# tuple shape is ``(template, customer_path, admin_path)`` keyed off the
# bundle's package so two bundles can coexist in the same monorepo. See
# :mod:`.frontend_admin` for the admin tree's directory layout (``src/``
# is flat under ``frontend-admin/<pkg>/``; the customer tree lives under
# ``frontend/src/<pkg>/`` with the tailwind config at root level per
# Vite/Next conventions).
def _emission_targets(pkg: str) -> tuple[tuple[str, str, str], ...]:
	return (
		(
			"design_tokens/design_tokens.css.j2",
			f"frontend/src/{pkg}/design_tokens.css",
			f"frontend-admin/{pkg}/src/design_tokens.css",
		),
		(
			"design_tokens/tailwind.config.ts.j2",
			f"frontend/{pkg}/tailwind.config.ts",
			f"frontend-admin/{pkg}/tailwind.config.ts",
		),
		(
			"design_tokens/theme.ts.j2",
			f"frontend/src/{pkg}/theme.ts",
			f"frontend-admin/{pkg}/src/theme.ts",
		),
	)


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit the six design-token files (3 artifacts × 2 trees).

	Per Principle 2 of the v0.3.0 plan, this is a per-bundle aggregation
	— even a multi-JTBD bundle gets exactly six files. The customer
	tree and the admin tree receive byte-identical token bodies so a
	colour swap stays in lockstep across both apps.
	"""

	pkg = bundle.project.package
	design = bundle.project.design
	context = {
		"project": bundle.project,
		"design": design,
		"package": pkg,
	}

	files: list[GeneratedFile] = []
	for template, customer_path, admin_path in _emission_targets(pkg):
		body = render(template, **context)
		files.append(GeneratedFile(path=customer_path, content=body))
		files.append(GeneratedFile(path=admin_path, content=body))
	return files
