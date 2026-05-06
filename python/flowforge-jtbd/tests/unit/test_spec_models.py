"""Lint-facing spec model behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from flowforge_jtbd.spec import (
	ActorRef,
	JtbdBundle,
	JtbdLintSpec,
	RoleDef,
	StageDecl,
	coerce_bundle,
)

from .conftest import make_bundle, make_full_spec


def test_stage_names_excludes_delegations() -> None:
	spec = JtbdLintSpec(
		jtbd_id="x",
		version="1.0.0",
		stages=[
			StageDecl(name="execute"),
			StageDecl(name="audit", handled_by="other"),
		],
	)
	assert spec.stage_names() == {"execute"}
	assert spec.stage_delegations() == {"audit": "other"}


def test_jtbd_id_must_be_non_empty() -> None:
	with pytest.raises(ValidationError):
		JtbdLintSpec(jtbd_id="", version="1.0.0")
	with pytest.raises(ValidationError):
		JtbdLintSpec(jtbd_id="   ", version="1.0.0")


def test_actor_ref_extra_forbidden() -> None:
	with pytest.raises(ValidationError):
		ActorRef.model_validate({"role": "x", "weird": True})


def test_role_def_defaults() -> None:
	r = RoleDef(name="banker")
	assert r.default_tier == 0
	assert r.capacities == []


def test_bundle_lookup_helpers() -> None:
	a = make_full_spec("a")
	b = make_full_spec("b")
	bundle = make_bundle([a, b])
	assert bundle.find("a") is a
	assert bundle.find("missing") is None
	assert set(bundle.by_id().keys()) == {"a", "b"}


def test_coerce_bundle_accepts_dict() -> None:
	d = {
		"bundle_id": "from-dict",
		"jtbds": [
			{
				"jtbd_id": "x",
				"version": "1.0.0",
				"stages": [{"name": "execute"}],
			},
		],
	}
	bundle = coerce_bundle(d)
	assert isinstance(bundle, JtbdBundle)
	assert bundle.bundle_id == "from-dict"
	assert bundle.jtbds[0].jtbd_id == "x"


def test_coerce_bundle_passthrough() -> None:
	bundle = make_bundle([make_full_spec("x")])
	assert coerce_bundle(bundle) is bundle


def test_jtbd_lint_spec_allows_extra_fields() -> None:
	"""Forward-compat with E-1's richer canonical schema."""
	spec = JtbdLintSpec.model_validate({
		"jtbd_id": "x",
		"version": "1.0.0",
		"stages": [{"name": "execute"}],
		"future_field": {"nested": True},
	})
	assert spec.jtbd_id == "x"
