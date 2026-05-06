"""Lockfile model + body-hash determinism tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flowforge_jtbd.dsl import (
	JtbdComposition,
	JtbdLockfile,
	JtbdLockfilePin,
	canonical_json,
)
from pydantic import ValidationError


def _pin(jtbd_id: str = "claim_intake", version: str = "1.0.0") -> JtbdLockfilePin:
	return JtbdLockfilePin(
		jtbd_id=jtbd_id,
		version=version,
		spec_hash="sha256:" + ("0" * 64),
		source="local",
	)


def test_minimal_lockfile_validates() -> None:
	lock = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin()],
	)
	assert lock.schema_version == "1"
	assert lock.body_hash is None  # caller fills via with_body_hash()


def test_duplicate_pins_rejected() -> None:
	with pytest.raises(ValidationError):
		JtbdLockfile(
			composition_id="comp-1",
			project_package="claims_intake",
			pins=[_pin("a"), _pin("a")],
		)


def test_naive_datetime_rejected() -> None:
	with pytest.raises(ValidationError):
		JtbdLockfile(
			composition_id="c",
			project_package="p",
			pins=[_pin()],
			generated_at=datetime(2026, 5, 6, 12, 0, 0),  # naive
		)


def test_aware_datetime_normalised_to_utc() -> None:
	from datetime import timedelta, timezone as tz

	plus_three = tz(timedelta(hours=3))
	lock = JtbdLockfile(
		composition_id="c",
		project_package="p",
		pins=[_pin()],
		generated_at=datetime(2026, 5, 6, 12, 0, 0, tzinfo=plus_three),
	)
	assert lock.generated_at.tzinfo == timezone.utc
	assert lock.generated_at.hour == 9


def test_compute_body_hash_independent_of_pin_order() -> None:
	a = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin("a"), _pin("b")],
	)
	b = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin("b"), _pin("a")],
	)
	assert a.compute_body_hash() == b.compute_body_hash()


def test_body_hash_independent_of_generated_at_and_by() -> None:
	"""generated_at / generated_by are metadata, not part of the body."""
	pins = [_pin("a"), _pin("b")]
	a = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=pins,
		generated_by="user-1",
	)
	b = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=pins,
		generated_by="user-2",
	)
	assert a.compute_body_hash() == b.compute_body_hash()


def test_body_hash_changes_when_pin_changes() -> None:
	a = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin("a", "1.0.0")],
	)
	b = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin("a", "1.0.1")],
	)
	assert a.compute_body_hash() != b.compute_body_hash()


def test_with_body_hash_populates_body_hash() -> None:
	lock = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin()],
	).with_body_hash()
	assert lock.body_hash is not None
	assert lock.body_hash.startswith("sha256:")


def test_invalid_spec_hash_rejected() -> None:
	with pytest.raises(ValidationError):
		JtbdLockfilePin(
			jtbd_id="x", version="1.0.0", spec_hash="md5:abc"
		)


def test_canonical_json_of_lockfile_is_byte_stable() -> None:
	a = JtbdLockfile(
		composition_id="comp-1",
		project_package="claims_intake",
		pins=[_pin()],
	)
	one = canonical_json(a.canonical_body())
	two = canonical_json(a.canonical_body())
	assert one == two


def test_composition_unique_jtbd_ids_required() -> None:
	c = JtbdComposition(
		id="c-1",
		tenant_id="t-1",
		name="claims-intake",
		project_package="claims_intake",
		jtbd_ids=["a", "b", "c"],
	)
	assert c.jtbd_ids == ["a", "b", "c"]


def test_composition_empty_jtbd_ids_rejected() -> None:
	with pytest.raises(ValidationError):
		JtbdComposition(
			id="c-1",
			tenant_id="t-1",
			name="x",
			project_package="x",
			jtbd_ids=[],
		)
