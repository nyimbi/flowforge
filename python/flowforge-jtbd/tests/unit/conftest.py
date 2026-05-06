"""Shared fixtures for E-4 lint tests."""

from __future__ import annotations

from flowforge_jtbd.spec import (
	ActorRef,
	JtbdBundle,
	JtbdLintSpec,
	RoleDef,
	StageDecl,
)


_FULL_STAGES = [
	StageDecl(name="discover"),
	StageDecl(name="execute"),
	StageDecl(name="error_handle"),
	StageDecl(name="report"),
	StageDecl(name="audit"),
]


def make_full_spec(
	jtbd_id: str = "demo_jtbd",
	*,
	version: str = "1.0.0",
	actor: ActorRef | None = None,
	requires: list[str] | None = None,
	stages: list[StageDecl] | None = None,
	compliance: list[str] | None = None,
) -> JtbdLintSpec:
	"""Build a complete lint-spec with every required stage covered."""
	return JtbdLintSpec(
		jtbd_id=jtbd_id,
		version=version,
		actor=actor,
		requires=list(requires or []),
		stages=list(stages or _FULL_STAGES),
		compliance=list(compliance or []),
	)


def make_bundle(
	jtbds: list[JtbdLintSpec],
	*,
	bundle_id: str = "test-bundle",
	shared_roles: dict[str, RoleDef] | None = None,
) -> JtbdBundle:
	return JtbdBundle(
		bundle_id=bundle_id,
		jtbds=list(jtbds),
		shared_roles=dict(shared_roles or {}),
	)
