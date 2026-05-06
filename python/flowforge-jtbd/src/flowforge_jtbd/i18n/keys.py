"""Catalog-key derivation for JTBD specs.

Walks a :class:`flowforge_jtbd.dsl.JtbdSpec` (or its dict form) and
returns the canonical set of catalog keys defined in
``framework/docs/jtbd-editor-arch.md`` §23.17:

* ``<jtbd_id>.title``
* ``<jtbd_id>.situation`` / ``.motivation`` / ``.outcome``
* ``<jtbd_id>.fields.<field_id>.label`` / ``.help``
* ``<jtbd_id>.edge_cases.<edge_id>.message``
* ``<jtbd_id>.notifications.<trigger>.subject`` / ``.body``
* ``<jtbd_id>.success_criteria[<i>]``

The function is dict-tolerant so it can run on raw bundle JSON without
forcing a Pydantic round-trip.
"""

from __future__ import annotations

from typing import Any


_TOP_LEVEL_FIELDS: tuple[str, ...] = (
	"title",
	"situation",
	"motivation",
	"outcome",
)


def _spec_dict(spec: Any) -> dict[str, Any]:
	"""Coerce *spec* (Pydantic model or dict) to a plain dict."""
	if isinstance(spec, dict):
		return spec
	# Pydantic v2 BaseModel
	dump = getattr(spec, "model_dump", None)
	if callable(dump):
		out = dump(mode="json", exclude_none=False)
		assert isinstance(out, dict)
		return out
	raise TypeError(
		f"keys_for_spec expects a dict or Pydantic model, got {type(spec).__name__}",
	)


def _spec_id(spec: dict[str, Any]) -> str:
	for candidate in ("id", "jtbd_id"):
		value = spec.get(candidate)
		if isinstance(value, str) and value:
			return value
	raise ValueError("spec is missing 'id' / 'jtbd_id'")


def keys_for_spec(spec: Any) -> set[str]:
	"""Return every catalog key derivable from *spec*.

	Optional fields that are absent or empty do not generate keys —
	callers wanting a stable schema should iterate the constant key
	taxonomy independently. The returned set is unordered.
	"""
	dump = _spec_dict(spec)
	jtbd_id = _spec_id(dump)
	out: set[str] = set()

	for field_name in _TOP_LEVEL_FIELDS:
		value = dump.get(field_name)
		if isinstance(value, str) and value:
			out.add(f"{jtbd_id}.{field_name}")

	# fields = data_capture (per the canonical schema)
	for entry in dump.get("data_capture") or []:
		if not isinstance(entry, dict):
			continue
		field_id = entry.get("id")
		if not isinstance(field_id, str) or not field_id:
			continue
		out.add(f"{jtbd_id}.fields.{field_id}.label")
		# Help is conditional on the spec carrying any hint text. The
		# canonical schema stores hint under either ``help`` or
		# ``description`` depending on field kind, so accept either.
		if entry.get("help") or entry.get("description"):
			out.add(f"{jtbd_id}.fields.{field_id}.help")

	for entry in dump.get("edge_cases") or []:
		if not isinstance(entry, dict):
			continue
		edge_id = entry.get("id") or entry.get("name")
		if not isinstance(edge_id, str) or not edge_id:
			continue
		out.add(f"{jtbd_id}.edge_cases.{edge_id}.message")

	for entry in dump.get("notifications") or []:
		if not isinstance(entry, dict):
			continue
		trigger = entry.get("trigger")
		if not isinstance(trigger, str) or not trigger:
			continue
		out.add(f"{jtbd_id}.notifications.{trigger}.subject")
		out.add(f"{jtbd_id}.notifications.{trigger}.body")

	criteria = dump.get("success_criteria") or []
	for index, _ in enumerate(criteria):
		out.add(f"{jtbd_id}.success_criteria[{index}]")

	return out


__all__ = ["keys_for_spec"]
