"""E-37 / AU-01 backfill: add ``ordinal`` column + ``UNIQUE(tenant_id, ordinal)``.

Fresh deploys built from ``create_tables()`` already have this column.
This script handles the in-place migration for environments deployed
before E-37 landed.

The migration is **online**, **idempotent**, and **per-tenant lock-scoped**:

1. ``ALTER TABLE ff_audit_events ADD COLUMN ordinal BIGINT`` (nullable).
2. Per tenant, under ``pg_advisory_xact_lock(hashtext(tenant_id))``,
   backfill ordinals via ``ROW_NUMBER() OVER (PARTITION BY tenant_id
   ORDER BY occurred_at, event_id)``.
3. ``ALTER TABLE ff_audit_events ADD CONSTRAINT
   uq_ff_audit_tenant_ordinal UNIQUE (tenant_id, ordinal)``.

Because the unique constraint ignores NULL ordinals on PG/SQLite, step 1
alone is application-safe — readers fall back to ``occurred_at`` ordering
when ``ordinal IS NULL`` (sink.py:346-348). Steps 2 + 3 can roll out at
operator pace.

Usage::

    python -m flowforge_audit_pg.migrations.audit_ordinal_backfill \\
        --dsn postgres://... --step add-column

    python -m flowforge_audit_pg.migrations.audit_ordinal_backfill \\
        --dsn postgres://... --step backfill --batch-size 10000

    python -m flowforge_audit_pg.migrations.audit_ordinal_backfill \\
        --dsn postgres://... --step add-constraint

    python -m flowforge_audit_pg.migrations.audit_ordinal_backfill \\
        --dsn postgres://... --step verify
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

log = logging.getLogger(__name__)


_ADD_COLUMN_SQL = (
	"ALTER TABLE ff_audit_events "
	"ADD COLUMN IF NOT EXISTS ordinal BIGINT"
)

_LIST_TENANTS_SQL = (
	"SELECT DISTINCT tenant_id FROM ff_audit_events "
	"WHERE ordinal IS NULL ORDER BY tenant_id"
)

_BACKFILL_TENANT_SQL = """
WITH numbered AS (
	SELECT
		event_id,
		ROW_NUMBER() OVER (
			PARTITION BY tenant_id
			ORDER BY occurred_at, event_id
		) AS rn
	FROM ff_audit_events
	WHERE tenant_id = :tenant_id
)
UPDATE ff_audit_events e
SET ordinal = n.rn
FROM numbered n
WHERE e.event_id = n.event_id AND e.ordinal IS NULL
"""

_ADD_CONSTRAINT_SQL = (
	"ALTER TABLE ff_audit_events "
	"ADD CONSTRAINT uq_ff_audit_tenant_ordinal "
	"UNIQUE (tenant_id, ordinal)"
)

_VERIFY_SQL = """
SELECT
	(SELECT COUNT(*) FROM ff_audit_events) AS total_rows,
	(SELECT COUNT(*) FROM ff_audit_events WHERE ordinal IS NULL) AS null_ordinals,
	EXISTS(
		SELECT 1 FROM information_schema.table_constraints
		WHERE constraint_name = 'uq_ff_audit_tenant_ordinal'
	) AS constraint_present
"""


async def _add_column(engine: Any) -> None:
	log.info("step=add-column starting")
	async with engine.begin() as conn:
		await conn.execute(sa.text(_ADD_COLUMN_SQL))
	log.info("step=add-column done")


async def _backfill(engine: Any, batch_size: int) -> None:
	log.info("step=backfill starting batch_size=%d", batch_size)
	async with engine.connect() as conn:
		result = await conn.execute(sa.text(_LIST_TENANTS_SQL))
		tenants = [row[0] for row in result.fetchall()]
	log.info("step=backfill tenants=%d", len(tenants))
	for tenant_id in tenants:
		async with engine.begin() as conn:
			# Per-tenant advisory lock prevents concurrent inserts from
			# stealing ordinals while we backfill.
			await conn.execute(
				sa.text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
				{"k": str(tenant_id)},
			)
			await conn.execute(
				sa.text(_BACKFILL_TENANT_SQL),
				{"tenant_id": tenant_id},
			)
		log.info("step=backfill tenant=%s done", tenant_id)
	log.info("step=backfill complete")


async def _add_constraint(engine: Any) -> None:
	log.info("step=add-constraint starting")
	async with engine.begin() as conn:
		# Skip if already present — operator may re-run.
		exists = await conn.execute(
			sa.text(
				"SELECT EXISTS(SELECT 1 FROM information_schema."
				"table_constraints WHERE constraint_name = "
				"'uq_ff_audit_tenant_ordinal')"
			)
		)
		if exists.scalar():
			log.info("step=add-constraint already present, skipping")
			return
		await conn.execute(sa.text(_ADD_CONSTRAINT_SQL))
	log.info("step=add-constraint done")


async def _verify(engine: Any) -> dict[str, Any]:
	async with engine.connect() as conn:
		row = (await conn.execute(sa.text(_VERIFY_SQL))).fetchone()
	if row is None:
		return {"total_rows": 0, "null_ordinals": 0, "constraint_present": False}
	return {
		"total_rows": int(row[0]),
		"null_ordinals": int(row[1]),
		"constraint_present": bool(row[2]),
	}


async def _run(dsn: str, step: str, batch_size: int) -> int:
	engine = create_async_engine(dsn)
	try:
		if step == "add-column":
			await _add_column(engine)
		elif step == "backfill":
			await _backfill(engine, batch_size)
		elif step == "add-constraint":
			await _add_constraint(engine)
		elif step == "verify":
			report = await _verify(engine)
			log.info("verify: %s", report)
			if report["null_ordinals"] != 0:
				log.error(
					"verify FAIL: %d null ordinals remain",
					report["null_ordinals"],
				)
				return 2
			if not report["constraint_present"]:
				log.error("verify FAIL: uq_ff_audit_tenant_ordinal not present")
				return 2
			log.info("verify OK: 0 null ordinals, constraint present")
		else:
			log.error("unknown step: %s", step)
			return 1
		return 0
	finally:
		await engine.dispose()


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="audit_ordinal_backfill")
	parser.add_argument("--dsn", required=True, help="async PG DSN")
	parser.add_argument(
		"--step",
		required=True,
		choices=["add-column", "backfill", "add-constraint", "verify"],
	)
	parser.add_argument("--batch-size", type=int, default=10_000)
	parser.add_argument("--log-level", default="INFO")
	args = parser.parse_args(argv)

	logging.basicConfig(
		level=args.log_level.upper(),
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	)
	return asyncio.run(_run(args.dsn, args.step, args.batch_size))


if __name__ == "__main__":
	sys.exit(main())
