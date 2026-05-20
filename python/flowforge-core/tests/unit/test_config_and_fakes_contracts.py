from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from flowforge import config
from flowforge.config import (
	ProductionConfigError,
	RuntimeConfig,
	production_config_errors,
	use_runtime_config,
	validate_production_config,
)
from flowforge.engine.saga import CompensationWorker, SagaLedger, SagaStep
from flowforge.ports.types import AuditEvent, NotificationSpec, OutboxEnvelope, Principal, Scope
from flowforge.testing.port_fakes import (
	InMemoryAccessGrant,
	InMemoryAuditSink,
	InMemoryDocuments,
	InMemoryMoney,
	InMemoryNotifications,
	InMemoryOutbox,
	InMemoryRbac,
	InMemorySettings,
	InMemorySigning,
	InMemoryTaskTracker,
	InMemoryTenancy,
	NoopRls,
)


@pytest.fixture(autouse=True)
def reset_config():
	config.reset_to_fakes()
	yield
	config.reset_to_fakes()


def test_runtime_config_context_overrides_module_globals() -> None:
	scoped = RuntimeConfig(snapshot_interval=7, lookup_rate_limit_per_minute=11)

	assert config.current().snapshot_interval == 100
	with use_runtime_config(scoped) as active:
		assert active is scoped
		assert config.current() is scoped
		assert config.current().snapshot_interval == 7
		assert config.current().lookup_rate_limit_per_minute == 11
	assert config.current().snapshot_interval == 100


def test_production_config_errors_fail_closed_for_missing_fake_and_unknown_ports() -> None:
	runtime = RuntimeConfig(
		tenancy=InMemoryTenancy(),
		rbac=object(),
		audit=None,
		outbox=object(),
		rls=NoopRls(),
	)

	errors = production_config_errors(
		runtime,
		required_ports=("tenancy", "audit", "rls", "not_a_port"),
	)

	assert "tenancy uses testing fake InMemoryTenancy" in errors
	assert "audit is not configured" in errors
	assert "rls uses testing fake NoopRls" in errors
	assert "unknown required port 'not_a_port'" in errors


def test_production_config_detects_legacy_testing_fake_class_names() -> None:
	class NoopTracing:
		pass

	runtime = RuntimeConfig(tracing=NoopTracing())

	assert production_config_errors(runtime, required_ports=("tracing",)) == [
		"tracing uses testing fake NoopTracing"
	]
	assert production_config_errors(
		runtime,
		required_ports=("tracing",),
		allow_testing_fakes=True,
	) == []


def test_validate_production_config_can_allow_testing_fakes_for_local_harnesses() -> None:
	runtime = RuntimeConfig(
		tenancy=InMemoryTenancy(),
		rbac=InMemoryRbac(),
		audit=InMemoryAuditSink(),
		outbox=InMemoryOutbox(),
		rls=NoopRls(),
	)

	validate_production_config(runtime, allow_testing_fakes=True)

	with pytest.raises(ProductionConfigError) as exc_info:
		validate_production_config(runtime)
	assert "testing fake" in str(exc_info.value)
	assert exc_info.value.errors


@pytest.mark.asyncio
async def test_in_memory_tenancy_binds_and_restores_elevated_scope() -> None:
	tenancy = InMemoryTenancy("tenant-a")

	assert await tenancy.current_tenant() == "tenant-a"
	await tenancy.bind_session(object(), "tenant-b")
	assert await tenancy.current_tenant() == "tenant-b"

	assert tenancy._elevated is False
	async with tenancy.elevated_scope():
		assert tenancy._elevated is True
	assert tenancy._elevated is False


@pytest.mark.asyncio
async def test_in_memory_rbac_registers_permissions_and_lists_principals() -> None:
	rbac = InMemoryRbac({"alice": {"claim.read"}, "bob": {"claim.read", "claim.write"}})
	scope = Scope(tenant_id="tenant-a")

	assert await rbac.has_permission(Principal(user_id="system", is_system=True), "missing", scope) is True
	assert await rbac.has_permission(Principal(user_id="alice"), "claim.read", scope) is True
	assert await rbac.has_permission(Principal(user_id="alice"), "claim.write", scope) is False
	assert [p.user_id for p in await rbac.list_principals_with("claim.read", scope)] == ["alice", "bob"]

	await rbac.register_permission("claim.read", "Read claims")
	assert await rbac.assert_seed(["claim.read", "claim.write"]) == ["claim.write"]


@pytest.mark.asyncio
async def test_in_memory_audit_records_verifies_and_redacts_payload_paths() -> None:
	sink = InMemoryAuditSink()
	event_id = await sink.record(
		AuditEvent(
			kind="claim.created",
			subject_kind="claim",
			subject_id="claim-1",
			tenant_id="tenant-a",
			actor_user_id="u1",
			payload={"email": "person@example.com", "status": "new"},
		)
	)

	assert event_id == "evt-1"
	assert (await sink.verify_chain()).ok is True
	assert await sink.redact(["email", "missing"], "privacy") == 1
	assert sink.events[0].payload["email"] == "[redacted:privacy]"


@pytest.mark.asyncio
async def test_in_memory_outbox_dispatches_registered_backend_handlers() -> None:
	outbox = InMemoryOutbox()
	handled: list[str] = []

	async def handler(envelope):
		handled.append(envelope.body["subject_id"])

	outbox.register("notify", handler, backend="email")
	await outbox.dispatch(
		OutboxEnvelope(kind="notify", tenant_id="tenant-a", body={"subject_id": "claim-1"}),
		backend="email",
	)

	assert handled == ["claim-1"]
	assert [env.body["subject_id"] for env in outbox.dispatched] == ["claim-1"]
	assert outbox.list_kinds("email") == ["notify"]
	assert outbox.list_kinds("sms") == []


@pytest.mark.asyncio
async def test_documents_money_settings_notifications_signing_tasks_and_grants_fakes() -> None:
	docs = InMemoryDocuments()
	await docs.attach("claim-1", "doc-1")
	assert await docs.list_for_subject("claim-1") == [{"id": "doc-1", "kind": "unknown"}]
	assert await docs.list_for_subject("claim-1", kinds=["policy"]) == []
	assert await docs.get_classification("doc-1") is None
	assert await docs.freshness_days("doc-1") == 0

	money = InMemoryMoney({("USD", "CAD"): Decimal("1.35")})
	assert await money.convert(Decimal("10"), "USD", "CAD", datetime.now(timezone.utc)) == (
		Decimal("13.50"),
		Decimal("1.35"),
	)
	assert await money.convert(Decimal("10"), "USD", "USD", datetime.now(timezone.utc)) == (
		Decimal("10"),
		Decimal("1"),
	)
	assert await money.format(Decimal("10.00"), "USD") == "10.00 USD"

	settings = InMemorySettings()

	@dataclass
	class SettingSpec:
		key: str
		default: str

	await settings.register(SettingSpec("locale", "fr-CA"))
	await settings.register({"key": "region", "default": "ca"})
	await settings.register(MappingProxyType({"key": "currency", "default": "CAD"}))
	await settings.set("theme", "dark", signed_by="admin")
	assert await settings.get("locale") == "fr-CA"
	assert await settings.get("region") == "ca"
	assert await settings.get("currency") == "CAD"
	assert await settings.get("theme") == "dark"

	signing = InMemorySigning("kid-1")
	signature = await signing.sign_payload(b"payload")
	assert signing.current_key_id() == "kid-1"
	assert await signing.verify(b"payload", signature, "kid-1") is True
	assert await signing.verify(b"tampered", signature, "kid-1") is False

	notifications = InMemoryNotifications()
	await notifications.register_template(
		NotificationSpec(
			template_id="claim.submitted",
			channels=("email",),
			subject_template="Claim {claim_id}",
			body_template="Status {status}",
		)
	)
	rendered = await notifications.render(
		"claim.submitted",
		"en",
		{"claim_id": "C-1", "status": "submitted"},
	)
	await notifications.send("email", "ops@example.com", rendered)
	assert rendered == ("Claim C-1", "Status submitted")
	assert await notifications.render("missing", "en", {}) == ("missing", "")
	assert notifications.sent == [
		{
			"channel": "email",
			"to": "ops@example.com",
			"subject": "Claim C-1",
			"body": "Status submitted",
		}
	]

	tasks = InMemoryTaskTracker()
	assert await tasks.create_task("review", "claim-1", "Check documents") == "t-1"
	assert tasks.tasks[0]["note"] == "Check documents"

	grants = InMemoryAccessGrant()
	until = datetime(2026, 1, 1, tzinfo=timezone.utc)
	await grants.grant("claim:claim-1#viewer@user:alice", until=until)
	assert grants.grants["claim:claim-1#viewer@user:alice"] == until
	await grants.revoke("claim:claim-1#viewer@user:alice")
	assert grants.grants == {}

	rls = NoopRls()
	await rls.bind(None, {"tenant_id": "tenant-a"})
	entered_elevated_scope = False
	async with rls.elevated(None):
		entered_elevated_scope = True
	assert entered_elevated_scope is True


def test_saga_ledger_append_list_and_mark_are_copy_safe() -> None:
	ledger = SagaLedger()
	step = SagaStep(kind="release_lock", args={"lock_id": "L1"})
	ledger.append("instance-1", step)

	rows = ledger.list("instance-1")
	rows.append(SagaStep(kind="extra"))
	ledger.mark("instance-1", 0, "compensated")
	ledger.mark("instance-1", 99, "ignored")

	assert len(ledger.list("instance-1")) == 1
	assert ledger.list("instance-1")[0] == SagaStep(
		kind="release_lock",
		args={"lock_id": "L1"},
		status="compensated",
	)
	assert ledger.list("missing") == []


@pytest.mark.asyncio
async def test_compensation_worker_replays_success_failure_and_skips() -> None:
	@dataclass
	class Row:
		idx: int
		kind: str
		args: dict[str, object]

	class Queries:
		def __init__(self) -> None:
			self.rows = [
				Row(2, "missing_handler", {"id": "C"}),
				Row(1, "refund", {"id": "B"}),
				Row(0, "release_lock", {"id": "A"}),
			]
			self.marks: list[tuple[str, int, str]] = []

		async def list_pending_for_compensation(self, instance_id: str):
			assert instance_id == "instance-1"
			return list(self.rows)

		async def mark(self, instance_id: str, idx: int, status: str) -> bool:
			self.marks.append((instance_id, idx, status))
			return True

	queries = Queries()
	worker = CompensationWorker()
	handled: list[dict[str, object]] = []

	async def release_lock(args: dict[str, object]) -> None:
		handled.append(args)

	async def refund(_: dict[str, object]) -> None:
		raise RuntimeError("processor unavailable")

	worker.register("release_lock", release_lock)
	worker.register("refund", refund)

	assert worker.has_handler("release_lock") is True
	assert worker.has_handler("missing_handler") is False
	report = await worker.replay_pending("instance-1", queries)

	assert report.compensated == 1
	assert report.failed == 1
	assert report.skipped == 1
	assert report.total == 3
	assert handled == [{"id": "A"}]
	assert queries.marks == [
		("instance-1", 1, "failed"),
		("instance-1", 0, "compensated"),
	]


def test_compensation_worker_register_and_replay_validate_required_inputs() -> None:
	worker = CompensationWorker()

	with pytest.raises(AssertionError, match="kind is required"):
		worker.register("", lambda _: None)  # type: ignore[arg-type]
	with pytest.raises(AssertionError, match="handler is required"):
		worker.register("release_lock", None)  # type: ignore[arg-type]
