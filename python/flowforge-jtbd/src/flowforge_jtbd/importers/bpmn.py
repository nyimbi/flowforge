"""BPMN 2.0 importer — converts BPMN XML to flowforge WorkflowDef.

Parses a simplified BPMN 2.0 process (single pool, no sub-processes) and
emits a :class:`flowforge.dsl.workflow_def.WorkflowDef` JSON dict.

Supported BPMN elements:
* ``startEvent`` → initial state (automatic kind)
* ``endEvent`` → terminal_success or terminal_fail state
* ``userTask`` → manual_review state
* ``serviceTask``, ``scriptTask``, ``task`` → automatic state
* ``exclusiveGateway``, ``parallelGateway`` → mapped to automatic or
  parallel_fork / parallel_join depending on incoming/outgoing count
* ``sequenceFlow`` → transitions (event name = flow id or label)

Usage::

    from flowforge_jtbd.importers.bpmn import BpmnImporter

    importer = BpmnImporter()
    wd_dict = importer.parse(bpmn_xml_string)
    # wd_dict is a dict matching WorkflowDef schema
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def _bpmn(tag: str) -> str:
	return f"{{{_BPMN_NS}}}{tag}"


def _local(tag: str) -> str:
	"""Strip namespace from an ElementTree tag."""
	return re.sub(r"^\{[^}]+\}", "", tag)


def _clean_id(s: str) -> str:
	"""Convert a BPMN element ID to a valid state/transition name."""
	return re.sub(r"[^a-zA-Z0-9_]", "_", s).strip("_").lower() or "unnamed"


class BpmnImportError(ValueError):
	"""Raised when the BPMN document cannot be parsed into a WorkflowDef."""


class BpmnImporter:
	"""Parse BPMN 2.0 XML and produce a :class:`~flowforge.dsl.workflow_def.WorkflowDef` dict.

	The importer supports BPMN with or without explicit namespaces — it
	matches both ``{http://...BPMN/20100524/MODEL}startEvent`` and bare
	``startEvent`` tags.
	"""

	def parse(self, xml_text: str) -> dict[str, Any]:
		"""Parse *xml_text* and return a WorkflowDef-compatible dict.

		Raises :class:`BpmnImportError` if the document contains no process.
		"""
		root = ET.fromstring(xml_text)
		process = self._find_process(root)
		if process is None:
			raise BpmnImportError("No <process> element found in BPMN document")

		process_id = _clean_id(process.get("id") or "workflow")
		process_name = process.get("name") or process_id

		states: list[dict[str, Any]] = []
		transitions: list[dict[str, Any]] = []
		initial_state: str | None = None

		# Collect all flow elements
		elements: dict[str, dict[str, Any]] = {}  # id → {kind, name, ...}
		outgoing: dict[str, list[str]] = {}  # element_id → [flow_ids]
		incoming: dict[str, list[str]] = {}  # element_id → [flow_ids]
		flows: dict[str, dict[str, Any]] = {}  # flow_id → {source, target, name}

		for child in process:
			tag = _local(child.tag)
			elem_id = child.get("id") or ""
			elem_name = child.get("name") or _clean_id(elem_id)

			if tag == "startEvent":
				elements[elem_id] = {"tag": "startEvent", "name": _clean_id(elem_id), "label": elem_name}
				initial_state = _clean_id(elem_id)
			elif tag == "endEvent":
				end_name = child.get("name") or ""
				is_fail = "fail" in end_name.lower() or "error" in end_name.lower() or "cancel" in end_name.lower()
				elements[elem_id] = {
					"tag": "endEvent",
					"name": _clean_id(elem_id),
					"label": elem_name,
					"is_fail": is_fail,
				}
			elif tag == "userTask":
				elements[elem_id] = {"tag": "userTask", "name": _clean_id(elem_id), "label": elem_name}
			elif tag in ("serviceTask", "scriptTask", "task", "callActivity"):
				elements[elem_id] = {"tag": "serviceTask", "name": _clean_id(elem_id), "label": elem_name}
			elif tag in ("exclusiveGateway", "inclusiveGateway"):
				elements[elem_id] = {"tag": "exclusiveGateway", "name": _clean_id(elem_id), "label": elem_name}
			elif tag == "parallelGateway":
				elements[elem_id] = {"tag": "parallelGateway", "name": _clean_id(elem_id), "label": elem_name}
			elif tag == "sequenceFlow":
				flow_id = elem_id
				source = child.get("sourceRef", "")
				target = child.get("targetRef", "")
				flow_name = child.get("name") or flow_id
				flows[flow_id] = {"source": source, "target": target, "name": flow_name}
				outgoing.setdefault(source, []).append(flow_id)
				incoming.setdefault(target, []).append(flow_id)

		if not elements:
			raise BpmnImportError("No flow elements found in BPMN process")

		# Determine initial state
		if initial_state is None:
			# Fall back to first element with no incoming flows
			for eid, elem in elements.items():
				if not incoming.get(eid):
					initial_state = elem["name"]
					break
		if initial_state is None:
			raise BpmnImportError("Cannot determine initial state — no startEvent or source-less element")

		# Build states
		for eid, elem in elements.items():
			tag = elem["tag"]
			name = elem["name"]
			out_count = len(outgoing.get(eid, []))
			inc_count = len(incoming.get(eid, []))

			if tag == "startEvent":
				kind: str = "automatic"
			elif tag == "endEvent":
				kind = "terminal_fail" if elem.get("is_fail") else "terminal_success"
			elif tag == "userTask":
				kind = "manual_review"
			elif tag == "parallelGateway":
				# Parallel fork if multiple outgoing, parallel join if multiple incoming
				kind = "parallel_join" if inc_count > 1 else "parallel_fork"
			else:
				# serviceTask, exclusiveGateway — automatic
				kind = "automatic"

			states.append({"name": name, "kind": kind})

		# Build transitions from sequence flows
		transition_counter = [0]

		def next_t_id() -> str:
			transition_counter[0] += 1
			return f"t_{transition_counter[0]:03d}"

		for flow_id, flow in flows.items():
			source_elem = elements.get(flow["source"])
			target_elem = elements.get(flow["target"])
			if source_elem is None or target_elem is None:
				continue
			flow_name_raw = flow["name"] or flow_id
			event_name = re.sub(r"[^a-zA-Z0-9_]", "_", flow_name_raw).strip("_").lower() or f"event_{next_t_id()}"
			transitions.append({
				"id": next_t_id(),
				"event": event_name,
				"from_state": source_elem["name"],
				"to_state": target_elem["name"],
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			})

		return {
			"key": process_id,
			"version": "1.0.0",
			"subject_kind": process_id,
			"initial_state": initial_state,
			"metadata": {"source": "bpmn_import", "bpmn_process_name": process_name},
			"states": states,
			"transitions": transitions,
			"escalations": [],
		}

	def _find_process(self, root: ET.Element) -> ET.Element | None:
		"""Find the first <process> element anywhere in the tree."""
		# Try with namespace
		for elem in root.iter(_bpmn("process")):
			return elem
		# Try without namespace (bare BPMN)
		for elem in root.iter("process"):
			if _local(elem.tag) == "process":
				return elem
		return None


__all__ = ["BpmnImporter", "BpmnImportError"]
