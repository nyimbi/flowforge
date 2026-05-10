"""W4a / item 3 — hypothesis seed uniqueness check (ADR-003).

Walks every emitted ``test_<jtbd>_properties.py`` under
``examples/*/generated/backend/tests/`` plus every retrofit property
test under ``tests/property/generators/``. For each one, extracts the
``_SEED = <int>  # 0x<hex>`` literal and asserts:

1. The literal matches ``int(sha256(<JTBD_ID|generator_name>)[:8], 16)``
   — the ADR-003 contract.
2. Within a single bundle (i.e. ``examples/<example>/generated/``) no
   two JTBDs share a seed; ditto for the generator-retrofit space.

A failure here means a JTBD id collided on the 32-bit seed space — at
which point the offending bundle needs a renamed JTBD or a documented
collision exception. The ADR explicitly retains this audit gate
because ``sha256(...)[:8]`` is collision-prone in theory.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]

# ``_SEED = <int>  # 0x<hex> = int(sha256(...)[:8], 16)``
_SEED_RE = re.compile(r"_SEED\s*=\s*(\d+)\s*#\s*0x([0-9a-f]{8})")
# ``JTBD_ID = "<id>"`` (emitted) or fallback to the test-file's directory name.
_JTBD_ID_RE = re.compile(r'JTBD_ID\s*=\s*"([^"]+)"')


def _expected_seed(name: str) -> int:
	"""ADR-003 seed: leading 8 hex chars of sha256(name) as a 32-bit int."""

	return int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)


def _parse_emitted_seed_file(path: Path) -> tuple[str, int, str]:
	"""Return ``(jtbd_id, seed_int, seed_hex)`` for a generated property test."""

	text = path.read_text(encoding="utf-8")
	m = _SEED_RE.search(text)
	assert m is not None, f"no _SEED literal in {path}"
	seed_int = int(m.group(1))
	seed_hex = m.group(2)
	jt = _JTBD_ID_RE.search(text)
	jtbd_id = jt.group(1) if jt else path.parent.name
	return jtbd_id, seed_int, seed_hex


def test_emitted_property_test_seeds_match_adr_003() -> None:
	"""Every generated ``test_<jtbd>_properties.py`` pins the ADR-003 seed."""

	files = sorted(
		_REPO_ROOT.glob("examples/*/generated/backend/tests/*/test_*_properties.py")
	)
	assert files, (
		"no generated property tests under examples/*/generated/ — regen via "
		"`flowforge jtbd-generate` for every example bundle"
	)
	for path in files:
		jtbd_id, seed_int, seed_hex = _parse_emitted_seed_file(path)
		expected = _expected_seed(jtbd_id)
		assert seed_int == expected, (
			f"ADR-003 drift in {path}: seed={seed_int} but "
			f"sha256({jtbd_id!r})[:8]={expected}"
		)
		# Hex comment must match the decimal literal (defence against an
		# editor mangling the comment without the runtime assert
		# catching it).
		assert int(seed_hex, 16) == seed_int, (
			f"hex/decimal mismatch in {path}: 0x{seed_hex} vs {seed_int}"
		)


def test_no_seed_collisions_within_bundle() -> None:
	"""Two JTBDs in the same example bundle MUST NOT share a 32-bit seed."""

	per_bundle: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
	for path in sorted(
		_REPO_ROOT.glob("examples/*/generated/backend/tests/*/test_*_properties.py")
	):
		# ``examples/<example>/generated/backend/tests/<jtbd>/test_*.py``
		example = path.parents[3].name
		jtbd_id, seed_int, _ = _parse_emitted_seed_file(path)
		per_bundle[example][seed_int].append(jtbd_id)

	collisions: list[str] = []
	for example, by_seed in per_bundle.items():
		for seed_int, jtbds in by_seed.items():
			if len(jtbds) > 1:
				collisions.append(
					f"{example}: seed {seed_int} shared by JTBDs {sorted(jtbds)}"
				)
	assert not collisions, "ADR-003 seed collision detected:\n  " + "\n  ".join(collisions)


def test_retrofit_generator_seeds_match_adr_003_pattern() -> None:
	"""Every retrofit test under tests/property/generators/ pins its own seed.

	Mirrors the per-JTBD contract: the seed is the leading 8 hex chars of
	``sha256(generator_name)`` decoded as a 32-bit int, surfaced via the
	``generator_seed("<name>")`` helper from ``_bundle_factory``.
	"""

	gen_tests = sorted(
		(_REPO_ROOT / "tests" / "property" / "generators").glob("test_*_properties.py")
	)
	assert len(gen_tests) >= 13, f"expected ≥13 retrofit tests, got {len(gen_tests)}"

	per_seed: dict[int, list[str]] = defaultdict(list)
	for path in gen_tests:
		text = path.read_text(encoding="utf-8")
		m = re.search(r'generator_seed\("([^"]+)"\)', text)
		assert m is not None, f"no generator_seed(...) call in {path}"
		gen_name = m.group(1)
		expected = _expected_seed(gen_name)
		# Filename convention: test_<generator>_properties.py — assert the
		# claimed name matches so a renamed file doesn't silently re-pin
		# under a different seed.
		stem = path.stem  # test_compensation_handlers_properties
		assert stem == f"test_{gen_name}_properties", (
			f"file/name mismatch: {stem} but generator_seed({gen_name!r})"
		)
		per_seed[expected].append(gen_name)

	collisions = {s: names for s, names in per_seed.items() if len(names) > 1}
	assert not collisions, f"retrofit seed collision: {collisions}"
