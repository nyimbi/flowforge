"""Cross-bundle alembic env + ini scaffolding."""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle
from .._types import GeneratedFile


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	env_py = render("alembic/env.py.j2", project=bundle.project, bundle=bundle)
	script_mako = render("alembic/script.py.mako.j2", project=bundle.project)
	alembic_ini = render("alembic/alembic.ini.j2", project=bundle.project)
	return [
		GeneratedFile(path="backend/migrations/env.py", content=env_py),
		GeneratedFile(path="backend/migrations/script.py.mako", content=script_mako),
		GeneratedFile(path="backend/alembic.ini", content=alembic_ini),
	]
