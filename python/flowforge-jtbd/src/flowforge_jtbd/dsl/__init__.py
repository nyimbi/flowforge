"""Canonical JTBD DSL — pydantic models for specs, bundles, lockfiles.

This subpackage owns the wire-format truth for ticket E-1
(``framework/docs/flowforge-evolution.md`` §3,
``framework/docs/jtbd-editor-arch.md`` §13). The lint-facing models
live alongside in :mod:`flowforge_jtbd.spec` (E-4); they intentionally
expose only the subset the linter needs and keep ``extra='allow'`` so
they ride forward through schema churn.

Three artefacts compose the contract:

* :class:`flowforge_jtbd.dsl.JtbdSpec` — one JTBD, plus the version /
  hash / replaced_by metadata that anchors content addressing.
* :class:`flowforge_jtbd.dsl.JtbdBundle` — project + shared metadata +
  the JTBD list, the unit a tenant publishes.
* :class:`flowforge_jtbd.dsl.JtbdLockfile` — frozen pin table for a
  composition (jtbd_id × version × spec_hash × source). Same canonical
  JSON path is used to compute its body hash.

Hashing helpers live in :mod:`flowforge_jtbd.dsl.canonical`. They follow
the RFC-8785-aligned shape spelled out in
``framework/docs/jtbd-editor-arch.md`` §23.2.
"""

from __future__ import annotations

from .canonical import canonical_json, spec_hash
from .lockfile import (
	JtbdComposition,
	JtbdLockfile,
	JtbdLockfilePin,
	LockfileSource,
)
from .spec import (
	JtbdActor,
	JtbdApproval,
	JtbdBundle,
	JtbdDocReq,
	JtbdEdgeCase,
	JtbdField,
	JtbdNotification,
	JtbdProject,
	JtbdShared,
	JtbdSla,
	JtbdSpec,
	JtbdSpecStatus,
)

__all__ = [
	"JtbdActor",
	"JtbdApproval",
	"JtbdBundle",
	"JtbdComposition",
	"JtbdDocReq",
	"JtbdEdgeCase",
	"JtbdField",
	"JtbdLockfile",
	"JtbdLockfilePin",
	"JtbdNotification",
	"JtbdProject",
	"JtbdShared",
	"JtbdSla",
	"JtbdSpec",
	"JtbdSpecStatus",
	"LockfileSource",
	"canonical_json",
	"spec_hash",
]
