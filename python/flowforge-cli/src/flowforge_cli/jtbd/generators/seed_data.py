"""Per-bundle generator: Faker-driven seed data per JTBD.

Item 14 of :doc:`docs/improvements`, W4a of
:doc:`docs/v0.3.0-engineering-plan`. Emits one
``backend/seeds/<package>/seed_<jtbd>.py`` module per JTBD that, when
invoked, creates ten realistic instances per *reachable forward state*
through the generated service layer (so RLS, audit chain, and
permissions engage exactly as a real client would). Faker is seeded
deterministically from ``int(sha256("<package>:<jtbd_id>")[:8], 16)``
so calling ``seed()`` twice against the same database produces
byte-identical seed rows.

This is a per-bundle generator (not per-JTBD) under the v0.3.0
engineering plan principle 2: per-bundle generators must be
aggregations. The output set is one file per JTBD plus an
``__init__.py`` package marker so the seeds tree is importable.

Field-kind → Faker dispatch lives in :func:`_faker_expr` and follows
``transforms.SA_COLUMN_TYPE`` / ``transforms.TS_FIELD_COMPONENT`` shape
— same kind set, deterministic mapping. Validation ranges (``min`` /
``max`` / ``enum``) are honoured when present so generated values stay
within the declared bounds.

The fixture-registry primer at :mod:`._fixture_registry` records the
attribute paths this generator reads; the bidirectional coverage test
cross-checks generator and registry.
"""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any

from .._render import render
from ..normalize import NormalizedBundle, NormalizedField, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W4a coverage test asserts they
# agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].class_name",
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].kind",
	"jtbds[].fields[].label",
	"jtbds[].fields[].validation",
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].module_name",
	"jtbds[].states",
	"jtbds[].title",
	"jtbds[].transitions",
	"project.package",
)


# Number of seed rows emitted per reachable forward state. Pinned at
# 10 per :doc:`docs/improvements` item 14. Override at runtime via the
# generated ``seed(rows_per_state=...)`` keyword argument.
ROWS_PER_STATE = 10


def faker_seed(package: str, jtbd_id: str) -> int:
	"""Derive the deterministic 32-bit Faker seed for *(package, jtbd_id)*.

	``int(sha256("<package>:<jtbd_id>")[:8], 16)`` — exactly what the
	W4a brief specifies. Same input always yields the same seed across
	machines, Python builds, and Faker versions, so two regens of the
	same bundle produce byte-identical seed rows at runtime.
	"""

	assert isinstance(package, str) and package, "package required"
	assert isinstance(jtbd_id, str) and jtbd_id, "jtbd_id required"
	digest = hashlib.sha256(f"{package}:{jtbd_id}".encode("utf-8")).hexdigest()
	return int(digest[:8], 16)


def _faker_expr(field: NormalizedField) -> str:
	"""Return the Python source-code Faker expression for *field*.

	Pure transform: same input → same source string. Used at template
	time so the emitted ``_build_payload`` body is byte-stable across
	regens and the runtime values stay deterministic under the seeded
	``Faker`` instance.

	The dispatch matches the kind set in :data:`transforms.SA_COLUMN_TYPE`;
	new kinds added there must add a branch here or fall through to the
	generic ``faker.word()`` placeholder.
	"""

	kind = field.kind
	label_lc = (field.label or "").lower()
	id_lc = (field.id or "").lower()
	is_name_field = ("name" in label_lc) or ("name" in id_lc)
	validation = field.validation or {}

	if kind == "text":
		if is_name_field:
			return "faker.name()"
		return "faker.text(max_nb_chars=200)"
	if kind == "textarea":
		return "faker.text(max_nb_chars=2000)"
	if kind == "email":
		return "faker.email()"
	if kind == "phone":
		return "faker.phone_number()"
	if kind == "address":
		return "faker.address()"
	if kind == "date":
		return "faker.date_between(start_date='-2y', end_date='today')"
	if kind == "datetime":
		return (
			"faker.date_time_between(start_date='-2y', end_date='now',"
			" tzinfo=timezone.utc)"
		)
	if kind == "money":
		mn = validation.get("min")
		mx = validation.get("max")
		if mn is not None and mx is not None:
			return (
				f"round(faker.pyfloat(min_value={float(mn)},"
				f" max_value={float(mx)}, right_digits=2), 2)"
			)
		return "round(faker.pyfloat(left_digits=5, right_digits=2, positive=True), 2)"
	if kind == "number":
		mn = validation.get("min")
		mx = validation.get("max")
		if mn is not None and mx is not None:
			return f"faker.pyint(min_value={int(mn)}, max_value={int(mx)})"
		return "faker.pyint()"
	if kind == "boolean":
		return "faker.boolean()"
	if kind == "enum":
		opts = validation.get("enum") or validation.get("choices") or ()
		if opts:
			# Sort for deterministic emission across dict-iteration
			# orders; the runtime random_element pick is still seeded
			# by the Faker instance.
			parts = ", ".join(repr(str(o)) for o in sorted(str(o) for o in opts))
			return f"faker.random_element(elements=({parts},))"
		return "faker.word()"
	if kind == "signature":
		return 'f"{faker.uuid4()}-signed"'
	if kind == "file":
		return 'f"https://example.com/seeds/{faker.uuid4()}.pdf"'
	if kind in ("party_ref", "document_ref"):
		return "faker.uuid4()"
	# Fallback for unknown kinds — keeps the seed deterministic but
	# obviously synthetic; new kinds should add an explicit branch.
	return "faker.word()"


def _shortest_event_path(
	jtbd: NormalizedJTBD, src: str, dst: str
) -> list[str] | None:
	"""BFS over transitions to find the shortest event sequence from *src* to *dst*.

	Returns ``None`` when no path exists (the target state is
	unreachable from *src* via the synthesised transitions). The seed
	module skips unreachable states rather than emitting a sequence
	that would fail at runtime.

	Edges are ordered by ``(priority, event, to_state)`` for
	deterministic tie-breaking when multiple transitions share an
	origin; the lowest-priority edge wins so ``branch``-shaped
	transitions (priority ≥ 5) are picked only when the canonical
	low-priority path can't reach the target.
	"""

	if src == dst:
		return []

	# Build adjacency list, sorted for determinism.
	adjacency: dict[str, list[tuple[int, str, str]]] = {}
	for tr in jtbd.transitions:
		from_state = tr.get("from_state") or ""
		to_state = tr.get("to_state") or ""
		event = tr.get("event") or ""
		priority = int(tr.get("priority") or 0)
		adjacency.setdefault(from_state, []).append((priority, event, to_state))
	for edges in adjacency.values():
		edges.sort()

	visited: set[str] = {src}
	queue: deque[tuple[str, list[str]]] = deque([(src, [])])
	while queue:
		state, path = queue.popleft()
		for _edge in adjacency.get(state, ()):
			_, event, target = _edge
			if target in visited:
				continue
			new_path = path + [event]
			if target == dst:
				return new_path
			visited.add(target)
			queue.append((target, new_path))
	return None


def _seed_event_paths(jtbd: NormalizedJTBD) -> list[tuple[str, tuple[str, ...]]]:
	"""Return ``[(state, events_after_submit), ...]`` for seedable states.

	The seed harness always opens with ``service.submit(payload)`` —
	which fires the synthesised ``submit`` event and advances out of
	the initial state. This helper:

	1. iterates the JTBD's states in declaration order,
	2. computes the shortest event path from the initial state,
	3. strips the leading ``submit`` (the service does it),
	4. drops the initial state (unreachable post-submit),
	5. drops states with no path (unreachable; e.g. a guard-protected
	   ``compensated`` state when no seed payload satisfies
	   ``context.<eid>``).

	Output order follows the JTBD's state declaration so the generated
	module is byte-stable.
	"""

	paths: list[tuple[str, tuple[str, ...]]] = []
	for state in jtbd.states:
		name = state.get("name") or ""
		if not name:
			continue
		if name == jtbd.initial_state:
			# submit() advances out of the initial state; not seedable
			# as a terminal "the entity rests in this state" target.
			continue
		full_path = _shortest_event_path(jtbd, jtbd.initial_state, name)
		if full_path is None:
			# Unreachable from the initial state via deterministic
			# event firing — skip rather than emit a sequence that
			# would fail at runtime.
			continue
		# The generated service.submit() fires "submit" itself, so the
		# template-side loop only walks the post-submit suffix.
		if full_path and full_path[0] == "submit":
			tail = tuple(full_path[1:])
		else:
			tail = tuple(full_path)
		paths.append((name, tail))
	return paths


def _field_view(jtbd: NormalizedJTBD) -> list[dict[str, Any]]:
	"""Return ``[{id, kind, faker_call}, ...]`` for the template loop."""

	rows: list[dict[str, Any]] = []
	for f in jtbd.fields:
		rows.append(
			{
				"id": f.id,
				"kind": f.kind,
				"faker_call": _faker_expr(f),
			}
		)
	return rows


def _needs_timezone_import(fields: list[dict[str, Any]]) -> bool:
	"""Return True when any field's faker_call references ``timezone.utc``."""

	return any("timezone.utc" in row["faker_call"] for row in fields)


def _seed_for_jtbd(
	bundle: NormalizedBundle, jtbd: NormalizedJTBD
) -> GeneratedFile:
	"""Render one ``backend/seeds/<package>/seed_<jtbd>.py`` per JTBD."""

	fields = _field_view(jtbd)
	state_paths = _seed_event_paths(jtbd)
	content = render(
		"seed_data.py.j2",
		project=bundle.project,
		jtbd=jtbd,
		fields=fields,
		state_paths=state_paths,
		faker_seed=faker_seed(bundle.project.package, jtbd.id),
		rows_per_state=ROWS_PER_STATE,
		needs_timezone=_needs_timezone_import(fields),
	)
	return GeneratedFile(
		path=f"backend/seeds/{bundle.project.package}/seed_{jtbd.module_name}.py",
		content=content,
	)


def _seed_package_init(bundle: NormalizedBundle) -> GeneratedFile:
	"""Emit ``backend/seeds/<package>/__init__.py`` so seeds is importable."""

	jtbd_lines = "\n".join(
		f'\t"{j.module_name}",' for j in sorted(bundle.jtbds, key=lambda j: j.id)
	)
	content = (
		'"""Seed-data package for ' + bundle.project.name + '.\n\n'
		"Generated by flowforge JTBD generator (v0.3.0 W4a / item 14).\n"
		"Each ``seed_<jtbd>.py`` exposes a deterministic ``seed()`` coroutine\n"
		"that loads ten rows per reachable forward state through the\n"
		"generated service layer.  Run ``make seed`` to populate the\n"
		"canonical example database.\n"
		'"""\n\n'
		"from __future__ import annotations\n\n\n"
		"# JTBD module names registered under this seeds package — the\n"
		"# ``__main__`` entrypoint walks this list when invoked as\n"
		"# ``python -m seeds.<package>``.\n"
		"JTBDS: tuple[str, ...] = (\n"
		f"{jtbd_lines}\n"
		")\n"
	)
	return GeneratedFile(
		path=f"backend/seeds/{bundle.project.package}/__init__.py",
		content=content,
	)


def _seed_package_main(bundle: NormalizedBundle) -> GeneratedFile:
	"""Emit ``backend/seeds/<package>/__main__.py`` for ``python -m`` invocation.

	Walks every per-JTBD seed module declared in :data:`JTBDS` and runs
	its async ``seed()`` coroutine in declaration order. The Make
	target ``make seed`` calls this entrypoint — it's the canonical way
	to seed every JTBD in the bundle through the service layer.
	"""

	package = bundle.project.package
	content = (
		f'"""Seed every JTBD in the {package} bundle.\n\n'
		"Generated by flowforge JTBD generator (v0.3.0 W4a / item 14).\n\n"
		"Invoke via::\n\n"
		f"\tpython -m seeds.{package}\n\n"
		"or via the canonical Make target::\n\n"
		"\tmake seed\n"
		'"""\n\n'
		"from __future__ import annotations\n\n"
		"import asyncio\n"
		"import importlib\n"
		"from typing import Any\n\n"
		f"from . import JTBDS\n\n\n"
		"async def _run_all() -> list[dict[str, Any]]:\n"
		"\tcreated: list[dict[str, Any]] = []\n"
		"\tfor jtbd_module in JTBDS:\n"
		f"\t\tmodule = importlib.import_module(f\"seeds.{package}.seed_{{jtbd_module}}\")\n"
		"\t\tcreated.extend(await module.seed())\n"
		"\treturn created\n\n\n"
		'if __name__ == "__main__":\n'
		"\trows = asyncio.run(_run_all())\n"
		'\tprint(f"seed: loaded {len(rows)} rows across {len(JTBDS)} JTBD(s)")\n'
	)
	return GeneratedFile(
		path=f"backend/seeds/{bundle.project.package}/__main__.py",
		content=content,
	)


def generate(bundle: NormalizedBundle) -> list[GeneratedFile]:
	"""Emit one seed module per JTBD plus the seeds package marker.

	Per-bundle generator (Principle 2 of the engineering plan): the
	output set is computed at the bundle level so two regens against
	the same bundle return byte-identical lists in stable order.
	"""

	files: list[GeneratedFile] = [
		_seed_package_init(bundle),
		_seed_package_main(bundle),
	]
	for jtbd in sorted(bundle.jtbds, key=lambda j: j.id):
		files.append(_seed_for_jtbd(bundle, jtbd))
	return files
