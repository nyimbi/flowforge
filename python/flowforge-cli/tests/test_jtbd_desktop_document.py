"""Tests for the optional JTBD desktop editor document model."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.jtbd_desktop.document import (
	JtbdDocument,
	build_ai_authoring_prompt,
	build_template_from_jtbd,
	create_default_bundle,
	create_jtbd_from_prompt,
	create_jtbd_from_template,
	create_template_library,
	load_template_library,
	normalise_id,
	requires_pii,
	save_template_library,
	verify_generation,
)
from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.parse import parse_bundle
from flowforge_cli.main import app
from flowforge_jtbd.dsl.spec import JtbdSpec


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
	assert doc.bundle["project"]["annotations"]["tags"] == ["draft"]


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


def test_annotations_are_schema_and_generator_compatible() -> None:
	bundle = create_default_bundle()
	bundle["project"]["annotations"]["notes"] = "Reviewed with operations."
	bundle["jtbds"][0]["annotations"]["owner"] = "ops"

	assert parse_bundle(bundle) is bundle
	assert generate(bundle)


def test_annotations_do_not_change_jtbd_spec_hash() -> None:
	bundle = create_default_bundle()
	spec = JtbdSpec.model_validate(bundle["jtbds"][0])
	annotated = spec.model_copy(
		update={"annotations": {"notes": "Reviewed by operations"}}
	)

	assert annotated.compute_hash() == spec.compute_hash()


def test_add_duplicate_and_remove_jobs_keeps_unique_ids() -> None:
	doc = JtbdDocument(create_default_bundle())

	second = doc.add_jtbd("Review Case")
	third = doc.duplicate_jtbd(second)
	doc.remove_jtbd(0)

	assert doc.jtbd_ids() == ["review_case", "review_case_copy"]
	assert doc.get_jtbd(third - 1)["status"] == "draft"
	assert doc.dirty


def test_visual_composition_dependencies_are_managed_safely() -> None:
	doc = JtbdDocument(create_default_bundle())
	review = doc.add_jtbd("Review case")

	doc.add_dependency(review, "intake_case")

	assert doc.get_jtbd(review)["requires"] == ["intake_case"]
	assert doc.dirty

	# Duplicate adds are idempotent so repeated visual edge creation does not
	# produce invalid duplicate requires entries.
	doc.add_dependency(review, "intake_case")
	assert doc.get_jtbd(review)["requires"] == ["intake_case"]

	doc.remove_dependency(review, "intake_case")
	assert doc.get_jtbd(review)["requires"] == []


def test_renaming_and_removing_jobs_updates_visual_dependencies() -> None:
	doc = JtbdDocument(create_default_bundle())
	review = doc.add_jtbd("Review case")
	close = doc.add_jtbd("Close case")
	doc.add_dependency(review, "intake_case")
	doc.add_dependency(close, "review_case")

	doc.rename_jtbd(review, "quality_review")

	assert doc.get_jtbd(close)["requires"] == ["quality_review"]
	assert doc.get_jtbd(review)["id"] == "quality_review"

	doc.remove_jtbd(review)

	assert doc.get_jtbd(close - 1)["requires"] == []


def test_renaming_jobs_rejects_empty_or_duplicate_ids() -> None:
	doc = JtbdDocument(create_default_bundle())
	doc.add_jtbd("Review case")

	for bad in ("", "intake_case"):
		try:
			doc.rename_jtbd(1, bad)
		except ValueError:
			pass
		else:  # pragma: no cover - defensive assertion.
			raise AssertionError(f"invalid rename should be rejected: {bad!r}")


def test_visual_composition_rejects_invalid_dependencies() -> None:
	doc = JtbdDocument(create_default_bundle())
	review = doc.add_jtbd("Review case")

	for bad in ("review_case", "missing_job", ""):
		try:
			doc.add_dependency(review, bad)
		except ValueError:
			pass
		else:  # pragma: no cover - defensive assertion.
			raise AssertionError(f"invalid dependency should be rejected: {bad!r}")


def test_add_from_template_and_prompt_manage_unique_jtbd_list() -> None:
	doc = JtbdDocument(create_default_bundle())
	library = create_template_library()

	template_index = doc.add_jtbd_from_template(library["templates"][0])
	prompt_index = doc.add_jtbd_from_prompt("Collect customer email and payment amount for approval")
	direct_draft = create_jtbd_from_prompt(
		"Screen new vendor tax form and contact email",
		{"screen_new_vendor_tax_form_and_contact"},
	)

	assert doc.get_jtbd(template_index)["annotations"]["source_template"] == "approval_intake"
	assert doc.get_jtbd(prompt_index)["annotations"]["ai_assist"]["review_required"] is True
	assert len(set(doc.jtbd_ids())) == len(doc.jtbd_ids())
	assert any(f["kind"] == "email" for f in doc.get_jtbd(prompt_index)["data_capture"])
	assert any(f["kind"] == "money" for f in doc.get_jtbd(prompt_index)["data_capture"])
	assert direct_draft["id"] == "screen_new_vendor_tax_form_and_contact_2"
	assert any(f["kind"] == "email" for f in direct_draft["data_capture"])


def test_template_library_roundtrip(tmp_path: Path) -> None:
	library = create_template_library()
	path = tmp_path / "templates.json"

	save_template_library(path, library)
	loaded = load_template_library(path)

	assert loaded == json.loads(path.read_text(encoding="utf-8"))
	assert loaded["templates"][0]["id"] == "approval_intake"


def test_template_export_and_ai_prompt() -> None:
	bundle = create_default_bundle()
	template = build_template_from_jtbd(bundle["jtbds"][0], description="Reusable intake")
	jtbd = create_jtbd_from_template(template, {"intake_case"})
	prompt = build_ai_authoring_prompt(bundle, bundle["jtbds"][0])

	assert template["description"] == "Reusable intake"
	assert jtbd["id"] == "intake_case_2"
	assert "Selected JTBD JSON" in prompt


def test_templates_and_duplicates_strip_storage_metadata() -> None:
	bundle = create_default_bundle()
	storage_keys = {
		"spec_hash": "sha256:" + "a" * 64,
		"parent_version_id": "v0",
		"replaced_by": "new_intake",
		"created_by": "author-1",
		"published_by": "publisher-1",
	}
	bundle["jtbds"][0].update(storage_keys)
	template = build_template_from_jtbd(bundle["jtbds"][0])
	materialized = create_jtbd_from_template(template, set())
	doc = JtbdDocument(bundle)
	duplicate_index = doc.duplicate_jtbd(0)

	for candidate in (template["jtbd"], materialized, doc.get_jtbd(duplicate_index)):
		for key in storage_keys:
			assert key not in candidate


def test_verify_generation_reports_emitted_files() -> None:
	result = verify_generation(create_default_bundle())

	assert result.ok
	assert result.errors == []
	assert any("generation emits" in info for info in result.infos)


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


def test_validation_treats_lint_errors_as_blocking() -> None:
	bundle = create_default_bundle()
	bundle["jtbds"][0]["requires"] = ["ghost_job"]
	doc = JtbdDocument(bundle)

	result = doc.validate()

	assert not result.ok
	assert any("requires_unknown_jtbd" in error for error in result.errors)


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
