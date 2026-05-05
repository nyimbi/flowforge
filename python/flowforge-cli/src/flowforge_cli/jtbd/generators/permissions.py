"""Cross-bundle permissions catalog."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	content = render("permissions.py.j2", project=bundle.project, bundle=bundle)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/permissions.py",
		content=content,
	)
