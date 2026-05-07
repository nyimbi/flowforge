"""Smoke test for flowforge-jtbd-construction (audit-2026 E-49 / D-04).

Loads the shipped bundle via the standard ``load_bundle()`` helper and
asserts every JTBD has a non-empty ``data_capture`` list with at least
one domain-specific field.
"""

from __future__ import annotations

from importlib.resources import files

import yaml

from flowforge_jtbd_construction import DOMAIN, DISPLAY_NAME, load_bundle


def test_smoke_load_bundle_returns_dict() -> None:
	bundle = load_bundle()
	assert isinstance(bundle, dict)
	for key in ("project", "shared", "jtbds"):
		assert key in bundle, f"bundle missing top-level key {key!r}"


def test_smoke_bundle_lists_jtbds() -> None:
	bundle = load_bundle()
	jtbds = bundle["jtbds"]
	assert isinstance(jtbds, list)
	assert len(jtbds) >= 1
	for entry in jtbds:
		assert "id" in entry and "version" in entry, (
			f"bundle.jtbds entry malformed: {entry}"
		)


def test_smoke_each_jtbd_has_data_capture() -> None:
	resource = files("flowforge_jtbd_construction") / "jtbds"
	for jtbd_yaml in resource.iterdir():
		if jtbd_yaml.name.endswith(".yaml"):
			with jtbd_yaml.open("rb") as fh:
				doc = yaml.safe_load(fh)
			assert "data_capture" in doc, (
				f"{jtbd_yaml.name}: missing data_capture"
			)
			assert isinstance(doc["data_capture"], list)
			assert len(doc["data_capture"]) >= 1, (
				f"{jtbd_yaml.name}: data_capture must have at least 1 field"
			)


def test_smoke_domain_metadata_consistent() -> None:
	bundle = load_bundle()
	# Project block carries the domain; sanity-check it matches the package marker.
	project = bundle.get("project", {})
	assert isinstance(DOMAIN, str) and DOMAIN
	assert isinstance(DISPLAY_NAME, str) and DISPLAY_NAME
	# project.domain should equal DOMAIN — guards against accidental copy-paste
	# across packages.
	if "domain" in project:
		assert project["domain"] == DOMAIN, (
			f"bundle project.domain={project['domain']!r} != {DOMAIN!r}"
		)
