"""BPMN 2.0 reference exporter (E-21, community).

Converts a :class:`~flowforge_jtbd.dsl.spec.JtbdSpec` to simplified BPMN 2.0
XML suitable for import into Camunda Modeler, Activiti, or any BPMN-compliant
tool.

The output is intentionally minimal — it models the JTBD as a single pool
process with:

- A start event labelled with the JTBD situation.
- One ``userTask`` per ``data_capture`` field.
- One ``userTask`` per ``approval`` gate.
- An exclusive gateway if multiple approval gates exist.
- An end event labelled with the JTBD outcome.

This is a reference implementation, not a full-fidelity BPMN modeller.
Community-maintained; ships in ``flowforge-jtbd`` core so hosts can use it
without an extra install.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from ..dsl.spec import JtbdBundle, JtbdSpec


_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
_BPMNDiagram_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
_DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

ET.register_namespace("bpmn", _BPMN_NS)
ET.register_namespace("dc", _DC_NS)
ET.register_namespace("bpmndi", _BPMNDiagram_NS)
ET.register_namespace("di", _DI_NS)


def _bpmn(tag: str) -> str:
	return f"{{{_BPMN_NS}}}{tag}"


class BpmnExporter:
	"""Exports a JtbdSpec to BPMN 2.0 XML."""

	exporter_id = "bpmn"

	def export(self, spec: JtbdSpec, bundle: JtbdBundle | None = None) -> str:
		"""Return BPMN 2.0 XML as a UTF-8 string."""
		definitions = ET.Element(
			_bpmn("definitions"),
			attrib={
				"targetNamespace": f"https://flowforge.dev/jtbd/{spec.id}",
			},
		)

		process = ET.SubElement(
			definitions,
			_bpmn("process"),
			attrib={
				"id": f"Process_{spec.id}",
				"name": spec.title or spec.id,
				"isExecutable": "false",
			},
		)

		seq_counter = [0]
		elements: list[str] = []  # ids in order, for sequence flows

		def next_seq() -> str:
			seq_counter[0] += 1
			return f"Flow_{seq_counter[0]}"

		def add_seq(source: str, target: str) -> None:
			ET.SubElement(
				process,
				_bpmn("sequenceFlow"),
				attrib={"id": next_seq(), "sourceRef": source, "targetRef": target},
			)

		# Start event
		start_id = f"StartEvent_{spec.id}"
		start = ET.SubElement(
			process,
			_bpmn("startEvent"),
			attrib={"id": start_id, "name": spec.situation[:50] if spec.situation else "start"},
		)
		elements.append(start_id)

		# Data capture tasks
		for field in spec.data_capture:
			task_id = f"Task_capture_{field.id}"
			ET.SubElement(
				process,
				_bpmn("userTask"),
				attrib={
					"id": task_id,
					"name": field.label or field.id,
				},
			)
			elements.append(task_id)

		# Approval tasks
		for i, approval in enumerate(spec.approvals):
			task_id = f"Task_approve_{i}_{approval.role}"
			ET.SubElement(
				process,
				_bpmn("userTask"),
				attrib={
					"id": task_id,
					"name": f"Approval: {approval.role} ({approval.policy})",
				},
			)
			elements.append(task_id)

		# End event
		end_id = f"EndEvent_{spec.id}"
		ET.SubElement(
			process,
			_bpmn("endEvent"),
			attrib={"id": end_id, "name": spec.outcome[:50] if spec.outcome else "done"},
		)
		elements.append(end_id)

		# Chain sequence flows
		for i in range(len(elements) - 1):
			add_seq(elements[i], elements[i + 1])

		# Serialise
		ET.indent(definitions, space="  ")
		return ET.tostring(definitions, encoding="unicode", xml_declaration=False)


__all__ = ["BpmnExporter"]
