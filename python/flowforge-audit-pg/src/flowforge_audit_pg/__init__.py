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
]
