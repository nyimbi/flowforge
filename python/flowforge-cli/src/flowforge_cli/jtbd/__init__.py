"""JTBD-to-app generator (U19).

Deterministic transform pipeline that takes a JTBD bundle (validated
against ``jtbd-1.0.schema.json``) and emits a per-JTBD application
skeleton: alembic migration, SQLAlchemy model, workflow adapter, JSON
DSL workflow definition, form spec, simulation tests, Next.js step
component plus the cross-bundle aggregations (permissions catalog,
audit taxonomy, notifications, alembic env, README, .env.example).

No LLM calls. Templates are pure jinja2 with ``StrictUndefined`` so a
typo blows up at render time, not at runtime.
"""

from __future__ import annotations

from .normalize import NormalizedBundle, NormalizedJTBD, normalize
from .parse import JTBDParseError, parse_bundle
from .pipeline import GeneratedFile, generate

__all__ = [
	"GeneratedFile",
	"JTBDParseError",
	"NormalizedBundle",
	"NormalizedJTBD",
	"generate",
	"normalize",
	"parse_bundle",
]
