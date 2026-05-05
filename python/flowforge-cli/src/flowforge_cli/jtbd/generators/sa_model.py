"""Generate a SQLAlchemy 2.x model for one JTBD."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	content = render("sa_model.py.j2", project=bundle.project, jtbd=jtbd)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/models/{jtbd.module_name}.py",
		content=content,
	)
