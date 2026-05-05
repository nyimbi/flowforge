"""Tests for ``flowforge_cli.jtbd.parse`` — schema + §B-1 pii rule."""

from __future__ import annotations

from typing import Any

import pytest

from flowforge_cli.jtbd.parse import JTBDParseError, parse_bundle


def _ok_bundle() -> dict[str, Any]:
	return {
		"project": {
			"name": "claims",
			"package": "claims",
			"domain": "claims",
		},
		"shared": {
			"roles": ["adjuster"],
			"permissions": ["claim.read"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["claim is queued within SLA"],
				"data_capture": [
					{"id": "claimant_name", "kind": "text", "label": "Name", "pii": True},
					{"id": "loss_amount", "kind": "money", "label": "Loss", "pii": False},
				],
			}
		],
	}


def test_ok_bundle_parses() -> None:
	parse_bundle(_ok_bundle())


def test_missing_pii_for_text_kind_raises() -> None:
	bundle = _ok_bundle()
	# Drop the pii flag; the schema-level required-on-field still flags
	# this, but our domain check surfaces a sharper message.
	bundle["jtbds"][0]["data_capture"][0].pop("pii")
	with pytest.raises(JTBDParseError) as exc:
		parse_bundle(bundle)
	# Either the schema "pii is a required property" or our domain rule
	# fires; both name the field id.
	msg = str(exc.value)
	assert "pii" in msg
	assert "claimant_name" in msg or "data_capture" in msg


def test_unknown_top_level_field_rejected() -> None:
	bundle = _ok_bundle()
	bundle["unexpected"] = "nope"
	with pytest.raises(JTBDParseError) as exc:
		parse_bundle(bundle)
	assert "Additional properties" in str(exc.value) or "unexpected" in str(exc.value)


def test_missing_jtbds_rejected() -> None:
	bundle = _ok_bundle()
	bundle.pop("jtbds")
	with pytest.raises(JTBDParseError):
		parse_bundle(bundle)


def test_invalid_id_pattern_rejected() -> None:
	bundle = _ok_bundle()
	bundle["jtbds"][0]["id"] = "Has-Caps"
	with pytest.raises(JTBDParseError):
		parse_bundle(bundle)
