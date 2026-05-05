"""Emit a thin domain service layer per JTBD."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	content = render("domain_service.py.j2", project=bundle.project, jtbd=jtbd)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/services/{jtbd.module_name}_service.py",
		content=content,
	)
