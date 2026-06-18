"""flowforge-audit-pg — PostgreSQL AuditSink with sha256 hash chain."""

from .hash_chain import (
	AuditRow,
	TOMBSTONE,
	canonical_json,
	compute_row_sha,
	redact_payload,
	verify_chain_in_memory,
)
from .sink import PgAuditSink, create_tables, ff_audit_events
from .analytics import (
	cycle_time_stats,
	state_dwell_stats,
	transition_frequency,
	sla_compliance_rate,
	instance_funnel,
)

__all__ = [
	"PgAuditSink",
	"create_tables",
	"ff_audit_events",
	"AuditRow",
	"TOMBSTONE",
	"canonical_json",
	"compute_row_sha",
	"redact_payload",
	"verify_chain_in_memory",
	"cycle_time_stats",
	"state_dwell_stats",
	"transition_frequency",
	"sla_compliance_rate",
	"instance_funnel",
]
