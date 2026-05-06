"""Tests for the incremental compiler + build lockfile (E-26).

The fixture is a seeded multi-JTBD bundle (claim_intake + claim_triage
+ a cross-cutting permissions.py file). The tests prove:

* First run: every file is NEW → rebuilt.
* Second run with no input change: every file is UNCHANGED → skipped.
* Edit one JTBD's spec_hash → only that JTBD's per-file outputs +
  the cross-cutting permissions.py rebuild; the unrelated JTBD's
  outputs stay UNCHANGED.
* Hand-edit a generated file → status flips to HAND_EDITED and the
  compiler refuses to overwrite unless force=True.
* Drop a JTBD entirely → its files surface as REMOVED and prune=True
  deletes them.
* Lockfile JSON round-trip is byte-stable.
"""

from __future__ import annotations

import json

from flowforge.compiler import (
	BuildLockfile,
	FileTarget,
	IncrementalCompiler,
	InMemoryFileStore,
	PlanEntryStatus,
	hash_inputs,
)


# ---------------------------------------------------------------------------
# Fixture: seeded multi-JTBD bundle abstracted to (path, inputs, render) tuples
# ---------------------------------------------------------------------------


def _per_jtbd_targets(
	jtbd_id: str,
	spec_hash: str,
	bundle_meta: dict[str, str],
) -> list[FileTarget]:
	"""Three per-JTBD generated files: model, service, definition.json.

	Each file's input set carries the JTBD spec_hash + the bundle
	metadata it depends on. A change to either invalidates the file.
	"""

	def _render_model() -> bytes:
		return f"# model for {jtbd_id} ({spec_hash})\n".encode("utf-8")

	def _render_service() -> bytes:
		return f"# service for {jtbd_id} ({spec_hash})\n".encode("utf-8")

	def _render_def() -> bytes:
		return json.dumps(
			{"jtbd_id": jtbd_id, "spec_hash": spec_hash},
			sort_keys=True,
			separators=(",", ":"),
		).encode("utf-8")

	common_inputs: dict[str, object] = {
		"jtbd_id": jtbd_id,
		"spec_hash": spec_hash,
		"bundle_meta": bundle_meta,
	}
	return [
		FileTarget(
			path=f"backend/{jtbd_id}/model.py",
			inputs=common_inputs,
			render=_render_model,
			last_jtbd_version="1.0.0",
		),
		FileTarget(
			path=f"backend/{jtbd_id}/service.py",
			inputs=common_inputs,
			render=_render_service,
			last_jtbd_version="1.0.0",
		),
		FileTarget(
			path=f"workflows/{jtbd_id}/definition.json",
			inputs=common_inputs,
			render=_render_def,
			last_jtbd_version="1.0.0",
		),
	]


def _cross_cutting_permissions(
	jtbds: list[tuple[str, str]], roles: list[str]
) -> FileTarget:
	"""Cross-cutting file: aggregates over every JTBD."""

	def _render() -> bytes:
		body = {
			"jtbds": [{"id": jid, "hash": h} for jid, h in jtbds],
			"roles": sorted(roles),
		}
		return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

	return FileTarget(
		path="backend/permissions.py",
		inputs={"jtbds": jtbds, "roles": sorted(roles)},
		render=_render,
		last_jtbd_version=None,
		# Cross-cutting files cannot be hand-protected — they must
		# rebuild whenever any JTBD changes.
		protected_when_hand_edited=False,
	)


def _build_targets(
	jtbds: list[tuple[str, str]], roles: list[str]
) -> list[FileTarget]:
	bundle_meta = {"package": "claims_intake_demo"}
	targets: list[FileTarget] = []
	for jtbd_id, spec_hash in jtbds:
		targets.extend(_per_jtbd_targets(jtbd_id, spec_hash, bundle_meta))
	targets.append(_cross_cutting_permissions(jtbds, roles))
	return targets


# ---------------------------------------------------------------------------
# Plan + apply behaviour
# ---------------------------------------------------------------------------


def test_first_run_marks_every_file_as_new_and_rebuilds() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	targets = _build_targets(
		[("claim_intake", "h1"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer"],
	)
	plan = compiler.plan(targets)
	assert all(e.status is PlanEntryStatus.NEW for e in plan.entries)
	assert len(plan.entries) == len(targets)

	result = compiler.apply(plan, targets)
	assert set(result.rebuilt) == {t.path for t in targets}
	assert result.skipped_unchanged == ()
	for t in targets:
		assert store.exists(t.path)
		entry = lockfile.get(t.path)
		assert entry is not None
		assert entry.expected_input_hash == hash_inputs(t.inputs)


def test_second_run_with_no_input_change_skips_everything() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	targets = _build_targets(
		[("claim_intake", "h1"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer"],
	)
	compiler.apply(compiler.plan(targets), targets)

	# Same inputs second time around.
	plan2 = compiler.plan(targets)
	assert all(e.status is PlanEntryStatus.UNCHANGED for e in plan2.entries)

	result = compiler.apply(plan2, targets)
	assert result.rebuilt == ()
	assert set(result.skipped_unchanged) == {t.path for t in targets}


def test_changing_one_jtbd_only_rebuilds_its_slice_plus_cross_cutting() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	v1 = _build_targets(
		[("claim_intake", "h1"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer"],
	)
	compiler.apply(compiler.plan(v1), v1)

	# Bump claim_intake's spec_hash → its three per-JTBD files plus
	# the cross-cutting permissions.py become stale. claim_triage's
	# files keep their previous input hash and stay UNCHANGED.
	v2 = _build_targets(
		[("claim_intake", "h1_v2"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer"],
	)
	plan = compiler.plan(v2)
	by_path = {e.path: e.status for e in plan.entries}

	rebuild_paths = {p for p, s in by_path.items() if s is PlanEntryStatus.REBUILD}
	unchanged_paths = {
		p for p, s in by_path.items() if s is PlanEntryStatus.UNCHANGED
	}
	assert rebuild_paths == {
		"backend/claim_intake/model.py",
		"backend/claim_intake/service.py",
		"workflows/claim_intake/definition.json",
		"backend/permissions.py",
	}
	assert unchanged_paths == {
		"backend/claim_triage/model.py",
		"backend/claim_triage/service.py",
		"workflows/claim_triage/definition.json",
	}

	result = compiler.apply(plan, v2)
	assert set(result.rebuilt) == rebuild_paths
	assert set(result.skipped_unchanged) == unchanged_paths


def test_changing_only_shared_roles_rebuilds_cross_cutting_only() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	v1 = _build_targets(
		[("claim_intake", "h1"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer"],
	)
	compiler.apply(compiler.plan(v1), v1)

	# Add a new shared role. Per-JTBD files do not depend on the role
	# list (they get bundle_meta which is unchanged); only the cross-
	# cutting permissions.py rebuilds.
	v2 = _build_targets(
		[("claim_intake", "h1"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer", "claims_supervisor"],
	)
	plan = compiler.plan(v2)
	rebuilds = {e.path for e in plan.entries if e.needs_rebuild}
	assert rebuilds == {"backend/permissions.py"}


def test_hand_edited_file_is_protected_unless_force() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	targets = _build_targets(
		[("claim_intake", "h1")],
		roles=["intake_clerk"],
	)
	compiler.apply(compiler.plan(targets), targets)

	# Author hand-edits one of the generated files.
	store.write("backend/claim_intake/service.py", b"# manually tuned\n")

	# Same inputs — but the on-disk content drifted.
	plan = compiler.plan(targets)
	by_path = {e.path: e.status for e in plan.entries}
	assert by_path["backend/claim_intake/service.py"] is PlanEntryStatus.HAND_EDITED

	result = compiler.apply(plan, targets)
	assert result.skipped_hand_edited == ("backend/claim_intake/service.py",)
	# The on-disk hand-edited content is preserved.
	assert store.read("backend/claim_intake/service.py") == b"# manually tuned\n"
	# The lockfile records the hand-edit flag.
	entry = lockfile.get("backend/claim_intake/service.py")
	assert entry is not None and entry.hand_edited is True

	# Force re-run: hand-edited file is overwritten.
	plan2 = compiler.plan(targets)
	assert {e.status for e in plan2.entries if e.path == "backend/claim_intake/service.py"} == {
		PlanEntryStatus.HAND_EDITED,
	}
	compiler.apply(plan2, targets, force=True)
	assert (
		store.read("backend/claim_intake/service.py")
		== b"# service for claim_intake (h1)\n"
	)
	entry2 = lockfile.get("backend/claim_intake/service.py")
	assert entry2 is not None and entry2.hand_edited is False


def test_cross_cutting_files_are_not_hand_edit_protected() -> None:
	"""§23.6 — losing a hand edit on a cross-cutting file would silently
	break tenants. The compiler still rebuilds them in the no-force
	path."""
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	targets = _build_targets(
		[("claim_intake", "h1")],
		roles=["intake_clerk"],
	)
	compiler.apply(compiler.plan(targets), targets)
	store.write("backend/permissions.py", b"hand-edited\n")

	# Now bump roles so cross-cutting input hash changes; cross-cutting
	# file rebuilds even though it was hand-edited.
	v2 = _build_targets(
		[("claim_intake", "h1")],
		roles=["intake_clerk", "manager"],
	)
	plan = compiler.plan(v2)
	cross = next(e for e in plan.entries if e.path == "backend/permissions.py")
	assert cross.status is PlanEntryStatus.REBUILD

	compiler.apply(plan, v2)
	assert b"hand-edited" not in store.read("backend/permissions.py")


def test_dropped_target_surfaces_as_removed_and_prune_deletes_it() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	v1 = _build_targets(
		[("claim_intake", "h1"), ("claim_triage", "h2")],
		roles=["intake_clerk", "triage_officer"],
	)
	compiler.apply(compiler.plan(v1), v1)

	# Author removes claim_triage entirely.
	v2 = _build_targets(
		[("claim_intake", "h1")],
		roles=["intake_clerk"],
	)
	plan = compiler.plan(v2)
	removed = {e.path for e in plan.entries if e.status is PlanEntryStatus.REMOVED}
	assert removed == {
		"backend/claim_triage/model.py",
		"backend/claim_triage/service.py",
		"workflows/claim_triage/definition.json",
	}

	# prune=False keeps the files; prune=True deletes + drops lockfile entries.
	r1 = compiler.apply(plan, v2, prune=False)
	assert r1.removed == ()
	assert store.exists("backend/claim_triage/service.py")

	r2 = compiler.apply(plan, v2, prune=True)
	assert set(r2.removed) == removed
	for path in removed:
		assert not store.exists(path)
		assert path not in lockfile


def test_missing_file_with_matching_hash_still_rebuilds() -> None:
	"""If the file disappeared from disk but the lockfile still claims
	a hash, treat it as a rebuild — the on-disk truth wins."""
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	targets = _build_targets(
		[("claim_intake", "h1")],
		roles=["intake_clerk"],
	)
	compiler.apply(compiler.plan(targets), targets)
	# Author deletes one of the generated files.
	store.remove("backend/claim_intake/model.py")

	plan = compiler.plan(targets)
	by_path = {e.path: e.status for e in plan.entries}
	assert by_path["backend/claim_intake/model.py"] is PlanEntryStatus.REBUILD


def test_duplicate_target_paths_raise() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)
	targets = [
		FileTarget(path="x.py", inputs={"v": 1}, render=lambda: b"a"),
		FileTarget(path="x.py", inputs={"v": 2}, render=lambda: b"b"),
	]
	try:
		compiler.plan(targets)
	except ValueError as exc:
		assert "duplicate target path" in str(exc)
	else:  # pragma: no cover — should never reach
		raise AssertionError("expected ValueError on duplicate path")


# ---------------------------------------------------------------------------
# BuildLockfile serialisation
# ---------------------------------------------------------------------------


def test_lockfile_round_trips_through_canonical_json_bytes() -> None:
	lock = BuildLockfile()
	lock.record(
		"a/b.py",
		expected_input_hash="abc",
		output_hash="123",
		last_jtbd_version="1.0.0",
	)
	lock.record(
		"a/a.py",
		expected_input_hash="def",
		output_hash="456",
		last_jtbd_version="1.0.0",
	)
	encoded = lock.to_bytes()
	decoded = BuildLockfile.from_bytes(encoded)
	assert decoded.entries == lock.entries
	# Bytes are byte-stable: re-encoding the round-tripped lockfile
	# produces the same payload.
	assert decoded.to_bytes() == encoded
	# Sorted keys at the top level.
	parsed = json.loads(encoded.decode("utf-8"))
	assert list(parsed["entries"].keys()) == sorted(parsed["entries"].keys())


def test_lockfile_save_and_load_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
	lock = BuildLockfile()
	lock.record(
		"src/x.py",
		expected_input_hash="h1",
		output_hash="o1",
	)
	path = tmp_path / "flowforge.lockfile"
	lock.save(path)
	loaded = BuildLockfile.load(path)
	assert loaded.entries == lock.entries

	# Missing file → empty lockfile.
	missing = tmp_path / "no-such.lockfile"
	assert len(BuildLockfile.load(missing)) == 0


def test_apply_persists_output_hash_for_hand_edit_detection() -> None:
	store = InMemoryFileStore()
	lockfile = BuildLockfile()
	compiler = IncrementalCompiler(lockfile=lockfile, store=store)

	targets = _build_targets(
		[("claim_intake", "h1")],
		roles=["intake_clerk"],
	)
	compiler.apply(compiler.plan(targets), targets)

	# Output hash on disk equals the lockfile-recorded hash.
	from flowforge.compiler import hash_bytes

	for t in targets:
		entry = lockfile.get(t.path)
		assert entry is not None
		assert entry.output_hash == hash_bytes(store.read(t.path))


def test_input_hash_independent_of_dict_key_order() -> None:
	a = hash_inputs({"a": 1, "b": 2, "c": [3, 1, 2]})
	b = hash_inputs({"c": [3, 1, 2], "b": 2, "a": 1})
	assert a == b
