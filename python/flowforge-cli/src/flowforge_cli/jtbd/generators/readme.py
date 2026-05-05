"""Cross-bundle README for the generated app."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	content = render("README.md.j2", project=bundle.project, bundle=bundle)
	return GeneratedFile(path="README.md", content=content)
