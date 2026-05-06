"""Tests for E-27 — TemplateCache + 12 starter templates.

Covers:
- TemplateParameter model
- JtbdTemplate model and instantiate
- TemplateCache: register, get, list_ids, instantiate, load_library, search
- TemplateCache.default() loads all 12 starter templates
- Parameter fill correctness and error cases
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowforge_jtbd.templates import JtbdTemplate, TemplateCache, TemplateParameter
from flowforge_jtbd.templates.cache import _fill


# ---------------------------------------------------------------------------
# TemplateParameter
# ---------------------------------------------------------------------------

def test_template_parameter_fields() -> None:
	p = TemplateParameter(name="workflow_key", type="string", required=True)
	assert p.name == "workflow_key"
	assert p.type == "string"
	assert p.required is True
	assert p.default is None


def test_template_parameter_with_default() -> None:
	p = TemplateParameter(name="count", type="integer", required=False, default=2)
	assert p.default == 2


# ---------------------------------------------------------------------------
# _fill helper
# ---------------------------------------------------------------------------

def test_fill_replaces_placeholder_in_string() -> None:
	assert _fill("Hello {{name}}", {"name": "world"}) == "Hello world"


def test_fill_replaces_in_nested_dict() -> None:
	obj = {"key": "{{k}}", "nested": {"x": "{{k}}"}}
	result = _fill(obj, {"k": "val"})
	assert result == {"key": "val", "nested": {"x": "val"}}


def test_fill_replaces_in_list() -> None:
	assert _fill(["{{a}}", "{{b}}"], {"a": "x", "b": "y"}) == ["x", "y"]


def test_fill_leaves_unknown_placeholder() -> None:
	assert _fill("{{unknown}}", {}) == "{{unknown}}"


def test_fill_integer_param_becomes_string() -> None:
	assert _fill("count {{n}}", {"n": 3}) == "count 3"


def test_fill_does_not_mutate_original() -> None:
	obj = {"key": "{{k}}"}
	_fill(obj, {"k": "v"})
	assert obj["key"] == "{{k}}"  # deep-copied before fill


# ---------------------------------------------------------------------------
# JtbdTemplate
# ---------------------------------------------------------------------------

def _simple_template() -> JtbdTemplate:
	params = [
		TemplateParameter(name="workflow_key", type="string"),
		TemplateParameter(name="subject_kind", type="string"),
	]
	wf = {
		"key": "{{workflow_key}}",
		"subject_kind": "{{subject_kind}}",
		"initial_state": "open",
		"states": [{"name": "open", "kind": "manual_review"}, {"name": "done", "kind": "terminal_success"}],
		"transitions": [{"id": "close", "event": "close", "from_state": "open", "to_state": "done"}],
	}
	t = JtbdTemplate(
		id="simple",
		name="Simple",
		description="A simple two-state workflow.",
		parameters=params,
		workflow_template=wf,
		tags=["test"],
	)
	return t


def test_template_instantiate_fills_params() -> None:
	t = _simple_template()
	wf = t.instantiate({"workflow_key": "claim", "subject_kind": "claim"})
	assert wf["key"] == "claim"
	assert wf["subject_kind"] == "claim"


def test_template_instantiate_raises_on_missing_required() -> None:
	t = _simple_template()
	with pytest.raises(ValueError, match="workflow_key"):
		t.instantiate({"subject_kind": "claim"})


def test_template_param_names() -> None:
	t = _simple_template()
	assert t.param_names() == {"workflow_key", "subject_kind"}


def test_template_from_dict() -> None:
	data = {
		"id": "t1",
		"name": "T1",
		"description": "desc",
		"parameters": [{"name": "x", "type": "string"}],
		"workflow_template": {"key": "{{x}}"},
		"tags": ["a"],
	}
	t = JtbdTemplate.from_dict(data)
	assert t.id == "t1"
	assert len(t.parameters) == 1
	assert t.tags == ["a"]


def test_template_from_dict_defaults_optional_param() -> None:
	data = {
		"id": "t2",
		"name": "T2",
		"description": "",
		"parameters": [
			{"name": "required_approvals", "type": "integer", "required": False, "default": 2}
		],
		"workflow_template": {"needed": "{{required_approvals}}"},
	}
	t = JtbdTemplate.from_dict(data)
	wf = t.instantiate({})
	assert wf["needed"] == "2"


# ---------------------------------------------------------------------------
# TemplateCache
# ---------------------------------------------------------------------------

def test_template_cache_register_and_get() -> None:
	cache = TemplateCache()
	t = _simple_template()
	cache.register(t)
	assert cache.get("simple") is t


def test_template_cache_get_missing_returns_none() -> None:
	assert TemplateCache().get("nonexistent") is None


def test_template_cache_list_ids_sorted() -> None:
	cache = TemplateCache()
	cache.register(_simple_template())
	assert cache.list_ids() == ["simple"]


def test_template_cache_size() -> None:
	cache = TemplateCache()
	cache.register(_simple_template())
	assert cache.size() == 1


def test_template_cache_instantiate() -> None:
	cache = TemplateCache()
	cache.register(_simple_template())
	wf = cache.instantiate("simple", {"workflow_key": "my_wf", "subject_kind": "claim"})
	assert wf["key"] == "my_wf"


def test_template_cache_instantiate_missing_template_raises() -> None:
	with pytest.raises(KeyError):
		TemplateCache().instantiate("nonexistent")


def test_template_cache_list_templates_sorted() -> None:
	cache = TemplateCache()
	t1 = _simple_template()
	t1.id = "zzz"  # type: ignore[misc]
	cache.register(t1)
	t2 = JtbdTemplate(id="aaa", name="A", description="", parameters=[], workflow_template={})
	cache.register(t2)
	ids = [t.id for t in cache.list_templates()]
	assert ids == ["aaa", "zzz"]


def test_template_cache_search_by_tag() -> None:
	cache = TemplateCache()
	t = _simple_template()
	cache.register(t)  # has tag "test"
	results = cache.search("test")
	assert len(results) == 1
	assert results[0].id == "simple"


def test_template_cache_search_missing_tag() -> None:
	cache = TemplateCache()
	cache.register(_simple_template())
	assert cache.search("nosuch") == []


def test_template_cache_load_library(tmp_path: Path) -> None:
	data = {
		"id": "lib_tmpl",
		"name": "Library Template",
		"description": "",
		"parameters": [],
		"workflow_template": {},
	}
	(tmp_path / "lib_tmpl.json").write_text(json.dumps(data), encoding="utf-8")
	cache = TemplateCache()
	loaded = cache.load_library(tmp_path)
	assert loaded == 1
	assert cache.get("lib_tmpl") is not None


def test_template_cache_load_library_skips_malformed(tmp_path: Path) -> None:
	(tmp_path / "bad.json").write_text("not json", encoding="utf-8")
	cache = TemplateCache()
	loaded = cache.load_library(tmp_path)
	assert loaded == 0


# ---------------------------------------------------------------------------
# TemplateCache.default() — 12 starter templates
# ---------------------------------------------------------------------------

def test_default_cache_loads_twelve_templates() -> None:
	cache = TemplateCache.default()
	assert cache.size() == 12


def test_default_cache_has_all_expected_ids() -> None:
	cache = TemplateCache.default()
	expected = {
		"n_of_m_approval", "document_collection", "escalation_chain",
		"audit_trail", "sla_monitor", "dual_approval", "parallel_review",
		"sequential_stages", "notification_dispatch", "data_capture_wizard",
		"delegation_handler", "retry_with_backoff",
	}
	assert set(cache.list_ids()) == expected


def test_default_cache_n_of_m_approval_instantiates() -> None:
	cache = TemplateCache.default()
	wf = cache.instantiate("n_of_m_approval", {
		"workflow_key": "claim_approval",
		"subject_kind": "claim",
		"required_approvals": 2,
		"approval_permission": "claim.approve",
	})
	assert wf["key"] == "claim_approval"
	assert wf["subject_kind"] == "claim"


def test_default_cache_document_collection_instantiates() -> None:
	cache = TemplateCache.default()
	wf = cache.instantiate("document_collection", {
		"workflow_key": "kyc_docs",
		"subject_kind": "kyc",
	})
	assert wf["key"] == "kyc_docs"
	assert wf["initial_state"] == "collecting"


def test_default_cache_escalation_chain_has_two_levels() -> None:
	cache = TemplateCache.default()
	wf = cache.instantiate("escalation_chain", {
		"workflow_key": "esc_wf", "subject_kind": "case",
	})
	state_names = {s["name"] for s in wf["states"]}
	assert "l1_review" in state_names
	assert "l2_review" in state_names


def test_default_cache_retry_with_backoff_has_retry_state() -> None:
	cache = TemplateCache.default()
	wf = cache.instantiate("retry_with_backoff", {
		"workflow_key": "api_call", "subject_kind": "request",
	})
	state_names = {s["name"] for s in wf["states"]}
	assert "retrying" in state_names
	assert "permanently_failed" in state_names


def test_default_cache_all_templates_instantiate_with_minimal_params() -> None:
	"""Smoke test: every template can instantiate with workflow_key + subject_kind."""
	cache = TemplateCache.default()
	for tmpl in cache.list_templates():
		wf = cache.instantiate(tmpl.id, {
			"workflow_key": f"{tmpl.id}_test",
			"subject_kind": "item",
		})
		assert wf["key"] == f"{tmpl.id}_test"


def test_default_cache_templates_have_tags() -> None:
	cache = TemplateCache.default()
	for tmpl in cache.list_templates():
		assert len(tmpl.tags) >= 2, f"{tmpl.id} has too few tags"
