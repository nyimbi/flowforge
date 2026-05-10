"""W4a / item 3 — property-coverage audit gate.

Asserts that every generator added in W0-W3 has at least one
hypothesis property test under ``tests/property/generators/``. The
list is the 13-generator canon documented in the W4a task brief:

  compensation_handlers, migration_safety, openapi, diagram,
  frontend_admin, restore_runbook, idempotency, analytics_taxonomy,
  frontend_cli, frontend_email, frontend_slack, lineage, design_tokens.

The Makefile target ``audit-2026-property-coverage`` runs this test in
isolation so a missing retrofit fails fast in CI; the regular
``audit-2026-unit`` and ``audit-2026-property`` lanes still exercise
the property tests themselves.
"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]


# The 13 W0-W3 generators that MUST own a retrofit property test under
# ``tests/property/generators/test_<generator>_properties.py``. Sorted
# for byte-stable failure messages.
REQUIRED_GENERATORS: tuple[str, ...] = (
	"analytics_taxonomy",
	"compensation_handlers",
	"design_tokens",
	"diagram",
	"frontend_admin",
	"frontend_cli",
	"frontend_email",
	"frontend_slack",
	"idempotency",
	"lineage",
	"migration_safety",
	"openapi",
	"restore_runbook",
)


def test_every_required_generator_has_a_property_test() -> None:
	"""Asserts the file ``tests/property/generators/test_<gen>_properties.py``
	exists and imports the generator under test.

	Failure message lists the missing generators so the fix is mechanical:
	add the file from the bundle-factory template at
	``tests/property/generators/_bundle_factory.py``.
	"""

	gen_dir = _REPO_ROOT / "tests" / "property" / "generators"
	assert gen_dir.is_dir(), f"missing retrofit directory: {gen_dir}"

	missing: list[str] = []
	weak: list[str] = []
	for gen in REQUIRED_GENERATORS:
		path = gen_dir / f"test_{gen}_properties.py"
		if not path.is_file():
			missing.append(gen)
			continue
		text = path.read_text(encoding="utf-8")
		# Sanity-check: the test must import the generator it claims to
		# cover, otherwise the retrofit is a placeholder.
		needle = f"from flowforge_cli.jtbd.generators import {gen}"
		if needle not in text:
			weak.append(f"{gen} (missing import: {needle!r})")
		if "@given(" not in text:
			weak.append(f"{gen} (no @given decorator — not a property test)")

	problems: list[str] = []
	if missing:
		problems.append("missing retrofit files: " + ", ".join(sorted(missing)))
	if weak:
		problems.append("weak retrofit files: " + ", ".join(sorted(weak)))
	assert not problems, "property-coverage gate failed:\n  " + "\n  ".join(problems)
