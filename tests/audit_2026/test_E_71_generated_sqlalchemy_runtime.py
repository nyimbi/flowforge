"""E-71 — generated JTBD adapter can use durable SQLAlchemy runtime state."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from flowforge.ports.types import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from flowforge_sqlalchemy import (
	Base,
	WorkflowEvent,
	WorkflowInstance,
	WorkflowInstanceSnapshot,
)

pytestmark = pytest.mark.asyncio

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE = _REPO_ROOT / "examples" / "insurance_claim" / "generated"


def _import_generated_adapter() -> Any:
	"""Load the checked-in insurance-claim generated adapter fresh."""

	for name in (
		"insurance_claim_demo.adapters.claim_intake_adapter",
		"insurance_claim_demo.adapters",
		"insurance_claim_demo.claim_intake",
		"insurance_claim_demo",
	):
		sys.modules.pop(name, None)

	src = _EXAMPLE / "backend" / "src" / "insurance_claim_demo"
	for ns in (
		"insurance_claim_demo",
		"insurance_claim_demo.adapters",
		"insurance_claim_demo.claim_intake",
	):
		mod_path = src
		if ns.endswith(".adapters"):
			mod_path = src / "adapters"
		elif ns.endswith(".claim_intake"):
			mod_path = src / "claim_intake"
		spec = importlib.util.spec_from_file_location(
			ns,
			mod_path / "__init__.py",
			submodule_search_locations=[str(mod_path)],
		)
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules[ns] = module
		if (mod_path / "__init__.py").is_file():
			spec.loader.exec_module(module)

	adapter_path = src / "adapters" / "claim_intake_adapter.py"
	spec = importlib.util.spec_from_file_location(
		"insurance_claim_demo.adapters.claim_intake_adapter",
		adapter_path,
	)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	setattr(
		module,
		"_DEF_PATH",
		_EXAMPLE / "workflows" / module.WORKFLOW_KEY / "definition.json",
	)
	return module


async def test_generated_adapter_persists_runtime_state_with_sqlalchemy(
	tmp_path: Path,
) -> None:
	engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
	session_factory = async_sessionmaker(engine, expire_on_commit=False)

	adapter = _import_generated_adapter()
	adapter.configure_runtime_session_factory(session_factory)
	principal = Principal(
		user_id="claim-adjuster",
		roles=("claims-officer",),
		is_system=False,
	)

	try:
		submitted = await adapter.fire_event(
			"submit",
			payload={
				"claimant_name": "Amina",
				"loss_date": "2026-01-01",
				"claim_amount": 1200,
			},
			instance_id="claim-71",
			principal=principal,
			tenant_id="tenant-generated-sql",
		)
		assert submitted.new_state == "review"

		approved = await adapter.fire_event(
			"approve",
			payload={"instance_id": "claim-71"},
			instance_id="claim-71",
			principal=principal,
			tenant_id="tenant-generated-sql",
		)
		assert approved.new_state == "done"

		async with session_factory() as session:
			instance = await session.scalar(
				select(WorkflowInstance).where(
					WorkflowInstance.tenant_id == "tenant-generated-sql",
					WorkflowInstance.id == "claim-71",
				)
			)
			assert instance is not None
			assert instance.state == "done"
			assert instance.terminal is True

			snapshot = await session.scalar(
				select(WorkflowInstanceSnapshot).where(
					WorkflowInstanceSnapshot.tenant_id == "tenant-generated-sql",
					WorkflowInstanceSnapshot.instance_id == "claim-71",
				)
			)
			assert snapshot is not None
			assert snapshot.state == "done"
			assert snapshot.seq == 2

			events = (
				await session.scalars(
					select(WorkflowEvent)
					.where(
						WorkflowEvent.tenant_id == "tenant-generated-sql",
						WorkflowEvent.instance_id == "claim-71",
					)
					.order_by(WorkflowEvent.seq)
				)
			).all()
			assert [(row.seq, row.event, row.to_state) for row in events] == [
				(1, "submit", "review"),
				(2, "approve", "done"),
			]
	finally:
		await engine.dispose()
