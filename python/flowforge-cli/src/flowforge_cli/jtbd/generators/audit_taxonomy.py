"""Cross-bundle audit topic catalog."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	content = render("audit_taxonomy.py.j2", project=bundle.project, bundle=bundle)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/audit_taxonomy.py",
		content=content,
	)
