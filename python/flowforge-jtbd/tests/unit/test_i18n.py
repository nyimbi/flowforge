"""Localisation layer tests (E-25).

Covers:

* :class:`LocaleCatalog` — basic accessors, register, merge, filter.
* :class:`LocaleRegistry` — fallback chain, multiple languages,
  ``get_or_key`` shorthand.
* :func:`keys_for_spec` — derives keys from JtbdSpec dicts (top-level
  text, fields, edge cases, notifications, success criteria).
* :func:`validate_catalog` — unknown-path errors + missing-translation
  warnings.
* :func:`load_catalog_from_path` / ``load_catalog_from_dir`` — JSON
  loaders.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import flowforge_jtbd.i18n.loader as loader_module
from flowforge_jtbd.i18n import (
    I18nIssue,
    LocaleCatalog,
    LocaleRegistry,
    keys_for_spec,
    load_catalog_from_dir,
    load_catalog_from_path,
    validate_catalog,
)
from flowforge_jtbd.i18n.loader import CatalogLoadError


# ---------------------------------------------------------------------------
# Spec fixture
# ---------------------------------------------------------------------------


def _spec(**overrides) -> dict:
    """Minimal spec dict that exercises every translatable shape."""
    base = {
        "id": "claim_intake",
        "title": "Submit a claim",
        "version": "1.0.0",
        "actor": {"role": "intake_clerk"},
        "situation": "A claimant submits a new claim through the portal.",
        "motivation": "Capture incident details and route for triage.",
        "outcome": "A claim record exists with status=intake.",
        "success_criteria": [
            "claim_id generated within 5 seconds",
            "intake form persisted",
        ],
        "data_capture": [
            {"id": "policy_id", "label": "Policy", "kind": "text"},
            {
                "id": "incident_date",
                "label": "Date",
                "kind": "date",
                "help": "When the incident happened.",
            },
        ],
        "edge_cases": [
            {"id": "policy_lapsed", "handle": "reject", "message": "Policy is lapsed."},
        ],
        "notifications": [
            {"trigger": "state_enter", "channel": "email", "audience": "claimant"},
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# LocaleCatalog
# ---------------------------------------------------------------------------


def test_catalog_construction() -> None:
    cat = LocaleCatalog(lang="en", entries={"x.title": "Hello"})
    assert cat.lang == "en"
    assert cat.has("x.title")
    assert cat.get("x.title") == "Hello"
    assert cat.get("missing") is None
    assert cat.get("missing", default="—") == "—"


def test_catalog_construction_strips_lang() -> None:
    cat = LocaleCatalog(lang="  fr  ")
    assert cat.lang == "fr"


def test_catalog_rejects_empty_lang() -> None:
    with pytest.raises(AssertionError):
        LocaleCatalog(lang="")


def test_catalog_register_adds_key() -> None:
    cat = LocaleCatalog(lang="en")
    cat.register("a.b", "value")
    assert cat.get("a.b") == "value"


def test_catalog_merge_overwrites_existing() -> None:
    cat = LocaleCatalog(lang="en", entries={"a": "old"})
    cat.merge({"a": "new", "b": "added"})
    assert cat.get("a") == "new"
    assert cat.get("b") == "added"


def test_catalog_merge_rejects_invalid_value_type() -> None:
    cat = LocaleCatalog(lang="en")
    with pytest.raises(ValueError):
        cat.merge({"a": 123})  # type: ignore[arg-type]


def test_catalog_merge_rejects_empty_key() -> None:
    cat = LocaleCatalog(lang="en")
    with pytest.raises(ValueError):
        cat.merge({"": "value"})


def test_catalog_filter_by_jtbd_scopes_correctly() -> None:
    cat = LocaleCatalog(
        lang="en",
        entries={
            "jtbd_a.title": "A",
            "jtbd_a.fields.x.label": "X",
            "jtbd_b.title": "B",
        },
    )
    out = cat.filter_by_jtbd("jtbd_a")
    assert set(out) == {"jtbd_a.title", "jtbd_a.fields.x.label"}


def test_catalog_filter_does_not_match_prefix_overlap() -> None:
    # 'jtbd_ab' should not match 'jtbd_a' filter — separator matters.
    cat = LocaleCatalog(
        lang="en",
        entries={
            "jtbd_a.title": "A",
            "jtbd_ab.title": "AB",
        },
    )
    out = cat.filter_by_jtbd("jtbd_a")
    assert "jtbd_ab.title" not in out


def test_catalog_entries_are_defensively_copied() -> None:
    source = {"x": "y"}
    cat = LocaleCatalog(lang="en", entries=source)
    source["x"] = "mutated"
    assert cat.get("x") == "y"


# ---------------------------------------------------------------------------
# LocaleRegistry
# ---------------------------------------------------------------------------


def test_registry_get_uses_requested_language_first() -> None:
    reg = LocaleRegistry()
    reg.register_catalog("en", {"x": "Hello"})
    reg.register_catalog("fr", {"x": "Bonjour"})
    assert reg.get("x", lang="fr") == "Bonjour"


def test_registry_falls_back_to_chain() -> None:
    reg = LocaleRegistry(fallback_chain=("en",))
    reg.register_catalog("en", {"x": "Hello"})
    # 'fr' has no entry; fallback to en.
    assert reg.get("x", lang="fr") == "Hello"


def test_registry_returns_none_when_unresolved() -> None:
    reg = LocaleRegistry(fallback_chain=())
    reg.register_catalog("fr", {"y": "Bonjour"})
    assert reg.get("x", lang="fr") is None


def test_registry_get_or_key_returns_key_when_unresolved() -> None:
    reg = LocaleRegistry(fallback_chain=())
    assert reg.get_or_key("missing.key", lang="fr") == "missing.key"


def test_registry_disable_fallback() -> None:
    reg = LocaleRegistry(fallback_chain=("en",))
    reg.register_catalog("en", {"x": "Hello"})
    # fallback=False suppresses the chain.
    assert reg.get("x", lang="fr", fallback=False) is None


def test_registry_register_replaces_existing() -> None:
    reg = LocaleRegistry()
    reg.register_catalog("en", {"x": "v1"})
    reg.register_catalog("en", {"x": "v2"})
    assert reg.get("x", lang="en") == "v2"


def test_registry_languages_returns_sorted_set() -> None:
    reg = LocaleRegistry()
    reg.register_catalog("fr", {})
    reg.register_catalog("en", {})
    reg.register_catalog("de", {})
    assert reg.languages() == ("de", "en", "fr")


def test_registry_register_catalog_object() -> None:
    reg = LocaleRegistry()
    cat = LocaleCatalog(lang="en", entries={"x": "hi"})
    reg.register_catalog("en", cat)
    assert reg.get("x", lang="en") == "hi"


# ---------------------------------------------------------------------------
# keys_for_spec
# ---------------------------------------------------------------------------


def test_keys_for_spec_covers_top_level_text() -> None:
    keys = keys_for_spec(_spec())
    assert "claim_intake.title" in keys
    assert "claim_intake.situation" in keys
    assert "claim_intake.motivation" in keys
    assert "claim_intake.outcome" in keys


def test_keys_for_spec_covers_fields() -> None:
    keys = keys_for_spec(_spec())
    assert "claim_intake.fields.policy_id.label" in keys
    # policy_id has no help → no help key.
    assert "claim_intake.fields.policy_id.help" not in keys
    # incident_date carries help text → help key emitted.
    assert "claim_intake.fields.incident_date.label" in keys
    assert "claim_intake.fields.incident_date.help" in keys


def test_keys_for_spec_covers_edge_cases() -> None:
    keys = keys_for_spec(_spec())
    assert "claim_intake.edge_cases.policy_lapsed.message" in keys


def test_keys_for_spec_covers_notifications() -> None:
    keys = keys_for_spec(_spec())
    assert "claim_intake.notifications.state_enter.subject" in keys
    assert "claim_intake.notifications.state_enter.body" in keys


def test_keys_for_spec_covers_success_criteria_indices() -> None:
    keys = keys_for_spec(_spec())
    assert "claim_intake.success_criteria[0]" in keys
    assert "claim_intake.success_criteria[1]" in keys


def test_keys_for_spec_skips_empty_optional_fields() -> None:
    spec = _spec(title="", data_capture=[], edge_cases=[], notifications=[])
    keys = keys_for_spec(spec)
    # title was empty → no key
    assert "claim_intake.title" not in keys
    # success_criteria still emit (kept by default in fixture)
    assert any(k.startswith("claim_intake.success_criteria") for k in keys)


def test_keys_for_spec_rejects_unknown_input() -> None:
    with pytest.raises(TypeError):
        keys_for_spec("not a spec")  # type: ignore[arg-type]


def test_keys_for_spec_requires_id() -> None:
    bad = dict(_spec())
    del bad["id"]
    with pytest.raises(ValueError):
        keys_for_spec(bad)


def test_keys_for_spec_accepts_jtbd_id_alias() -> None:
    """The lint-side spec uses 'jtbd_id' instead of 'id'."""
    bad = dict(_spec())
    del bad["id"]
    bad["jtbd_id"] = "renamed"
    keys = keys_for_spec(bad)
    assert any(k.startswith("renamed.") for k in keys)


def test_keys_for_spec_accepts_model_dump_and_skips_bad_nested_entries() -> None:
    class FakeSpec:
        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs == {"mode": "json", "exclude_none": False}
            return {
                "id": "model_spec",
                "title": "Model spec",
                "data_capture": [
                    "not-a-field",
                    {"id": "", "label": "blank"},
                    {"id": "description_only", "description": "Describe it"},
                ],
                "edge_cases": [
                    "not-an-edge",
                    {"name": "named_edge"},
                    {"id": ""},
                ],
                "notifications": [
                    "not-a-notification",
                    {"trigger": ""},
                    {"trigger": "approved"},
                ],
            }

    keys = keys_for_spec(FakeSpec())

    assert "model_spec.title" in keys
    assert "model_spec.fields.description_only.label" in keys
    assert "model_spec.fields.description_only.help" in keys
    assert "model_spec.edge_cases.named_edge.message" in keys
    assert "model_spec.notifications.approved.subject" in keys
    assert "model_spec.notifications.approved.body" in keys


# ---------------------------------------------------------------------------
# validate_catalog
# ---------------------------------------------------------------------------


def test_validate_emits_missing_translation_warnings() -> None:
    spec = _spec()
    cat = LocaleCatalog(
        lang="fr",
        entries={
            "claim_intake.title": "Soumettre une réclamation",
            # everything else is missing
        },
    )
    result = validate_catalog([spec], cat)
    assert result.lang == "fr"
    rules = {issue.rule for issue in result.warnings()}
    assert "missing_translation" in rules
    assert result.errors() == []
    # All warnings tagged with the source jtbd_id.
    assert all(issue.jtbd_id == "claim_intake" for issue in result.warnings())


def test_validate_emits_unknown_path_errors() -> None:
    spec = _spec()
    cat = LocaleCatalog(
        lang="fr",
        entries={
            "claim_intake.title": "Soumettre",
            "claim_intake.fields.ghost.label": "Fantôme",  # field doesn't exist
            "some_other_jtbd.title": "Other",  # whole jtbd not in bundle
        },
    )
    result = validate_catalog([spec], cat)
    error_keys = {issue.key for issue in result.errors()}
    assert "claim_intake.fields.ghost.label" in error_keys
    assert "some_other_jtbd.title" in error_keys


def test_validate_clean_catalog_has_no_errors() -> None:
    spec = _spec()
    expected_keys = keys_for_spec(spec)
    cat = LocaleCatalog(
        lang="en",
        entries={key: f"<{key}>" for key in expected_keys},
    )
    result = validate_catalog([spec], cat)
    assert result.ok
    assert result.errors() == []
    assert result.warnings() == []


def test_validate_handles_multiple_specs() -> None:
    a = _spec(id="a")
    b = _spec(id="b")
    cat = LocaleCatalog(lang="en", entries={"a.title": "A title"})
    # Note: the LocaleCatalog fixture knows _spec returns id='claim_intake' by
    # default; we override per spec to keep the test focused.
    for spec, jtbd_id in ((a, "a"), (b, "b")):
        assert _spec_id(spec) == jtbd_id

    result = validate_catalog([a, b], cat)
    # 'a.title' is satisfied; everything else for both jtbds → warnings.
    missing = {i.key for i in result.warnings()}
    assert any(k.startswith("a.") for k in missing)
    assert any(k.startswith("b.") for k in missing)


def test_validate_catalog_uses_unknown_owner_for_object_without_id() -> None:
    class FakeSpec:
        title = "Untitled"

        def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
            return {"jtbd_id": "dumped", "title": "Dumped title"}

    result = validate_catalog([FakeSpec()], LocaleCatalog(lang="en", entries={}))

    assert result.warnings()[0].jtbd_id == "<unknown>"


def test_validate_catalog_reads_object_id_attribute() -> None:
    class FakeSpec:
        id = "object_spec"

        def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
            return {"id": "object_spec", "title": "Object title"}

    result = validate_catalog([FakeSpec()], LocaleCatalog(lang="en", entries={}))

    assert result.warnings()[0].jtbd_id == "object_spec"


def _spec_id(spec) -> str:
    return spec.get("id") or spec.get("jtbd_id")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_catalog_from_path(tmp_path: Path) -> None:
    src = tmp_path / "fr.json"
    src.write_text(
        json.dumps(
            {
                "claim_intake.title": "Soumettre",
                "claim_intake.situation": "Le client soumet",
            }
        )
    )
    cat = load_catalog_from_path(src)
    assert cat.lang == "fr"
    assert cat.get("claim_intake.title") == "Soumettre"


def test_load_catalog_from_path_explicit_lang(tmp_path: Path) -> None:
    src = tmp_path / "translations.json"
    src.write_text(json.dumps({"a": "b"}))
    cat = load_catalog_from_path(src, lang="es")
    assert cat.lang == "es"


def test_load_catalog_from_path_rejects_non_object(tmp_path: Path) -> None:
    src = tmp_path / "en.json"
    src.write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(CatalogLoadError):
        load_catalog_from_path(src)


def test_load_catalog_from_path_rejects_bad_filename_without_lang(
    tmp_path: Path,
) -> None:
    src = tmp_path / "translations.json"
    src.write_text(json.dumps({"a": "b"}))
    with pytest.raises(CatalogLoadError, match="could not derive language"):
        load_catalog_from_path(src)


def test_load_catalog_from_path_rejects_invalid_json(tmp_path: Path) -> None:
    src = tmp_path / "en.json"
    src.write_text("{")
    with pytest.raises(CatalogLoadError, match="Expecting property name"):
        load_catalog_from_path(src)


def test_load_catalog_from_path_rejects_non_string_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    src = tmp_path / "en.json"
    src.write_text("{}")
    monkeypatch.setattr(loader_module.json, "loads", lambda _text: {1: "value"})
    with pytest.raises(CatalogLoadError, match="non-string key"):
        load_catalog_from_path(src)


def test_load_catalog_from_path_rejects_non_string_value(tmp_path: Path) -> None:
    src = tmp_path / "en.json"
    src.write_text(json.dumps({"a": 1}))
    with pytest.raises(CatalogLoadError):
        load_catalog_from_path(src)


def test_load_catalog_from_path_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CatalogLoadError):
        load_catalog_from_path(tmp_path / "missing.json")


def test_load_catalog_from_dir_collects_languages(tmp_path: Path) -> None:
    (tmp_path / "en.json").write_text(json.dumps({"x": "Hello"}))
    (tmp_path / "fr.json").write_text(json.dumps({"x": "Bonjour"}))
    (tmp_path / "nested").mkdir()
    (tmp_path / "README.md").write_text("not a catalog")
    (tmp_path / "fr_CA.json").write_text(json.dumps({"x": "Allô"}))

    out = load_catalog_from_dir(tmp_path)
    assert set(out) == {"en", "fr", "fr_CA"}
    assert out["en"].get("x") == "Hello"


def test_load_catalog_from_dir_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(CatalogLoadError):
        load_catalog_from_dir(tmp_path / "missing")


# ---------------------------------------------------------------------------
# I18nIssue type sanity
# ---------------------------------------------------------------------------


def test_i18n_issue_is_frozen() -> None:
    issue = I18nIssue(
        severity="warning",
        rule="missing_translation",
        key="x",
        jtbd_id="x",
        message="m",
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        issue.message = "different"  # type: ignore[misc]
