"""Tests for flowforge_jtbd.migrate — E-3 replaced_by migration runner."""

from __future__ import annotations

from typing import Any

import pytest

from flowforge_jtbd.migrate import (
	ApplyResult,
	FieldChange,
	MigrationDiff,
	MigrationError,
	apply_to_record,
	build_migration,
	diff_shapes,
	format_diff_text,
	resolve_chain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bundle(*jtbds: dict[str, Any]) -> dict[str, Any]:
	return {"project": {"name": "test"}, "jtbds": list(jtbds)}


def _jtbd(
	jtbd_id: str,
	*,
	replaced_by: str | None = None,
	deprecated: bool = False,
	fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
	spec: dict[str, Any] = {
		"id": jtbd_id,
		"actor": {"role": "user"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["sc"],
	}
	if replaced_by:
		spec["replaced_by"] = replaced_by
	if deprecated:
		spec["deprecated"] = True
	if fields is not None:
		spec["data_capture"] = fields
	return spec


def _field(fid: str, kind: str = "text", *, pii: bool = False) -> dict[str, Any]:
	return {"id": fid, "kind": kind, "pii": pii}


# ---------------------------------------------------------------------------
# resolve_chain
# ---------------------------------------------------------------------------


def test_resolve_chain_no_replacement() -> None:
	bundle = _bundle(_jtbd("a"))
	assert resolve_chain(bundle, "a") == ["a"]


def test_resolve_chain_single_hop() -> None:
	bundle = _bundle(
		_jtbd("a", replaced_by="b", deprecated=True),
		_jtbd("b"),
	)
	assert resolve_chain(bundle, "a") == ["a", "b"]


def test_resolve_chain_multi_hop() -> None:
	bundle = _bundle(
		_jtbd("a", replaced_by="b", deprecated=True),
		_jtbd("b", replaced_by="c", deprecated=True),
		_jtbd("c"),
	)
	assert resolve_chain(bundle, "a") == ["a", "b", "c"]


def test_resolve_chain_start_not_found() -> None:
	bundle = _bundle(_jtbd("a"))
	with pytest.raises(MigrationError, match="not found"):
		resolve_chain(bundle, "missing")


def test_resolve_chain_target_missing() -> None:
	bundle = _bundle(_jtbd("a", replaced_by="ghost"))
	with pytest.raises(MigrationError, match="not found in bundle"):
		resolve_chain(bundle, "a")


def test_resolve_chain_cycle_detected() -> None:
	bundle = _bundle(
		_jtbd("a", replaced_by="b"),
		_jtbd("b", replaced_by="a"),
	)
	with pytest.raises(MigrationError, match="cycle"):
		resolve_chain(bundle, "a")


def test_resolve_chain_max_depth_exceeded() -> None:
	# Build a chain a→b→c with max_depth=2; should fail when trying to add c.
	bundle = _bundle(
		_jtbd("a", replaced_by="b"),
		_jtbd("b", replaced_by="c"),
		_jtbd("c"),
	)
	with pytest.raises(MigrationError, match="max_depth"):
		resolve_chain(bundle, "a", max_depth=2)


# ---------------------------------------------------------------------------
# diff_shapes
# ---------------------------------------------------------------------------


def test_diff_shapes_no_changes() -> None:
	fields = [_field("name"), _field("amount", "money")]
	old = _jtbd("v1", fields=fields)
	new = _jtbd("v2", fields=fields)
	diff = diff_shapes(old, new)

	assert diff.from_id == "v1"
	assert diff.to_id == "v2"
	assert diff.added == ()
	assert diff.removed == ()
	assert diff.changed == ()


def test_diff_shapes_added_field() -> None:
	old = _jtbd("v1", fields=[_field("name")])
	new = _jtbd("v2", fields=[_field("name"), _field("email", "email")])
	diff = diff_shapes(old, new)

	assert diff.added == ("email",)
	assert diff.removed == ()
	assert diff.changed == ()


def test_diff_shapes_removed_field() -> None:
	old = _jtbd("v1", fields=[_field("name"), _field("old_field")])
	new = _jtbd("v2", fields=[_field("name")])
	diff = diff_shapes(old, new)

	assert diff.added == ()
	assert diff.removed == ("old_field",)
	assert diff.changed == ()


def test_diff_shapes_changed_kind() -> None:
	old = _jtbd("v1", fields=[_field("amount", "text")])
	new = _jtbd("v2", fields=[_field("amount", "money")])
	diff = diff_shapes(old, new)

	assert diff.added == ()
	assert diff.removed == ()
	assert len(diff.changed) == 1
	ch = diff.changed[0]
	assert ch.id == "amount"
	assert ch.old_kind == "text"
	assert ch.new_kind == "money"


def test_diff_shapes_no_data_capture() -> None:
	old = _jtbd("v1")  # no data_capture key
	new = _jtbd("v2")
	diff = diff_shapes(old, new)
	assert diff.added == diff.removed == diff.changed == ()


def test_diff_shapes_mixed() -> None:
	old = _jtbd("v1", fields=[
		_field("kept"),
		_field("removed"),
		_field("changed", "text"),
	])
	new = _jtbd("v2", fields=[
		_field("kept"),
		_field("added"),
		_field("changed", "number"),
	])
	diff = diff_shapes(old, new)

	assert diff.added == ("added",)
	assert diff.removed == ("removed",)
	assert len(diff.changed) == 1
	assert diff.changed[0].id == "changed"


# ---------------------------------------------------------------------------
# build_migration
# ---------------------------------------------------------------------------


def test_build_migration_populates_full_chain() -> None:
	bundle = _bundle(
		_jtbd("a", replaced_by="b", deprecated=True, fields=[_field("x")]),
		_jtbd("b", replaced_by="c", deprecated=True, fields=[_field("x"), _field("y")]),
		_jtbd("c", fields=[_field("x"), _field("y"), _field("z")]),
	)
	diff = build_migration(bundle, "a")

	assert diff.chain == ("a", "b", "c")
	assert diff.from_id == "a"
	assert diff.to_id == "c"
	assert diff.added == ("y", "z")  # sorted
	assert diff.removed == ()


def test_build_migration_not_deprecated() -> None:
	bundle = _bundle(_jtbd("a", fields=[_field("x")]))
	diff = build_migration(bundle, "a")

	assert diff.chain == ("a",)
	assert diff.from_id == diff.to_id == "a"
	assert diff.added == diff.removed == diff.changed == ()


def test_build_migration_propagates_error() -> None:
	with pytest.raises(MigrationError):
		build_migration({"jtbds": []}, "missing")


# ---------------------------------------------------------------------------
# apply_to_record
# ---------------------------------------------------------------------------


def test_apply_to_record_drops_removed_with_value() -> None:
	diff = MigrationDiff(
		from_id="v1", to_id="v2",
		chain=("v1", "v2"),
		added=(),
		removed=("old_field",),
		changed=(),
	)
	record = {"name": "Alice", "old_field": "legacy_value"}
	result = apply_to_record(diff, record)

	assert "old_field" not in result.record
	assert result.dropped == ("old_field",)
	assert result.record["name"] == "Alice"


def test_apply_to_record_drops_removed_none_silently() -> None:
	diff = MigrationDiff(
		from_id="v1", to_id="v2",
		chain=("v1", "v2"),
		added=(),
		removed=("empty_field",),
		changed=(),
	)
	record = {"empty_field": None}
	result = apply_to_record(diff, record)

	assert result.dropped == ()  # None value → not listed as dropped


def test_apply_to_record_initialises_added_as_none() -> None:
	diff = MigrationDiff(
		from_id="v1", to_id="v2",
		chain=("v1", "v2"),
		added=("new_field",),
		removed=(),
		changed=(),
	)
	record = {"name": "Alice"}
	result = apply_to_record(diff, record)

	assert result.record["new_field"] is None
	assert result.dropped == ()


def test_apply_to_record_does_not_overwrite_existing_added() -> None:
	"""If the record already has the 'added' field, keep its value."""
	diff = MigrationDiff(
		from_id="v1", to_id="v2",
		chain=("v1", "v2"),
		added=("new_field",),
		removed=(),
		changed=(),
	)
	record = {"new_field": "already_set"}
	result = apply_to_record(diff, record)

	assert result.record["new_field"] == "already_set"


def test_apply_to_record_keeps_changed_fields_unchanged() -> None:
	diff = MigrationDiff(
		from_id="v1", to_id="v2",
		chain=("v1", "v2"),
		added=(),
		removed=(),
		changed=(FieldChange(id="amount", old_kind="text", new_kind="money"),),
	)
	record = {"amount": "150"}
	result = apply_to_record(diff, record)

	# Value kept as-is; caller coerces.
	assert result.record["amount"] == "150"


# ---------------------------------------------------------------------------
# format_diff_text
# ---------------------------------------------------------------------------


def test_format_diff_text_no_changes() -> None:
	diff = MigrationDiff(
		from_id="v1", to_id="v2",
		chain=("v1", "v2"),
		added=(), removed=(), changed=(),
	)
	text = format_diff_text(diff)
	assert "v1" in text
	assert "v2" in text
	assert "no data_capture changes" in text


def test_format_diff_text_shows_added_removed_changed() -> None:
	diff = MigrationDiff(
		from_id="old", to_id="new",
		chain=("old", "new"),
		added=("email",),
		removed=("legacy",),
		changed=(FieldChange(id="amount", old_kind="text", new_kind="money"),),
	)
	text = format_diff_text(diff)
	assert "+ email" in text
	assert "- legacy" in text
	assert "~ amount" in text
	assert "text → money" in text


def test_format_diff_text_multi_hop_chain() -> None:
	diff = MigrationDiff(
		from_id="a", to_id="c",
		chain=("a", "b", "c"),
		added=(), removed=(), changed=(),
	)
	text = format_diff_text(diff)
	assert "a → b → c" in text
