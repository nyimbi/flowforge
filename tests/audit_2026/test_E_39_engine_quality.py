"""E-39 — engine quality + correctness pass.

Audit findings (audit-fix-plan §4.1, §4.2, §4.3, §4.4, §7 E-39):
- C-02 (P1): All `uuid.uuid4()` → `uuid7str()` in engine/fire.py.
- C-03 (P1): Guard with syntax error raises `GuardEvaluationError` (not silent False).
- C-05 (P2): Non-serialisable context emits explicit `{"__non_json__": "<repr>"}` marker (not bare repr).
- C-08 (P1): Target like `"context"` (single component) raises `InvalidTargetError`.
- C-10 (P1): `compiler/validator.py` lookup-permission walks AST not substring;
  expression containing the string literal `"lookup_failed"` no longer triggers
  the permission warning.
- C-13 (P3): `flowforge/__init__.py` declares `__all__` (already true; pinned by lint).
- SA-01 (P1): All `uuid.uuid4()` → `uuid7str()` in flowforge-sqlalchemy snapshot_store.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from flowforge import config
from flowforge.compiler import validate
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.engine.fire import (
	GuardEvaluationError,
	InvalidTargetError,
)
from flowforge.ports.types import Principal


# ---------------------------------------------------------------------------
# C-02 — uuid7 in fire.py
# ---------------------------------------------------------------------------


def test_C_02_uuid7_in_new_instance() -> None:
	"""new_instance() generates UUID7 ids — time-ordered when sorted."""

	from flowforge._uuid7 import uuid7str  # E-39 shim

	wd = WorkflowDef.model_validate(
		{
			"key": "k",
			"version": "1.0.0",
			"subject_kind": "k",
			"initial_state": "s",
			"states": [{"name": "s", "kind": "manual_review"}],
			"transitions": [],
		}
	)

	# Two consecutive new_instance calls with no explicit id should yield
	# UUID7 strings; UUID7 is time-monotonic so id1 < id2 lexicographically.
	id1 = new_instance(wd).id
	id2 = new_instance(wd).id

	# UUID7s have version digit 7 in position 14 (0-indexed); v4 has 4.
	assert id1[14] == "7", f"expected UUID7, got {id1!r}"
	assert id2[14] == "7"
	# Time-ordered.
	assert id1 < id2

	# Sanity: shim re-exports correctly.
	import re
	assert re.match(r"^[0-9a-f-]{36}$", uuid7str())


@pytest.mark.asyncio
async def test_C_02_uuid7_in_create_entity_effect() -> None:
	"""create_entity effect produces UUID7 ids for new rows."""

	config.reset_to_fakes()
	wd = WorkflowDef.model_validate(
		{
			"key": "k",
			"version": "1.0.0",
			"subject_kind": "k",
			"initial_state": "s0",
			"states": [
				{"name": "s0", "kind": "manual_review"},
				{"name": "s1", "kind": "manual_review"},
			],
			"transitions": [
				{
					"id": "t",
					"event": "go",
					"from_state": "s0",
					"to_state": "s1",
					"effects": [
						{"kind": "create_entity", "entity": "claim", "values": {"x": 1}}
					],
				}
			],
		}
	)
	inst = new_instance(wd)
	await fire(wd, inst, "go", principal=Principal(user_id="u", is_system=True))
	assert inst.created_entities, "expected one created entity"
	_, row = inst.created_entities[0]
	assert row["id"][14] == "7", f"expected UUID7 id on entity row, got {row['id']!r}"


# ---------------------------------------------------------------------------
# C-03 — guard syntax error surfaces as GuardEvaluationError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_C_03_guard_syntax_error_raises() -> None:
	"""A guard that fails to evaluate raises GuardEvaluationError; existing
	false-guard tests (no exception, just no-match) remain green.

	Trigger: ``{"var": <non-string>}`` — the evaluator's `var` operator
	requires a string path; a non-string raises `EvaluationError`. The
	engine wraps that as GuardEvaluationError so authoring bugs surface.
	"""

	config.reset_to_fakes()
	wd = WorkflowDef.model_validate(
		{
			"key": "k",
			"version": "1.0.0",
			"subject_kind": "k",
			"initial_state": "s0",
			"states": [
				{"name": "s0", "kind": "manual_review"},
				{"name": "s1", "kind": "manual_review"},
			],
			"transitions": [
				{
					"id": "t",
					"event": "go",
					"from_state": "s0",
					"to_state": "s1",
					"guards": [
						{
							"kind": "expr",
							"expr": {"var": 123},
						}
					],
				}
			],
		}
	)
	inst = new_instance(wd)

	with pytest.raises(GuardEvaluationError):
		await fire(wd, inst, "go", principal=Principal(user_id="u", is_system=True))


@pytest.mark.asyncio
async def test_C_03_falsy_guard_remains_no_match() -> None:
	"""A guard returning False (not raising) still produces a no-match
	`FireResult` — no behaviour change for the legitimate path."""

	config.reset_to_fakes()
	wd = WorkflowDef.model_validate(
		{
			"key": "k",
			"version": "1.0.0",
			"subject_kind": "k",
			"initial_state": "s0",
			"states": [
				{"name": "s0", "kind": "manual_review"},
				{"name": "s1", "kind": "manual_review"},
			],
			"transitions": [
				{
					"id": "t",
					"event": "go",
					"from_state": "s0",
					"to_state": "s1",
					"guards": [{"kind": "expr", "expr": False}],
				}
			],
		}
	)
	inst = new_instance(wd)
	r = await fire(wd, inst, "go", principal=Principal(user_id="u", is_system=True))
	assert r.matched_transition_id is None
	assert inst.state == "s0"


# ---------------------------------------------------------------------------
# C-05 — non-JSON-safe context gets an explicit marker
# ---------------------------------------------------------------------------


def test_C_05_json_safe_marks_non_serialisable() -> None:
	"""_json_safe replaces non-serialisable values with an explicit
	``{"__non_json__": "<repr>"}`` marker — replay deterministic."""

	from flowforge.engine.fire import _json_safe

	class Bad:
		def __repr__(self) -> str:
			return "<Bad object>"

	out = _json_safe({"x": Bad(), "y": 1})
	# JSON-roundtrippable result.
	json.dumps(out)
	# Explicit marker, not bare repr.
	assert out == {"x": {"__non_json__": "<Bad object>"}, "y": 1}


def test_C_05_json_safe_passthrough_for_safe() -> None:
	"""Safe values are returned untouched (no defensive copy)."""

	from flowforge.engine.fire import _json_safe

	src = {"a": 1, "b": [1, 2], "c": {"d": "e"}}
	out = _json_safe(src)
	assert out == src


# ---------------------------------------------------------------------------
# C-08 — single-component dotted target rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_C_08_dotted_prefix_only_rejected() -> None:
	"""A `set` effect with target `'context'` (no dotted suffix) raises
	InvalidTargetError; legitimate `'context.x'` and `'context.x.y'` work."""

	config.reset_to_fakes()

	def _wd(target: str) -> WorkflowDef:
		return WorkflowDef.model_validate(
			{
				"key": "k",
				"version": "1.0.0",
				"subject_kind": "k",
				"initial_state": "s0",
				"states": [
					{"name": "s0", "kind": "manual_review"},
					{"name": "s1", "kind": "manual_review"},
				],
				"transitions": [
					{
						"id": "t",
						"event": "go",
						"from_state": "s0",
						"to_state": "s1",
						"effects": [{"kind": "set", "target": target, "expr": 1}],
					}
				],
			}
		)

	# Reject: bare "context" prefix with no path.
	wd = _wd("context")
	inst = new_instance(wd)
	with pytest.raises(InvalidTargetError):
		await fire(wd, inst, "go", principal=Principal(user_id="u", is_system=True))

	# Reject: empty string.
	wd = _wd("")
	inst = new_instance(wd)
	with pytest.raises(InvalidTargetError):
		await fire(wd, inst, "go", principal=Principal(user_id="u", is_system=True))

	# Accept: dotted-write keeps working.
	wd = _wd("context.x")
	inst = new_instance(wd)
	await fire(wd, inst, "go", principal=Principal(user_id="u", is_system=True))
	assert inst.context["x"] == 1


# ---------------------------------------------------------------------------
# C-10 — lookup-permission validator walks AST not substring
# ---------------------------------------------------------------------------


def test_C_10_string_literal_lookup_does_not_trigger_warning() -> None:
	"""A string literal containing 'lookup' inside a guard expression no
	longer triggers the permission-gate warning."""

	wd_data = {
		"key": "k",
		"version": "1.0.0",
		"subject_kind": "k",
		"initial_state": "s0",
		"states": [
			{"name": "s0", "kind": "manual_review"},
			{"name": "s1", "kind": "manual_review"},
		],
		"transitions": [
			{
				"id": "t",
				"event": "go",
				"from_state": "s0",
				"to_state": "s1",
				"guards": [
					{
						"kind": "expr",
						"expr": {"==": [{"var": "context.reason"}, "lookup_failed"]},
					}
				],
				"effects": [],
				"gates": [],
			}
		],
	}
	report = validate(wd_data)
	# No "lookup" warning because no actual lookup operator was used.
	assert not any("lookup" in w for w in report.warnings), report.warnings


def test_C_10_real_lookup_op_triggers_warning() -> None:
	"""An expression that actually invokes a `lookup` operator still
	triggers the permission-gate warning when no gate is paired."""

	wd_data = {
		"key": "k",
		"version": "1.0.0",
		"subject_kind": "k",
		"initial_state": "s0",
		"states": [
			{"name": "s0", "kind": "manual_review"},
			{"name": "s1", "kind": "manual_review"},
		],
		"transitions": [
			{
				"id": "t",
				"event": "go",
				"from_state": "s0",
				"to_state": "s1",
				"guards": [
					{
						"kind": "expr",
						"expr": {"lookup": ["policy", {"var": "context.id"}]},
					}
				],
				"effects": [],
				"gates": [],
			}
		],
	}
	report = validate(wd_data)
	assert any("lookup" in w for w in report.warnings), report.warnings


# ---------------------------------------------------------------------------
# C-13 — __all__ declared
# ---------------------------------------------------------------------------


def test_C_13_all_declared() -> None:
	"""flowforge package declares an __all__."""

	import flowforge

	assert hasattr(flowforge, "__all__")
	assert isinstance(flowforge.__all__, list)
	assert "__version__" in flowforge.__all__
	assert "config" in flowforge.__all__


# ---------------------------------------------------------------------------
# SA-01 — uuid7 in flowforge-sqlalchemy snapshot_store
# ---------------------------------------------------------------------------


def test_SA_01_uuid7_in_snapshot_store_source() -> None:
	"""snapshot_store.py uses uuid7str (not uuid.uuid4) for primary keys."""

	import inspect

	from flowforge_sqlalchemy import snapshot_store as ss_mod

	src = inspect.getsource(ss_mod)
	assert "uuid.uuid4" not in src, "snapshot_store.py still uses uuid.uuid4 (SA-01)"
	assert "uuid7str" in src, "snapshot_store.py must use uuid7str (SA-01)"


def test_SA_01_uuid7_minted_on_put(tmp_path: Any) -> None:  # noqa: ARG001
	"""Inserting a fresh snapshot mints a UUID7 primary key."""

	# Use an in-memory engine.
	from flowforge.engine.fire import Instance
	from flowforge_sqlalchemy.snapshot_store import SqlAlchemySnapshotStore
	import asyncio
	from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

	from flowforge_sqlalchemy.models import Base

	captured: list[str] = []

	async def _drive() -> None:
		engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
		sf = async_sessionmaker(engine, expire_on_commit=False)

		store = SqlAlchemySnapshotStore(sf, tenant_id="t")
		inst = Instance(id="i-1", def_key="k", def_version="1.0.0", state="s")
		await store.put(inst)

		from sqlalchemy import select as _select
		from flowforge_sqlalchemy.models import WorkflowInstanceSnapshot

		async with sf() as session:
			row = await session.scalar(
				_select(WorkflowInstanceSnapshot).where(
					WorkflowInstanceSnapshot.instance_id == "i-1"
				)
			)
			assert row is not None
			captured.append(row.id)

		await engine.dispose()

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_drive())
	finally:
		loop.close()

	assert captured, "no row id captured"
	assert captured[0][14] == "7", f"expected UUID7 pk, got {captured[0]!r}"
