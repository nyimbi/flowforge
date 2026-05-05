"""Emit Next.js step components + a route page per JTBD."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> list[GeneratedFile]:
	step = render("frontend/Step.tsx.j2", project=bundle.project, jtbd=jtbd)
	page = render("frontend/page.tsx.j2", project=bundle.project, jtbd=jtbd)
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
