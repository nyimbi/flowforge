"""R-01..R-07 — Cross-domain registry format validation tests.

Verifies that all seven registry YAML files under
python/flowforge-jtbd/src/flowforge_jtbd/registries/ are well-formed,
contain the required fields, and satisfy domain-specific invariants.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def _repo_root() -> Path:
	for parent in Path(__file__).resolve().parents:
		if (parent / "pyproject.toml").is_file() and (parent / "docs").is_dir():
			return parent
	raise AssertionError("could not locate flowforge repo root")


_REGISTRIES = (
	_repo_root()
	/ "python"
	/ "flowforge-jtbd"
	/ "src"
	/ "flowforge_jtbd"
	/ "registries"
)

_JTBD_ID_RE = re.compile(r"^[a-z][a-z0-9_]+\.[a-z][a-z0-9]+_[a-z][a-z0-9_]+$")


def _load(filename: str) -> list[dict]:
	path = _REGISTRIES / filename
	assert path.is_file(), f"registry file missing: {path}"
	data = yaml.safe_load(path.read_text(encoding="utf-8"))
	assert isinstance(data, list), f"{filename}: expected a YAML list, got {type(data).__name__}"
	assert len(data) > 0, f"{filename}: list must not be empty"
	return data


# ---------------------------------------------------------------------------
# R-01 citations.yaml
# ---------------------------------------------------------------------------


def test_registry_citations_canonical_format() -> None:
	"""R-01: every entry has id, text, domain, jurisdiction."""
	entries = _load("citations.yaml")
	required = {"id", "text", "domain", "jurisdiction"}
	for i, entry in enumerate(entries):
		missing = required - entry.keys()
		assert not missing, (
			f"citations.yaml entry [{i}] missing fields: {missing}. Entry: {entry}"
		)
		for field in required:
			assert isinstance(entry[field], str) and entry[field].strip(), (
				f"citations.yaml entry [{i}] field '{field}' must be a non-empty string"
			)
	# spot-check minimum coverage
	ids = {e["id"] for e in entries}
	assert "gdpr_art32" in ids, "citations.yaml must contain gdpr_art32"
	assert "hipaa_45cfr164_312" in ids, "citations.yaml must contain hipaa_45cfr164_312"
	assert "sox_s404" in ids, "citations.yaml must contain sox_s404"
	assert "naic_model_act_820" in ids, "citations.yaml must contain naic_model_act_820"
	assert "ucc_4a_202" in ids, "citations.yaml must contain ucc_4a_202"


# ---------------------------------------------------------------------------
# R-02 channels.yaml
# ---------------------------------------------------------------------------


def test_registry_channels_no_collisions() -> None:
	"""R-02: no duplicate channel ids; required fields present."""
	entries = _load("channels.yaml")
	required = {"id", "label", "protocol"}
	seen_ids: set[str] = set()
	for i, entry in enumerate(entries):
		missing = required - entry.keys()
		assert not missing, (
			f"channels.yaml entry [{i}] missing fields: {missing}. Entry: {entry}"
		)
		cid = entry["id"]
		assert cid not in seen_ids, f"channels.yaml: duplicate id '{cid}'"
		seen_ids.add(cid)
	expected_ids = {"email", "sms", "in_app", "push", "slack", "webhook", "fax", "postal_mail"}
	missing_channels = expected_ids - seen_ids
	assert not missing_channels, f"channels.yaml missing required channels: {missing_channels}"


# ---------------------------------------------------------------------------
# R-03 roles.yaml
# ---------------------------------------------------------------------------


def test_registry_roles_required_fields() -> None:
	"""R-03: every role entry has id, label, description; minimum 10 roles."""
	entries = _load("roles.yaml")
	required = {"id", "label", "description"}
	for i, entry in enumerate(entries):
		missing = required - entry.keys()
		assert not missing, (
			f"roles.yaml entry [{i}] missing fields: {missing}. Entry: {entry}"
		)
		for field in required:
			assert isinstance(entry[field], str) and entry[field].strip(), (
				f"roles.yaml entry [{i}] field '{field}' must be a non-empty string"
			)
	assert len(entries) >= 10, (
		f"roles.yaml must contain at least 10 entries, got {len(entries)}"
	)
	expected_ids = {
		"approver", "reviewer", "submitter", "auditor", "admin",
		"supervisor", "compliance_officer", "legal_counsel",
		"finance_controller", "system_agent",
	}
	found_ids = {e["id"] for e in entries}
	missing_roles = expected_ids - found_ids
	assert not missing_roles, f"roles.yaml missing required role ids: {missing_roles}"


# ---------------------------------------------------------------------------
# R-04 doc_types.yaml
# ---------------------------------------------------------------------------


def test_registry_doc_types_required_fields() -> None:
	"""R-04: every doc type has id, label, domains list; minimum 10 types."""
	entries = _load("doc_types.yaml")
	for i, entry in enumerate(entries):
		assert "id" in entry, f"doc_types.yaml entry [{i}] missing 'id'"
		assert "label" in entry, f"doc_types.yaml entry [{i}] missing 'label'"
		assert "domains" in entry, f"doc_types.yaml entry [{i}] missing 'domains'"
		assert isinstance(entry["domains"], list) and len(entry["domains"]) > 0, (
			f"doc_types.yaml entry [{i}] 'domains' must be a non-empty list"
		)
		assert isinstance(entry["id"], str) and entry["id"].strip(), (
			f"doc_types.yaml entry [{i}] 'id' must be a non-empty string"
		)
		assert isinstance(entry["label"], str) and entry["label"].strip(), (
			f"doc_types.yaml entry [{i}] 'label' must be a non-empty string"
		)
	assert len(entries) >= 10, (
		f"doc_types.yaml must contain at least 10 entries, got {len(entries)}"
	)
	expected_ids = {
		"identity_document", "proof_of_income", "contract", "invoice",
		"policy_document", "regulatory_filing", "audit_trail",
		"medical_record", "title_deed", "tax_return",
	}
	found_ids = {e["id"] for e in entries}
	missing_types = expected_ids - found_ids
	assert not missing_types, f"doc_types.yaml missing required doc type ids: {missing_types}"


# ---------------------------------------------------------------------------
# R-05 jtbd_ids.yaml
# ---------------------------------------------------------------------------


def test_registry_jtbd_ids_namespaced() -> None:
	"""R-05: all JTBD ids follow <domain>.<verb>_<noun> pattern."""
	entries = _load("jtbd_ids.yaml")
	required = {"id", "domain", "description"}
	for i, entry in enumerate(entries):
		missing = required - entry.keys()
		assert not missing, (
			f"jtbd_ids.yaml entry [{i}] missing fields: {missing}. Entry: {entry}"
		)
		jtbd_id = entry["id"]
		assert _JTBD_ID_RE.match(jtbd_id), (
			f"jtbd_ids.yaml entry [{i}] id '{jtbd_id}' does not match "
			f"pattern <domain>.<verb>_<noun> (regex: {_JTBD_ID_RE.pattern})"
		)
		# domain prefix must match the domain field
		prefix = jtbd_id.split(".")[0]
		assert prefix == entry["domain"], (
			f"jtbd_ids.yaml entry [{i}] id prefix '{prefix}' does not match "
			f"domain field '{entry['domain']}'"
		)
	# insurance_claim must be present
	ids = {e["id"] for e in entries}
	assert "insurance.process_claim" in ids, (
		"jtbd_ids.yaml must contain the canonical insurance.process_claim entry"
	)
	# must cover at least 3 distinct domains
	domains = {e["domain"] for e in entries}
	assert len(domains) >= 3, (
		f"jtbd_ids.yaml must cover at least 3 distinct domains, found: {domains}"
	)


# ---------------------------------------------------------------------------
# R-06 edge_case_ids.yaml
# ---------------------------------------------------------------------------


def test_registry_edge_cases_required_fields() -> None:
	"""R-06: every edge case has id, category, description; minimum 8 entries."""
	entries = _load("edge_case_ids.yaml")
	required = {"id", "category", "description"}
	for i, entry in enumerate(entries):
		missing = required - entry.keys()
		assert not missing, (
			f"edge_case_ids.yaml entry [{i}] missing fields: {missing}. Entry: {entry}"
		)
		for field in required:
			assert isinstance(entry[field], str) and entry[field].strip(), (
				f"edge_case_ids.yaml entry [{i}] field '{field}' must be a non-empty string"
			)
	assert len(entries) >= 8, (
		f"edge_case_ids.yaml must contain at least 8 entries, got {len(entries)}"
	)
	expected_ids = {
		"concurrent_submit", "expired_document", "duplicate_entity",
		"partial_approval", "rollback_mid_saga", "tenant_boundary_crossing",
		"zero_amount_transaction", "stale_snapshot",
	}
	found_ids = {e["id"] for e in entries}
	missing_cases = expected_ids - found_ids
	assert not missing_cases, (
		f"edge_case_ids.yaml missing required edge case ids: {missing_cases}"
	)


# ---------------------------------------------------------------------------
# R-07 sla_keys.yaml
# ---------------------------------------------------------------------------


def test_registry_sla_keys_required_fields() -> None:
	"""R-07: every SLA key entry has key, unit, description; minimum 6 entries."""
	entries = _load("sla_keys.yaml")
	required = {"key", "unit", "description"}
	for i, entry in enumerate(entries):
		missing = required - entry.keys()
		assert not missing, (
			f"sla_keys.yaml entry [{i}] missing fields: {missing}. Entry: {entry}"
		)
		for field in required:
			assert isinstance(entry[field], str) and entry[field].strip(), (
				f"sla_keys.yaml entry [{i}] field '{field}' must be a non-empty string"
			)
	assert len(entries) >= 6, (
		f"sla_keys.yaml must contain at least 6 entries, got {len(entries)}"
	)
	expected_keys = {
		"response_time_p99_seconds",
		"approval_deadline_days",
		"escalation_trigger_hours",
		"breach_notification_hours",
		"resolution_deadline_days",
		"soak_duration_seconds",
	}
	found_keys = {e["key"] for e in entries}
	missing_keys = expected_keys - found_keys
	assert not missing_keys, (
		f"sla_keys.yaml missing required SLA keys: {missing_keys}"
	)
