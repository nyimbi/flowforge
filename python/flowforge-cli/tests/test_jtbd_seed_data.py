"""Unit tests for v0.3.0 W4a / item 14 — Faker-driven seed data.

Covers:

* Per-bundle generator emits ``backend/seeds/<package>/seed_<jtbd>.py``
  per JTBD plus the seeds package marker (``__init__.py``) and the
  ``python -m`` entrypoint (``__main__.py``).
* Faker seed is deterministic per ``(package, jtbd_id)``: same input
  always yields the same 32-bit integer derived from
  ``int(sha256("<package>:<jtbd_id>")[:8], 16)``.
* Field-kind → Faker dispatch covers every kind in
  :data:`transforms.SA_COLUMN_TYPE` with the documented expression
  shape; validation ranges (``min`` / ``max`` / ``enum``) are honoured
  when present.
* Every ten-rows-per-state target state in the emitted ``SEED_PATHS``
  table is reachable via the synthesised transitions (BFS path-finder
  doesn't emit phantom event sequences).
* Generated seed module compiles under :mod:`compileall`.
* Pipeline regen is byte-deterministic across two runs against the
  same bundle.
* The fixture-coverage registry agrees with the generator's
  ``CONSUMES`` declaration.
"""

from __future__ import annotations

import compileall
import hashlib
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry, seed_data
from flowforge_cli.jtbd.normalize import normalize


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _bundle() -> dict[str, Any]:
	"""Single-JTBD bundle exercising every field-kind dispatch branch."""

	return {
		"project": {
			"name": "seed-demo",
			"package": "seed_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {"roles": ["adjuster"], "permissions": []},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{"id": "claimant_name", "kind": "text", "label": "Claimant name", "required": True, "pii": True},
					{"id": "summary", "kind": "text", "label": "Loss summary", "required": False, "pii": False},
					{"id": "loss_description", "kind": "textarea", "label": "Loss description", "pii": False},
					{"id": "contact_email", "kind": "email", "label": "Email", "required": True, "pii": True},
					{"id": "contact_phone", "kind": "phone", "label": "Phone", "pii": True},
					{"id": "claimant_address", "kind": "address", "label": "Address", "pii": True},
					{"id": "loss_date", "kind": "date", "label": "Date of loss", "pii": False},
					{"id": "occurred_at", "kind": "datetime", "label": "Occurred at", "pii": False},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Loss amount",
						"pii": False,
						"validation": {"min": 100, "max": 50000},
					},
					{"id": "headcount", "kind": "number", "label": "Headcount", "pii": False, "validation": {"min": 1, "max": 50}},
					{"id": "consent_given", "kind": "boolean", "label": "Consent", "pii": False},
					{
						"id": "loss_type",
						"kind": "enum",
						"label": "Loss type",
						"pii": False,
						"validation": {"enum": ["fire", "theft", "flood"]},
					},
					{"id": "signature", "kind": "signature", "label": "Signature", "pii": False},
					{"id": "evidence", "kind": "file", "label": "Evidence", "pii": False},
					{"id": "broker_id", "kind": "party_ref", "label": "Broker", "pii": False},
					{"id": "policy_doc", "kind": "document_ref", "label": "Policy doc", "pii": False},
				],
			}
		],
	}


# ---------------------------------------------------------------------------
# faker_seed: deterministic 32-bit int
# ---------------------------------------------------------------------------


def test_faker_seed_is_sha256_of_package_jtbd_id() -> None:
	expected = int(
		hashlib.sha256(b"seed_demo:claim_intake").hexdigest()[:8],
		16,
	)
	assert seed_data.faker_seed("seed_demo", "claim_intake") == expected


def test_faker_seed_is_pure_function() -> None:
	a = seed_data.faker_seed("seed_demo", "claim_intake")
	b = seed_data.faker_seed("seed_demo", "claim_intake")
	assert a == b


def test_faker_seed_differs_per_jtbd() -> None:
	a = seed_data.faker_seed("seed_demo", "claim_intake")
	b = seed_data.faker_seed("seed_demo", "permit_intake")
	assert a != b


# ---------------------------------------------------------------------------
# pipeline outputs
# ---------------------------------------------------------------------------


def test_seed_data_emits_per_jtbd_module() -> None:
	files = generate(_bundle())
	(seed_module,) = [
		f for f in files if f.path == "backend/seeds/seed_demo/seed_claim_intake.py"
	]
	# Header reflects the bundle / JTBD identity
	assert "seed_demo:claim_intake" in seed_module.content
	# FAKER_SEED literal matches the helper
	expected_seed = seed_data.faker_seed("seed_demo", "claim_intake")
	assert f"FAKER_SEED: int = {expected_seed}" in seed_module.content
	# 10 rows per state pinned per docs/improvements.md item 14
	assert "ROWS_PER_STATE: int = 10" in seed_module.content
	# Service is invoked through the absolute import (no engine bypass)
	assert (
		"from seed_demo.services.claim_intake_service import" in seed_module.content
	)
	assert "ClaimIntakeService()" in seed_module.content


def test_seed_data_emits_package_init() -> None:
	files = generate(_bundle())
	(init,) = [f for f in files if f.path == "backend/seeds/seed_demo/__init__.py"]
	assert "JTBDS: tuple[str, ...]" in init.content
	assert '"claim_intake"' in init.content


def test_seed_data_emits_main_entrypoint() -> None:
	files = generate(_bundle())
	(main,) = [f for f in files if f.path == "backend/seeds/seed_demo/__main__.py"]
	assert "from . import JTBDS" in main.content
	assert 'asyncio.run(_run_all())' in main.content
	assert 'seeds.seed_demo.seed_' in main.content


# ---------------------------------------------------------------------------
# field-kind → Faker dispatch
# ---------------------------------------------------------------------------


def test_faker_dispatch_text_name_label() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	# claimant_name (label has "name") → faker.name()
	assert '"claimant_name": faker.name()' in seed_module.content
	# summary (no name in id/label) → faker.text(max_nb_chars=200)
	assert '"summary": faker.text(max_nb_chars=200)' in seed_module.content


def test_faker_dispatch_textarea_email_phone_address() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	assert '"loss_description": faker.text(max_nb_chars=2000)' in seed_module.content
	assert '"contact_email": faker.email()' in seed_module.content
	assert '"contact_phone": faker.phone_number()' in seed_module.content
	assert '"claimant_address": faker.address()' in seed_module.content


def test_faker_dispatch_date_datetime() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	assert (
		"\"loss_date\": faker.date_between(start_date='-2y', end_date='today')"
		in seed_module.content
	)
	# datetime needs the timezone import threaded into the module header
	assert "from datetime import timezone" in seed_module.content
	assert (
		"\"occurred_at\": faker.date_time_between(start_date='-2y', end_date='now',"
		" tzinfo=timezone.utc)"
	) in seed_module.content


def test_faker_dispatch_money_with_validation_range() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	# Validation min=100 max=50000 → faker.pyfloat(min_value=100.0, max_value=50000.0, ...)
	assert (
		'"loss_amount": round(faker.pyfloat(min_value=100.0, max_value=50000.0,'
		' right_digits=2), 2)'
	) in seed_module.content


def test_faker_dispatch_number_with_validation_range() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	assert (
		'"headcount": faker.pyint(min_value=1, max_value=50)'
	) in seed_module.content


def test_faker_dispatch_boolean_enum() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	assert '"consent_given": faker.boolean()' in seed_module.content
	# Enum sorted for determinism: ["fire", "flood", "theft"]
	assert (
		'"loss_type": faker.random_element(elements=(\'fire\', \'flood\', \'theft\',))'
	) in seed_module.content


def test_faker_dispatch_signature_file_refs() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	assert '"signature": f"{faker.uuid4()}-signed"' in seed_module.content
	assert (
		'"evidence": f"https://example.com/seeds/{faker.uuid4()}.pdf"'
	) in seed_module.content
	assert '"broker_id": faker.uuid4()' in seed_module.content
	assert '"policy_doc": faker.uuid4()' in seed_module.content


# ---------------------------------------------------------------------------
# state-path BFS
# ---------------------------------------------------------------------------


def test_seed_paths_skip_initial_state() -> None:
	"""``intake`` is the initial state — submit() advances out of it.

	The seed loop opens with ``service.submit()`` which fires the
	``submit`` event itself, so an entity never rests in ``intake``.
	The generator must skip the initial state in ``SEED_PATHS``.
	"""

	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	assert '("intake"' not in seed_module.content


def test_seed_paths_strip_leading_submit() -> None:
	"""service.submit() fires "submit"; the suffix paths must not duplicate it."""

	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	# review is reached on submit alone → suffix is the empty tuple
	assert '("review", ())' in seed_module.content


def test_seed_paths_chain_to_terminal_states() -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	# done is reached by submit() + approve → suffix is ("approve",)
	assert '("done", ("approve",))' in seed_module.content


# ---------------------------------------------------------------------------
# determinism + compilation
# ---------------------------------------------------------------------------


def test_seed_module_compiles(tmp_path: Path) -> None:
	files = generate(_bundle())
	(seed_module,) = [f for f in files if f.path.endswith("seed_claim_intake.py")]
	dst = tmp_path / "seed_claim_intake.py"
	dst.write_text(seed_module.content, encoding="utf-8")
	assert compileall.compile_file(str(dst), quiet=1)


def test_seed_init_and_main_compile(tmp_path: Path) -> None:
	files = generate(_bundle())
	(init,) = [f for f in files if f.path.endswith("/seeds/seed_demo/__init__.py")]
	(main,) = [f for f in files if f.path.endswith("/seeds/seed_demo/__main__.py")]
	for stem, file in (("__init__.py", init), ("__main__.py", main)):
		dst = tmp_path / stem
		dst.write_text(file.content, encoding="utf-8")
		assert compileall.compile_file(str(dst), quiet=1)


def test_seed_pipeline_is_byte_deterministic() -> None:
	a = generate(_bundle())
	b = generate(_bundle())
	assert [f.path for f in a] == [f.path for f in b]
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic: {fa.path}"


# ---------------------------------------------------------------------------
# fixture-registry coverage
# ---------------------------------------------------------------------------


def test_seed_data_consumes_matches_registry() -> None:
	declared = seed_data.CONSUMES
	registered = _fixture_registry.get("seed_data")
	assert tuple(sorted(declared)) == tuple(sorted(registered)), (declared, registered)


# ---------------------------------------------------------------------------
# multi-JTBD bundle: per-JTBD module + multi-line JTBDS tuple
# ---------------------------------------------------------------------------


def test_multi_jtbd_bundle_emits_one_module_per_jtbd() -> None:
	bundle = _bundle()
	bundle["jtbds"].append(
		{
			"id": "permit_intake",
			"title": "File a permit",
			"actor": {"role": "applicant", "external": True},
			"situation": "applicant files",
			"motivation": "obtain permit",
			"outcome": "permit issued",
			"success_criteria": ["issued within 30d"],
			"data_capture": [
				{"id": "applicant_name", "kind": "text", "label": "Name", "required": True, "pii": True},
			],
		}
	)
	files = generate(bundle)
	seed_modules = sorted(
		f.path for f in files if "/seeds/seed_demo/seed_" in f.path
	)
	assert seed_modules == [
		"backend/seeds/seed_demo/seed_claim_intake.py",
		"backend/seeds/seed_demo/seed_permit_intake.py",
	]
	(init,) = [f for f in files if f.path.endswith("/seeds/seed_demo/__init__.py")]
	# JTBDS tuple is sorted by jtbd id
	assert init.content.index('"claim_intake"') < init.content.index('"permit_intake"')


def test_normalize_round_trip_smoke() -> None:
	"""Sanity: normalize() produces a bundle the seed_data generator accepts."""

	norm = normalize(_bundle())
	gen_files = seed_data.generate(norm)
	# seeds/<package>/__init__.py + __main__.py + one seed_<jtbd>.py
	assert len(gen_files) == 3
	assert all(f.path.startswith("backend/seeds/seed_demo/") for f in gen_files)
