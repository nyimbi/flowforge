"""E-32 / C-01, C-04 — engine fire two-phase atomicity + per-instance lock.

Acceptance criteria (audit-fix-plan §4.1):

* `test_C_01_outbox_failure_rolls_back_fire`: outbox raise during fire →
  state pre == state post; audit row absent.
* `test_C_04_concurrent_fire_race`: 100 concurrent `fire()` for one
  instance → exactly 1 transition; others raise `ConcurrentFireRejected`
  or await.

Both regression tests must fail BEFORE the E-32 patch and pass AFTER.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio

from flowforge import config  # noqa: E402
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.engine.fire import ConcurrentFireRejected, OutboxDispatchError
from flowforge.ports.types import OutboxEnvelope, Principal
from flowforge.testing.port_fakes import InMemoryAuditSink, InMemoryOutbox


def _toy_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "triage", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "triage",
					"priority": 0,
					"effects": [
						{"kind": "notify", "template": "claim.submitted"},
						{
							"kind": "set",
							"target": "context.triage.priority",
							"expr": "normal",
						},
					],
				},
			],
		}
	)


# ---------------------------------------------------------------------------
# C-01 — outbox failure rolls back fire
# ---------------------------------------------------------------------------


class _FailingOutbox(InMemoryOutbox):
	"""Outbox stub whose `dispatch` always raises."""

	async def dispatch(self, envelope: OutboxEnvelope, backend: str = "default") -> None:
		raise RuntimeError("simulated outbox failure")


async def test_C_01_outbox_failure_rolls_back_fire() -> None:
	"""Outbox raise during fire → state + audit + context restored to pre-fire."""

	config.reset_to_fakes()
	config.outbox = _FailingOutbox()
	# Use a real audit sink so we can assert no row was written.
	config.audit = InMemoryAuditSink()

	wd = _toy_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": "p-1"}})

	pre_state = inst.state
	pre_history = list(inst.history)
	pre_context = copy.deepcopy(inst.context)
	pre_audit_count = len(config.audit.events)

	with pytest.raises(OutboxDispatchError) as exc_info:
		await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	# C-01: original cause is preserved through chaining.
	assert isinstance(exc_info.value.__cause__, RuntimeError)
	assert "simulated outbox failure" in str(exc_info.value.__cause__)

	# C-01: instance state is unchanged.
	assert inst.state == pre_state
	assert inst.history == pre_history
	assert inst.context == pre_context
	# C-01: no audit row written for this transition.
	assert len(config.audit.events) == pre_audit_count


async def test_C_01_audit_failure_also_rolls_back_fire() -> None:
	"""Audit raise during fire → state restored; outboxes already dispatched
	are tolerated (logged-but-orphan path, documented)."""

	config.reset_to_fakes()

	class _FailingAudit:
		events: list[Any] = []

		async def record(self, event: Any) -> str:
			raise RuntimeError("simulated audit failure")

		async def verify_chain(self, since: str | None = None) -> Any:  # pragma: no cover
			raise NotImplementedError

		async def redact(self, paths: list[str], reason: str) -> int:  # pragma: no cover
			raise NotImplementedError

	config.audit = _FailingAudit()

	wd = _toy_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": "p-1"}})

	pre_state = inst.state
	pre_context = copy.deepcopy(inst.context)

	with pytest.raises(Exception):
		await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))

	assert inst.state == pre_state
	assert inst.context == pre_context


# ---------------------------------------------------------------------------
# C-04 — concurrent fire is serialised per instance
# ---------------------------------------------------------------------------


async def test_C_04_concurrent_fire_race() -> None:
	"""100 concurrent fires on one instance → exactly 1 transition occurs.

	The 99 losers must raise `ConcurrentFireRejected` (or be queued behind
	the lock — implementation choice). With a `submit` event that only
	matches in `intake → triage`, only the first fire causes a transition;
	subsequent fires (after the winner releases) see state=`triage` and
	return a no-match `FireResult`. So the assertion is: exactly one of
	the 100 calls returned `matched_transition_id == 'submit'`.
	"""

	config.reset_to_fakes()

	wd = _toy_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": "p-1"}})

	async def attempt() -> str | None | type[ConcurrentFireRejected]:
		try:
			r = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
			return r.matched_transition_id
		except ConcurrentFireRejected:
			return ConcurrentFireRejected

	results = await asyncio.gather(*(attempt() for _ in range(100)))
	matched = [r for r in results if r == "submit"]
	rejected = [r for r in results if r is ConcurrentFireRejected]
	no_match = [r for r in results if r is None]

	# Exactly one fire transitioned the instance.
	assert len(matched) == 1, f"expected 1 winner, got {len(matched)} (rejected={len(rejected)}, no_match={len(no_match)})"
	# Final state is the winner's destination.
	assert inst.state == "triage"
	# The other 99 either raised ConcurrentFireRejected (early reject) or
	# observed the post-transition state and returned a no-match result.
	assert len(rejected) + len(no_match) == 99


async def test_C_04_lock_released_after_fire() -> None:
	"""After fire returns, the instance lock is released so a follow-up
	fire on the same instance is not blocked."""

	config.reset_to_fakes()

	wd = _toy_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": "p-1"}})

	r1 = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert r1.matched_transition_id == "submit"

	# Sequential fire on the same instance should not raise.
	r2 = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	# inst is now in "triage", so "submit" no longer matches.
	assert r2.matched_transition_id is None
	assert inst.state == "triage"


async def test_C_04_lock_released_after_outbox_failure() -> None:
	"""After OutboxDispatchError, the per-instance lock is released so a
	retry attempt is not deadlocked."""

	config.reset_to_fakes()
	config.outbox = _FailingOutbox()

	wd = _toy_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": "p-1"}})

	with pytest.raises(OutboxDispatchError):
		await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))

	# Replace outbox with a working one + retry — lock must be free.
	config.outbox = InMemoryOutbox()
	r = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert r.matched_transition_id == "submit"
	assert inst.state == "triage"
