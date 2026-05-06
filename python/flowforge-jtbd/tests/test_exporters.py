"""Tests for E-21 Plugin SDK (JtbdExporter) + BPMN + storymap exporters."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from flowforge_jtbd.dsl.spec import JtbdBundle, JtbdSpec
from flowforge_jtbd.exporters import ExporterRegistry, JtbdExporter, available_exporters, export, register
from flowforge_jtbd.exporters.bpmn import BpmnExporter
from flowforge_jtbd.exporters.storymap import StorymapExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _spec(jtbd_id: str = "claim_intake", **extra: Any) -> JtbdSpec:
	data: dict[str, Any] = {
		"id": jtbd_id,
		"actor": {"role": "user"},
		"situation": "policyholder files an FNOL",
		"motivation": "recover losses",
		"outcome": "claim accepted",
		"success_criteria": ["claim queued within SLA"],
	}
	data.update(extra)
	return JtbdSpec.model_validate(data)


def _spec_with_fields() -> JtbdSpec:
	return _spec(
		data_capture=[
			{"id": "claimant_name", "kind": "text", "label": "Name", "pii": True},
			{"id": "loss_amount", "kind": "money", "label": "Loss Amount", "pii": False},
		],
		approvals=[
			{"role": "supervisor", "policy": "1_of_1"},
		],
	)


# ---------------------------------------------------------------------------
# JtbdExporter protocol
# ---------------------------------------------------------------------------


def test_bpmn_exporter_satisfies_protocol() -> None:
	assert isinstance(BpmnExporter(), JtbdExporter)


def test_storymap_exporter_satisfies_protocol() -> None:
	assert isinstance(StorymapExporter(), JtbdExporter)


def test_non_exporter_rejected_at_register() -> None:
	registry = ExporterRegistry()
	with pytest.raises(AssertionError):
		registry.register(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ExporterRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get() -> None:
	registry = ExporterRegistry()
	registry.register(BpmnExporter())
	assert registry.get("bpmn") is not None


def test_registry_ids_sorted() -> None:
	registry = ExporterRegistry()
	registry.register(StorymapExporter())
	registry.register(BpmnExporter())
	ids = registry.ids()
	assert ids == sorted(ids)


def test_registry_duplicate_raises() -> None:
	registry = ExporterRegistry()
	registry.register(BpmnExporter())
	with pytest.raises(ValueError, match="already registered"):
		registry.register(BpmnExporter())


def test_registry_replace_overwrites() -> None:
	registry = ExporterRegistry()
	registry.register(BpmnExporter())
	registry.replace(BpmnExporter())  # should not raise
	assert registry.get("bpmn") is not None


def test_registry_unregister() -> None:
	registry = ExporterRegistry()
	registry.register(BpmnExporter())
	registry.unregister("bpmn")
	assert registry.get("bpmn") is None


def test_registry_export_unknown_raises() -> None:
	registry = ExporterRegistry()
	with pytest.raises(KeyError):
		registry.export("nope", _spec())


# ---------------------------------------------------------------------------
# BPMN exporter
# ---------------------------------------------------------------------------


def test_bpmn_exporter_id() -> None:
	assert BpmnExporter().exporter_id == "bpmn"


def test_bpmn_minimal_spec_produces_xml() -> None:
	xml_str = BpmnExporter().export(_spec())
	assert xml_str.strip().startswith("<")
	root = ET.fromstring(xml_str)
	assert "definitions" in root.tag


def test_bpmn_contains_start_end_events() -> None:
	xml_str = BpmnExporter().export(_spec())
	root = ET.fromstring(xml_str)
	ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
	proc = root.find("bpmn:process", ns)
	assert proc is not None
	assert proc.find("bpmn:startEvent", ns) is not None
	assert proc.find("bpmn:endEvent", ns) is not None


def test_bpmn_data_capture_becomes_user_tasks() -> None:
	xml_str = BpmnExporter().export(_spec_with_fields())
	root = ET.fromstring(xml_str)
	ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
	proc = root.find("bpmn:process", ns)
	assert proc is not None
	tasks = proc.findall("bpmn:userTask", ns)
	task_names = [t.get("name", "") for t in tasks]
	assert any("Name" in n for n in task_names)
	assert any("Loss Amount" in n for n in task_names)


def test_bpmn_approval_becomes_user_task() -> None:
	xml_str = BpmnExporter().export(_spec_with_fields())
	root = ET.fromstring(xml_str)
	ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
	proc = root.find("bpmn:process", ns)
	assert proc is not None
	tasks = proc.findall("bpmn:userTask", ns)
	assert any("supervisor" in (t.get("name") or "") for t in tasks)


def test_bpmn_has_sequence_flows() -> None:
	xml_str = BpmnExporter().export(_spec_with_fields())
	root = ET.fromstring(xml_str)
	ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
	proc = root.find("bpmn:process", ns)
	assert proc is not None
	flows = proc.findall("bpmn:sequenceFlow", ns)
	assert len(flows) >= 1


# ---------------------------------------------------------------------------
# Story-map exporter
# ---------------------------------------------------------------------------


def test_storymap_exporter_id() -> None:
	assert StorymapExporter().exporter_id == "storymap"


def test_storymap_minimal_spec() -> None:
	result = json.loads(StorymapExporter().export(_spec()))
	assert result["epic"]["id"] == "claim_intake"
	assert "stories" in result
	assert "edge_cases" in result


def test_storymap_data_capture_becomes_stories() -> None:
	result = json.loads(StorymapExporter().export(_spec_with_fields()))
	story_titles = [s["title"] for s in result["stories"]]
	assert any("Name" in t for t in story_titles)
	assert any("Loss Amount" in t for t in story_titles)


def test_storymap_approval_becomes_story() -> None:
	result = json.loads(StorymapExporter().export(_spec_with_fields()))
	kinds = [s["kind"] for s in result["stories"]]
	assert "approval" in kinds


def test_storymap_success_criteria_in_acceptance_stories() -> None:
	result = json.loads(StorymapExporter().export(_spec()))
	criteria_stories = [s for s in result["stories"] if s["kind"] == "acceptance"]
	assert len(criteria_stories) >= 1


def test_storymap_epic_has_situation_motivation_outcome() -> None:
	result = json.loads(StorymapExporter().export(_spec()))
	epic = result["epic"]
	assert epic["situation"] == "policyholder files an FNOL"
	assert epic["motivation"] == "recover losses"
	assert epic["outcome"] == "claim accepted"
