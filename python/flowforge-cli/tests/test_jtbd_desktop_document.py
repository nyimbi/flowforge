"""Tests for the optional JTBD desktop editor document model."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.jtbd_desktop.document import (
	JtbdDocument,
	create_default_bundle,
	normalise_id,
	requires_pii,
)
from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.parse import parse_bundle
from flowforge_cli.main import app


runner = CliRunner()


def test_default_bundle_is_generation_ready() -> None:
	doc = JtbdDocument()

	result = doc.validate()
	files = generate(doc.bundle)

	assert result.ok
	assert result.errors == []
	assert not any("linter unavailable" in warning for warning in result.warnings)
	assert files
	assert doc.bundle["project"]["frontend"]["form_renderer"] == "real"
	assert doc.bundle["project"]["design"]["primary"] == "#2563eb"
	assert doc.bundle["jtbds"][0]["data_capture"][0]["pii"] is True
	assert "department" not in doc.bundle["jtbds"][0]["actor"]


def test_desktop_bundle_parser_accepts_authoring_metadata() -> None:
	bundle = create_default_bundle()
	bundle["jtbds"].append({
		**bundle["jtbds"][0],
		"id": "review_case",
		"title": "Review case",
		"requires": ["intake_case"],
		"version": "1.2.3",
		"status": "in_review",
	})

	assert parse_bundle(bundle) is bundle


def test_add_duplicate_and_remove_jobs_keeps_unique_ids() -> None:
	doc = JtbdDocument(create_default_bundle())

	second = doc.add_jtbd("Review Case")
	third = doc.duplicate_jtbd(second)
	doc.remove_jtbd(0)

	assert doc.jtbd_ids() == ["review_case", "review_case_copy"]
	assert doc.get_jtbd(third - 1)["status"] == "draft"
	assert doc.dirty


def test_remove_last_job_is_rejected() -> None:
	doc = JtbdDocument(create_default_bundle())

	try:
		doc.remove_jtbd(0)
	except ValueError as exc:
		assert "at least one job" in str(exc)
	else:  # pragma: no cover - defensive assertion.
		raise AssertionError("remove_jtbd should reject deleting the final job")


def test_validation_catches_canonical_schema_errors() -> None:
	bundle = create_default_bundle()
	bundle["jtbds"][0]["data_capture"][0] = {
		"id": "bad_field",
		"kind": "email",
		"label": "Bad field",
	}
	doc = JtbdDocument(bundle)

	result = doc.validate()

	assert not result.ok
	assert any("must declare pii" in error for error in result.errors)


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
	doc = JtbdDocument(create_default_bundle())
	doc.bundle["project"]["name"] = "Roundtrip"
	path = tmp_path / "jtbd-bundle.json"

	doc.save(path)
	loaded = JtbdDocument.load(path)

	assert not doc.dirty
	assert loaded.bundle == json.loads(path.read_text(encoding="utf-8"))
	assert loaded.bundle["project"]["name"] == "Roundtrip"


def test_document_input_is_copied() -> None:
	bundle = create_default_bundle()
	doc = JtbdDocument(bundle)
	doc.bundle["project"]["name"] = "Changed"

	assert bundle["project"]["name"] == "New Flowforge Project"


def test_normalise_id_produces_ascii_snake_case() -> None:
	assert normalise_id("  Review Case!  ") == "review_case"
	assert normalise_id("123") == "job"
	assert normalise_id("", fallback="fallback") == "fallback"


def test_sensitive_field_helper_matches_authoring_expectations() -> None:
	assert requires_pii("email")
	assert requires_pii("textarea")
	assert not requires_pii("number")


def test_desktop_command_is_registered_without_pyqt_import() -> None:
	result = runner.invoke(app, ["jtbd", "desktop", "--help"], terminal_width=140)

	assert result.exit_code == 0
	assert "Open the PyQt JTBD desktop editor" in result.output
	assert "--theme" in result.output


def test_missing_bundle_fails_before_gui_import(tmp_path: Path) -> None:
	missing = tmp_path / "missing.json"

	result = runner.invoke(app, ["jtbd", "desktop", "--bundle", str(missing)])

	assert result.exit_code == 1
	assert f"bundle not found: {missing}" in result.output
