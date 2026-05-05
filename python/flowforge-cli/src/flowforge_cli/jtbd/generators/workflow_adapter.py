"""Emit a workflow_adapter.py module that calls flowforge.engine.fire."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	content = render("workflow_adapter.py.j2", project=bundle.project, jtbd=jtbd)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/adapters/{jtbd.module_name}_adapter.py",
		content=content,
	)
