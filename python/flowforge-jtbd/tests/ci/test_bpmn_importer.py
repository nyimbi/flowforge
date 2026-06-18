"""Tests for the BPMN 2.0 importer."""

import pytest

from flowforge_jtbd.importers.bpmn import BpmnImporter, BpmnImportError
from flowforge.dsl.workflow_def import WorkflowDef


_SIMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="https://test.example">
  <bpmn:process id="TestProcess" name="Test Process" isExecutable="false">
    <bpmn:startEvent id="Start_1" name="start"/>
    <bpmn:userTask id="Task_review" name="Review Application"/>
    <bpmn:endEvent id="End_1" name="approved"/>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start_1" targetRef="Task_review" name="begin_review"/>
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_review" targetRef="End_1" name="approve"/>
  </bpmn:process>
</definitions>
"""

_NO_NS_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions>
  <process id="Proc1" name="Simple">
    <startEvent id="s1"/>
    <endEvent id="e1"/>
    <sequenceFlow id="f1" sourceRef="s1" targetRef="e1" name="go"/>
  </process>
</definitions>
"""


def test_parse_simple_bpmn():
	importer = BpmnImporter()
	result = importer.parse(_SIMPLE_BPMN)
	assert result["key"] == "testprocess"
	state_names = [s["name"] for s in result["states"]]
	assert "start_1" in state_names
	assert "task_review" in state_names
	assert "end_1" in state_names
	# user task → manual_review
	task = next(s for s in result["states"] if s["name"] == "task_review")
	assert task["kind"] == "manual_review"
	# end event → terminal_success
	end = next(s for s in result["states"] if s["name"] == "end_1")
	assert end["kind"] == "terminal_success"
	# 2 transitions
	assert len(result["transitions"]) == 2
	# initial state is the start event
	assert result["initial_state"] == "start_1"


def test_parse_no_namespace_bpmn():
	importer = BpmnImporter()
	result = importer.parse(_NO_NS_BPMN)
	assert result["key"] == "proc1"
	assert len(result["states"]) == 2


def test_parse_produces_valid_workflow_def():
	importer = BpmnImporter()
	result = importer.parse(_SIMPLE_BPMN)
	# WorkflowDef validation should not raise
	wd = WorkflowDef(**result)
	assert wd.key == "testprocess"
	assert wd.initial_state == "start_1"


def test_parse_empty_raises():
	importer = BpmnImporter()
	with pytest.raises(BpmnImportError):
		importer.parse("<definitions/>")


def test_fail_end_event():
	xml = """<definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
	  <bpmn:process id="P1">
	    <bpmn:startEvent id="s1"/>
	    <bpmn:endEvent id="e_fail" name="fail and cancel"/>
	    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="e_fail" name="abort"/>
	  </bpmn:process>
	</definitions>"""
	importer = BpmnImporter()
	result = importer.parse(xml)
	end = next(s for s in result["states"] if s["name"] == "e_fail")
	assert end["kind"] == "terminal_fail"
