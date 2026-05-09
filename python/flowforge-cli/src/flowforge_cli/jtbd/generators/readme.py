"""Cross-bundle README for the generated app.

Aggregates per-JTBD context into the top-level README. As of W1 / item 19
the README also embeds each JTBD's mermaid state-diagram source inline as
a fenced ``mermaid`` block, alongside a relative link to the
``workflows/<id>/diagram.mmd`` source file. Embedding the source rather
than a pre-rendered SVG preserves Principle 1 (determinism) — the SVG
bytes a mermaid-cli render would emit are not stable across versions.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile
from . import diagram


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	# Compute per-JTBD diagram sources up front so the template stays a
	# pure substitution (no Python in jinja2 expressions). Keyed by jtbd.id
	# so the template can do ``{{ diagrams[jtbd.id] }}`` deterministically.
	diagrams: dict[str, str] = {
		jt.id: diagram.build_mmd(bundle, jt) for jt in bundle.jtbds
	}
	content = render(
		"README.md.j2",
		project=bundle.project,
		bundle=bundle,
		diagrams=diagrams,
	)
	return GeneratedFile(path="README.md", content=content)
