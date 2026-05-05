"""Cross-bundle ``.env.example`` for the generated app."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	content = render("env.example.j2", project=bundle.project, bundle=bundle)
	return GeneratedFile(path=".env.example", content=content)
