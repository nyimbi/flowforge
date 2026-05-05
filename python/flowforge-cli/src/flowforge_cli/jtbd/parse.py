"""JTBD bundle parser.

Validates against ``jtbd-1.0.schema.json`` and applies the §B-1 fix:
``pii`` is required on every field whose ``kind`` could carry PII
(``text``, ``email``, ``phone``, ``address``, ``textarea``, ``file``,
``signature``, ``party_ref``). The schema already declares ``pii`` as
required globally; this module surfaces a friendly error that names
each offending field so the caller can fix them in one pass.
"""

from __future__ import annotations

import json
from importlib.resources import files as _ir_files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class JTBDParseError(ValueError):
	"""Raised when a bundle fails schema or domain validation."""


_PII_REQUIRED_KINDS = frozenset(
	{
		"text",
		"email",
		"phone",
		"address",
		"textarea",
		"file",
		"signature",
		"party_ref",
	}
)


_SCHEMA: dict[str, Any] | None = None


def _load_schema() -> dict[str, Any]:
	"""Resolve the JTBD JSON schema from the flowforge-core package."""

	global _SCHEMA
	if _SCHEMA is not None:
		return _SCHEMA
	try:
		res = _ir_files("flowforge.dsl.schema").joinpath("jtbd-1.0.schema.json")
		_SCHEMA = json.loads(res.read_text())
	except (ModuleNotFoundError, FileNotFoundError):
		# editable-install fallback
		import flowforge as _ff

		assert _ff.__file__ is not None
		ff_path = Path(_ff.__file__).resolve().parent
		_SCHEMA = json.loads((ff_path / "dsl" / "schema" / "jtbd-1.0.schema.json").read_text())
	assert isinstance(_SCHEMA, dict)
	return _SCHEMA


def parse_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
	"""Validate *bundle* against the JTBD schema and return it unchanged.

	Errors are collected and raised as a single :class:`JTBDParseError`
	with a multiline message — easier to read than the ``jsonschema``
	default which surfaces only the first failure.
	"""

	assert isinstance(bundle, dict), "bundle must be a dict"

	validator = Draft202012Validator(_load_schema())
	schema_errs = sorted(validator.iter_errors(bundle), key=lambda e: list(e.absolute_path))

	domain_errs: list[str] = []
	for jtbd in bundle.get("jtbds", []) or []:
		for field in jtbd.get("data_capture", []) or []:
			kind = field.get("kind")
			if kind in _PII_REQUIRED_KINDS and "pii" not in field:
				domain_errs.append(
					f"jtbds[{jtbd.get('id', '?')}].data_capture[{field.get('id', '?')}]: "
					f"pii flag is required for kind={kind!r}"
				)

	all_errs: list[str] = []
	for err in schema_errs:
		path = "/".join(str(p) for p in err.absolute_path) or "<root>"
		all_errs.append(f"schema at {path}: {err.message}")
	all_errs.extend(domain_errs)

	if all_errs:
		raise JTBDParseError("invalid JTBD bundle:\n  - " + "\n  - ".join(all_errs))

	return bundle
