"""Tests for ``flowforge jtbd migrate`` — E-3 replaced_by CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bundle(*jtbds: dict[str, Any]) -> dict[str, Any]:
	return {
		"project": {"name": "test", "package": "test", "domain": "test"},
		"shared": {"roles": ["user"], "permissions": ["test.read"]},
		"jtbds": list(jtbds),
	}


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


@pytest.fixture()
def simple_bundle(tmp_path: Path) -> Path:
	"""Bundle where 'old_intake' is replaced by 'new_intake'."""
	data = _bundle(
		_jtbd(
			"old_intake",
			replaced_by="new_intake",
			deprecated=True,
			fields=[_field("claimant_name", pii=True), _field("loss_amount", "money")],
		),
		_jtbd(
			"new_intake",
			fields=[
				_field("claimant_name", pii=True),
				_field("loss_amount", "money"),
				_field("incident_date", "date"),  # added
				# claimant_phone removed
			],
		),
	)
	p = tmp_path / "bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


@pytest.fixture()
def bundle_with_removed(tmp_path: Path) -> Path:
	"""Bundle where a field is removed in the replacement."""
	data = _bundle(
		_jtbd(
			"v1",
			replaced_by="v2",
			deprecated=True,
			fields=[_field("keep_me"), _field("drop_me")],
		),
		_jtbd("v2", fields=[_field("keep_me"), _field("new_field", "date")]),
	)
	p = tmp_path / "bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


@pytest.fixture()
def not_deprecated_bundle(tmp_path: Path) -> Path:
	data = _bundle(_jtbd("current", fields=[_field("name")]))
	p = tmp_path / "bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


@pytest.fixture()
def multi_hop_bundle(tmp_path: Path) -> Path:
	data = _bundle(
		_jtbd("a", replaced_by="b", deprecated=True, fields=[_field("x")]),
		_jtbd("b", replaced_by="c", deprecated=True, fields=[_field("x"), _field("y")]),
		_jtbd("c", fields=[_field("x"), _field("y"), _field("z")]),
	)
	p = tmp_path / "bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


# ---------------------------------------------------------------------------
# Tests — show diff only
# ---------------------------------------------------------------------------


def test_migrate_shows_diff(simple_bundle: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "migrate", "--bundle", str(simple_bundle), "--from", "old_intake"]
	)
	assert r.exit_code == 0, r.output
	assert "old_intake" in r.output
	assert "new_intake" in r.output
	assert "+ incident_date" in r.output


def test_migrate_not_deprecated_prints_notice(not_deprecated_bundle: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "migrate", "--bundle", str(not_deprecated_bundle), "--from", "current"]
	)
	assert r.exit_code == 0, r.output
	assert "not deprecated" in r.output


def test_migrate_multi_hop_shows_full_chain(multi_hop_bundle: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "migrate", "--bundle", str(multi_hop_bundle), "--from", "a"]
	)
	assert r.exit_code == 0, r.output
	assert "a → b → c" in r.output
	assert "+ y" in r.output
	assert "+ z" in r.output


def test_migrate_unknown_jtbd_exits_1(simple_bundle: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "migrate", "--bundle", str(simple_bundle), "--from", "ghost"]
	)
	assert r.exit_code == 1


# ---------------------------------------------------------------------------
# Tests — apply migration to a record
# ---------------------------------------------------------------------------


def test_migrate_record_prints_migrated(bundle_with_removed: Path, tmp_path: Path) -> None:
	record = tmp_path / "record.json"
	record.write_text(json.dumps({"keep_me": "Alice", "drop_me": "old_value"}), encoding="utf-8")

	r = runner.invoke(
		app,
		[
			"jtbd", "migrate",
			"--bundle", str(bundle_with_removed),
			"--from", "v1",
			"--record", str(record),
		],
	)
	assert r.exit_code == 0, r.output
	assert "migrated record" in r.output
	# drop_me removed; new_field added as null
	result = json.loads(r.output.split("migrated record:\n", 1)[1])
	assert "drop_me" not in result
	assert result["new_field"] is None
	assert result["keep_me"] == "Alice"


def test_migrate_record_writes_to_file(bundle_with_removed: Path, tmp_path: Path) -> None:
	record = tmp_path / "record.json"
	record.write_text(json.dumps({"keep_me": "Bob", "drop_me": "gone"}), encoding="utf-8")
	out = tmp_path / "migrated.json"

	r = runner.invoke(
		app,
		[
			"jtbd", "migrate",
			"--bundle", str(bundle_with_removed),
			"--from", "v1",
			"--record", str(record),
			"--out", str(out),
		],
	)
	assert r.exit_code == 0, r.output
	assert out.is_file()
	result = json.loads(out.read_text())
	assert "drop_me" not in result
	assert result["keep_me"] == "Bob"


def test_migrate_record_warns_on_dropped_data(bundle_with_removed: Path, tmp_path: Path) -> None:
	record = tmp_path / "record.json"
	# drop_me has a value — should warn
	record.write_text(json.dumps({"keep_me": "Alice", "drop_me": "value"}), encoding="utf-8")

	r = runner.invoke(
		app,
		[
			"jtbd", "migrate",
			"--bundle", str(bundle_with_removed),
			"--from", "v1",
			"--record", str(record),
		],
	)
	assert r.exit_code == 0, r.output
	# Warning goes to stderr; CliRunner mixes streams by default
	assert "drop_me" in r.output or "dropped" in r.output
