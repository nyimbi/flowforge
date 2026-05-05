"""Cross-bundle notifications catalog."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	content = render("notifications.py.j2", project=bundle.project, bundle=bundle)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/notifications.py",
		content=content,
	)
