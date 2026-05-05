"""Emit a FastAPI router shim per JTBD (uses flowforge-fastapi)."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	content = render("domain_router.py.j2", project=bundle.project, jtbd=jtbd)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/routers/{jtbd.module_name}_router.py",
		content=content,
	)
