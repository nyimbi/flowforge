"""Unit tests for the audit ordinal backfill migration helper."""

from __future__ import annotations

from typing import Any

import pytest

from flowforge_audit_pg.migrations import audit_ordinal_backfill as migration


class FakeResult:
	def __init__(
		self,
		*,
		rows: list[tuple[Any, ...]] | None = None,
		scalar_value: Any = None,
		row: tuple[Any, ...] | None = None,
	) -> None:
		self._rows = rows or []
		self._scalar = scalar_value
		self._row = row

	def fetchall(self) -> list[tuple[Any, ...]]:
		return self._rows

	def fetchone(self) -> tuple[Any, ...] | None:
		return self._row

	def scalar(self) -> Any:
		return self._scalar


class FakeConn:
	def __init__(self, results: list[FakeResult] | None = None) -> None:
		self.results = results or []
		self.calls: list[tuple[str, Any]] = []

	async def execute(self, statement: Any, params: Any = None) -> FakeResult:
		self.calls.append((str(statement), params))
		if self.results:
			return self.results.pop(0)
		return FakeResult()


class FakeContext:
	def __init__(self, conn: FakeConn) -> None:
		self.conn = conn

	async def __aenter__(self) -> FakeConn:
		return self.conn

	async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
		return None


class FakeEngine:
	def __init__(
		self,
		*,
		connect_conn: FakeConn | None = None,
		begin_conns: list[FakeConn] | None = None,
	) -> None:
		self.connect_conn = connect_conn or FakeConn()
		self.begin_conns = begin_conns or [FakeConn()]
		self.disposed = False

	def connect(self) -> FakeContext:
		return FakeContext(self.connect_conn)

	def begin(self) -> FakeContext:
		if len(self.begin_conns) > 1:
			return FakeContext(self.begin_conns.pop(0))
		return FakeContext(self.begin_conns[0])

	async def dispose(self) -> None:
		self.disposed = True


async def test_add_column_executes_idempotent_alter() -> None:
	conn = FakeConn()
	await migration._add_column(FakeEngine(begin_conns=[conn]))
	assert "ADD COLUMN IF NOT EXISTS ordinal" in conn.calls[0][0]


async def test_backfill_lists_tenants_and_locks_each_tenant() -> None:
	connect = FakeConn([FakeResult(rows=[("tenant-a",), ("tenant-b",)])])
	begin_a = FakeConn()
	begin_b = FakeConn()

	await migration._backfill(
		FakeEngine(connect_conn=connect, begin_conns=[begin_a, begin_b]),
		batch_size=100,
	)

	assert "SELECT DISTINCT tenant_id" in connect.calls[0][0]
	assert begin_a.calls[0][1] == {"k": "tenant-a"}
	assert begin_a.calls[1][1] == {"tenant_id": "tenant-a"}
	assert begin_b.calls[0][1] == {"k": "tenant-b"}
	assert begin_b.calls[1][1] == {"tenant_id": "tenant-b"}


async def test_add_constraint_skips_existing_constraint_but_adds_indexes() -> None:
	conn = FakeConn([FakeResult(scalar_value=True)])
	await migration._add_constraint(FakeEngine(begin_conns=[conn]))

	sql = "\n".join(call[0] for call in conn.calls)
	assert "uq_ff_audit_tenant_ordinal" in sql
	assert "CREATE INDEX IF NOT EXISTS ix_ff_audit_tenant_ordinal" in sql
	assert "ADD CONSTRAINT uq_ff_audit_tenant_ordinal" not in sql


async def test_add_constraint_creates_missing_constraint_and_indexes() -> None:
	conn = FakeConn([FakeResult(scalar_value=False)])
	await migration._add_constraint(FakeEngine(begin_conns=[conn]))

	sql = "\n".join(call[0] for call in conn.calls)
	assert "ADD CONSTRAINT uq_ff_audit_tenant_ordinal" in sql
	assert "ix_ff_audit_tenant_occurred_event" in sql


async def test_verify_reports_empty_and_populated_states() -> None:
	empty = await migration._verify(FakeEngine(connect_conn=FakeConn([FakeResult(row=None)])))
	assert empty == {"total_rows": 0, "null_ordinals": 0, "constraint_present": False}

	populated = await migration._verify(
		FakeEngine(connect_conn=FakeConn([FakeResult(row=(3, 0, True, True, True))]))
	)
	assert populated == {
		"total_rows": 3,
		"null_ordinals": 0,
		"constraint_present": True,
		"tenant_ordinal_index_present": True,
		"tenant_occurred_index_present": True,
	}


async def test_run_dispatches_steps_and_disposes_engine(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	engines = [
		FakeEngine(),
		FakeEngine(connect_conn=FakeConn([FakeResult(rows=[])])),
		FakeEngine(begin_conns=[FakeConn([FakeResult(scalar_value=True)])]),
	]
	monkeypatch.setattr(migration, "create_async_engine", lambda dsn: engines.pop(0))

	assert await migration._run("postgresql+asyncpg://db", "add-column", 10) == 0
	assert await migration._run("postgresql+asyncpg://db", "backfill", 10) == 0
	assert await migration._run("postgresql+asyncpg://db", "add-constraint", 10) == 0


@pytest.mark.parametrize(
	"report",
	[
		{"null_ordinals": 1, "constraint_present": True, "tenant_ordinal_index_present": True, "tenant_occurred_index_present": True},
		{"null_ordinals": 0, "constraint_present": False, "tenant_ordinal_index_present": True, "tenant_occurred_index_present": True},
		{"null_ordinals": 0, "constraint_present": True, "tenant_ordinal_index_present": False, "tenant_occurred_index_present": True},
		{"null_ordinals": 0, "constraint_present": True, "tenant_ordinal_index_present": True, "tenant_occurred_index_present": False},
	],
)
async def test_run_verify_failure_reports_exit_code_two(
	monkeypatch: pytest.MonkeyPatch,
	report: dict[str, Any],
) -> None:
	engine = FakeEngine()

	async def fake_verify(engine_arg: Any) -> dict[str, Any]:
		assert engine_arg is engine
		return report

	monkeypatch.setattr(migration, "create_async_engine", lambda dsn: engine)
	monkeypatch.setattr(migration, "_verify", fake_verify)

	assert await migration._run("postgresql+asyncpg://db", "verify", 10) == 2
	assert engine.disposed is True


async def test_run_verify_success_unknown_step_and_main(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	engine = FakeEngine()

	async def fake_verify(engine_arg: Any) -> dict[str, Any]:
		return {
			"null_ordinals": 0,
			"constraint_present": True,
			"tenant_ordinal_index_present": True,
			"tenant_occurred_index_present": True,
		}

	monkeypatch.setattr(migration, "create_async_engine", lambda dsn: engine)
	monkeypatch.setattr(migration, "_verify", fake_verify)
	assert await migration._run("postgresql+asyncpg://db", "verify", 10) == 0
	assert await migration._run("postgresql+asyncpg://db", "unknown", 10) == 1


def test_main_parses_args_and_runs_migration(monkeypatch: pytest.MonkeyPatch) -> None:
	async def fake_run(dsn: str, step: str, batch_size: int) -> int:
		assert dsn == "postgresql+asyncpg://db"
		assert step == "verify"
		assert batch_size == 5
		return 0

	monkeypatch.setattr(migration, "_run", fake_run)
	assert migration.main(
		[
			"--dsn",
			"postgresql+asyncpg://db",
			"--step",
			"verify",
			"--batch-size",
			"5",
			"--log-level",
			"debug",
		]
	) == 0
