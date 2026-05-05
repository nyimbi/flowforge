"""Emit a deterministic alembic migration for one JTBD's table."""

from __future__ import annotations

import hashlib

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


def _stable_revision(bundle_pkg: str, jtbd_id: str) -> str:
	"""Return a 12-char hex revision id derived from package + id.

	Deterministic so two runs of the generator emit identical migrations.
	"""

	digest = hashlib.sha256(f"{bundle_pkg}:{jtbd_id}".encode("utf-8")).hexdigest()
	return digest[:12]


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	revision = _stable_revision(bundle.project.package, jtbd.id)
	content = render(
		"db_migration.py.j2",
		project=bundle.project,
		jtbd=jtbd,
		revision=revision,
	)
	return GeneratedFile(
		path=f"backend/migrations/versions/{revision}_create_{jtbd.table_name}.py",
		content=content,
	)
