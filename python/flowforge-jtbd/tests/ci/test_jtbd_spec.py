"""Pydantic JtbdSpec / JtbdBundle round-trip + invariant tests."""

from __future__ import annotations

import pytest
from flowforge_jtbd.dsl import (
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
    canonical_json,
    spec_hash,
)
from flowforge_jtbd.dsl.spec import JtbdDesign
from pydantic import ValidationError


def _minimal_spec(jtbd_id: str = "claim_intake") -> JtbdSpec:
    return JtbdSpec(
        id=jtbd_id,
        title="Submit a new motor claim",
        actor=JtbdActor(role="intake_clerk", department="claims"),
        situation="A policyholder calls in after an accident.",
        motivation="Open claim quickly so adjuster can triage within SLA.",
        outcome="A triage-ready claim record exists.",
        success_criteria=["All required documents uploaded.", "Loss amount captured."],
        data_capture=[
            JtbdField(id="policy_id", kind="party_ref", pii=False),
            JtbdField(id="incident_date", kind="date"),
            JtbdField(id="loss_amount", kind="money"),
            JtbdField(id="claimant_name", kind="text", pii=True),
        ],
        documents_required=[
            JtbdDocReq(kind="police_report", min=1, freshness_days=30),
        ],
        approvals=[
            JtbdApproval(role="claims_supervisor", policy="authority_tier", tier=2)
        ],
        edge_cases=[
            JtbdEdgeCase(
                id="policy_lapsed",
                condition="policy.status != 'in_force'",
                handle="reject",
            ),
            JtbdEdgeCase(
                id="large_loss",
                condition="loss_amount > 100000",
                handle="branch",
                branch_to="senior_triage",
            ),
        ],
        sla=JtbdSla(warn_pct=80, breach_seconds=14400),
        notifications=[
            JtbdNotification(
                trigger="state_enter", channel="in_app", audience="triage_officer"
            ),
        ],
    )


def test_minimal_spec_validates() -> None:
    spec = _minimal_spec()
    assert spec.id == "claim_intake"
    assert spec.actor.role == "intake_clerk"
    assert spec.spec_hash is None  # caller fills this via with_hash()


def test_invalid_id_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        JtbdSpec(
            id="ClaimIntake",  # uppercase forbidden
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )


def test_invalid_version_rejected() -> None:
    with pytest.raises(ValidationError):
        JtbdSpec(
            id="claim_intake",
            version="not-a-version",
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )


def test_empty_version_rejected() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdSpec(
            id="claim_intake",
            version="",
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )
    assert "version must be non-empty" in str(ei.value)


def test_empty_version_suffix_rejected() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdSpec(
            id="claim_intake",
            version="1.0.0-",
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )
    assert "empty pre-release/build suffix" in str(ei.value)


def test_explicit_valid_version_is_preserved() -> None:
    spec = JtbdSpec(
        id="claim_intake",
        version="1.2.3",
        actor=JtbdActor(role="r"),
        situation="s",
        motivation="m",
        outcome="o",
        success_criteria=["sc"],
    )
    assert spec.version == "1.2.3"


def test_invalid_version_shape_from_packaging_rejected() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdSpec(
            id="claim_intake",
            version="1.0.0-foo@bar",
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )
    assert "valid PEP 440 / semver" in str(ei.value)


def test_spec_hash_must_use_sha256_prefix() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdSpec(
            id="claim_intake",
            spec_hash="md5:" + ("0" * 64),
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )
    assert "prefixed with 'sha256:'" in str(ei.value)


def test_valid_spec_hash_is_preserved() -> None:
    spec = JtbdSpec(
        id="claim_intake",
        spec_hash="sha256:" + ("0" * 64),
        actor=JtbdActor(role="r"),
        situation="s",
        motivation="m",
        outcome="o",
        success_criteria=["sc"],
    )
    assert spec.spec_hash == "sha256:" + ("0" * 64)


def test_invalid_spec_hash_digest_rejected() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdSpec(
            id="claim_intake",
            spec_hash="sha256:" + ("g" * 64),
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )
    assert "64 lowercase hex" in str(ei.value)


def test_non_ascii_identifier_rejected() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdSpec(
            id="café_run",
            actor=JtbdActor(role="r"),
            situation="s",
            motivation="m",
            outcome="o",
            success_criteria=["sc"],
        )
    assert "ASCII lowercase letters" in str(ei.value)


def test_pii_required_on_sensitive_kinds() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdField(id="claimant_name", kind="text")  # missing pii
    assert "must declare pii" in str(ei.value)


def test_pii_default_explicit_false_allowed() -> None:
    # explicit pii=False is fine even on sensitive kind
    field = JtbdField(id="policy_id", kind="party_ref", pii=False)
    assert field.pii is False


def test_edge_case_branch_requires_target() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdEdgeCase(id="x", condition="cond", handle="branch")
    assert "branch_to" in str(ei.value)


def test_approval_n_of_m_requires_n() -> None:
    with pytest.raises(ValidationError):
        JtbdApproval(role="reviewer", policy="n_of_m")


def test_approval_authority_tier_requires_tier() -> None:
    with pytest.raises(ValidationError):
        JtbdApproval(role="reviewer", policy="authority_tier")


def test_design_hex_colours_are_lowercased() -> None:
    design = JtbdDesign(primary="#ABC", accent="#123456EF")
    assert design.primary == "#abc"
    assert design.accent == "#123456ef"


def test_design_hex_colours_must_start_with_hash() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdDesign(primary="2563eb")
    assert "hex literal" in str(ei.value)


def test_design_hex_colours_reject_bad_lengths() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdDesign(primary="#12345")
    assert "3, 6, or 8" in str(ei.value)


def test_design_hex_colours_reject_non_hex_digits() -> None:
    with pytest.raises(ValidationError) as ei:
        JtbdDesign(primary="#12x")
    assert "non-hex digit" in str(ei.value)


def test_extra_keys_forbidden_at_canonical_layer() -> None:
    with pytest.raises(ValidationError):
        JtbdSpec.model_validate(
            {
                "id": "claim_intake",
                "unknown_field": "boom",
                "actor": {"role": "r"},
                "situation": "s",
                "motivation": "m",
                "outcome": "o",
                "success_criteria": ["sc"],
            }
        )


def test_compute_hash_deterministic_and_excludes_status() -> None:
    # Build two specs that differ only in status / parent_version_id
    # (which the hash body excludes). They should hash identically.
    a = _minimal_spec()
    b = a.model_copy(update={"status": "published", "parent_version_id": "abc"})
    assert a.compute_hash() == b.compute_hash()


def test_with_hash_populates_field() -> None:
    spec = _minimal_spec().with_hash()
    assert spec.spec_hash is not None
    assert spec.spec_hash.startswith("sha256:")


def test_hash_changes_when_id_or_version_changes() -> None:
    a = _minimal_spec("claim_intake").compute_hash()
    b = _minimal_spec("claim_intake_2").compute_hash()
    assert a != b
    c = _minimal_spec("claim_intake").model_copy(update={"version": "1.0.1"})
    assert a != c.compute_hash()


def test_bundle_unique_jtbd_ids_enforced() -> None:
    a = _minimal_spec("claim_intake")
    b = _minimal_spec("claim_intake")
    with pytest.raises(ValidationError):
        JtbdBundle(
            project=JtbdProject(
                name="claims-intake", package="claims_intake", domain="insurance"
            ),
            shared=JtbdShared(),
            jtbds=[a, b],
        )


def test_bundle_with_hashes_populates_every_spec_hash() -> None:
    bundle = JtbdBundle(
        project=JtbdProject(name="x", package="x", domain="d"),
        jtbds=[_minimal_spec("a"), _minimal_spec("b")],
    )
    hashed = bundle.with_hashes()
    assert all(s.spec_hash is not None for s in hashed.jtbds)


def test_bundle_find_and_by_id() -> None:
    bundle = JtbdBundle(
        project=JtbdProject(name="x", package="x", domain="d"),
        jtbds=[_minimal_spec("a"), _minimal_spec("b")],
    )
    assert bundle.find("a") is not None
    assert bundle.find("missing") is None
    idx = bundle.by_id()
    assert set(idx.keys()) == {"a", "b"}


def test_canonical_json_round_trip_for_full_bundle() -> None:
    bundle = JtbdBundle(
        project=JtbdProject(name="x", package="x", domain="insurance"),
        jtbds=[_minimal_spec("a")],
    )
    # Two encodings of the same bundle hash to the same value.
    a = canonical_json(bundle)
    b = canonical_json(bundle)
    assert a == b
    # spec_hash shape verification on the same body.
    hashed = bundle.jtbds[0].with_hash()
    assert spec_hash(hashed.hash_body()) == hashed.spec_hash
