"""Ratchet SnapshotConflict retry guidance for SQLAlchemy hosts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sqlalchemy_readme_documents_snapshot_conflict_retry_policy() -> None:
	readme = (ROOT / "python" / "flowforge-sqlalchemy" / "README.md").read_text(
		encoding="utf-8"
	)

	assert "### SnapshotConflict retry policy" in readme
	for required in (
		"Require an idempotency key",
		"discard the stale in-memory `Instance`",
		"Re-read the latest snapshot",
		"retry budget small",
		"HTTP `409 Conflict`",
		):
			assert required in readme
