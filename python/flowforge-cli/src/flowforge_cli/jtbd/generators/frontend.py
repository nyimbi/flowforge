"""Emit Next.js step components + a route page per JTBD.

The Step.tsx emission path is selected by ``bundle.project.frontend.form_renderer``
(v0.3.0 W1 / item 13 of ``docs/improvements.md``):

* ``"skeleton"`` (default): the legacy stub with ``<dd>—</dd>`` placeholders.
  Pre-W1 bundles default here so existing examples regen byte-identically.
* ``"real"``: a working ``@flowforge/renderer`` ``FormRenderer`` invocation
  bound to ``form_spec.json`` with derived client-side validators,
  ``show_if`` conditional visibility, PII visual treatment, and inline
  ``aria-describedby`` error wiring.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bundle/JTBD attribute paths consumed by this generator. The
# generator-fixture-coverage test (v0.3.0 plan §5 pre-mortem #1) walks
# every generator and asserts each declared path is exercised by at
# least one example bundle.
CONSUMES: tuple[str, ...] = (
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
)


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> list[GeneratedFile]:
	form_renderer = bundle.project.form_renderer
	step = render(
		"frontend/Step.tsx.j2",
		project=bundle.project,
		jtbd=jtbd,
		form_renderer=form_renderer,
	)
	page = render(
		"frontend/page.tsx.j2",
		project=bundle.project,
		jtbd=jtbd,
		form_renderer=form_renderer,
	)
	return [
		GeneratedFile(
			path=f"frontend/src/components/{jtbd.url_segment}/{jtbd.class_name}Step.tsx",
			content=step,
		),
		GeneratedFile(
			path=f"frontend/src/app/{jtbd.url_segment}/page.tsx",
			content=page,
		),
	]
