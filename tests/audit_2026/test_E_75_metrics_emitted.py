"""E-75 acceptance tests: per-fix metric emitters.

Verifies:
1. Each counter name string appears in at least one .py file under python/.
2. The no_orphan_promql_metrics.sh ratchet script exists and is executable.
3. ``import flowforge.engine.fire`` succeeds (smoke test).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

# All counter names E-75 requires to have source emitters.
EXPECTED_COUNTERS = [
	"flowforge_engine_fire_rejected_concurrent_total",
	"flowforge_audit_chain_breaks_total",
	"flowforge_audit_record_unique_violation_total",
	"flowforge_signing_secret_default_used_total",
	"flowforge_kms_transient_errors_total",
	"flowforge_tenancy_invalid_guc_key_total",
	"flowforge_migration_table_allowlist_rejections_total",
	"flowforge_jtbd_hub_package_install_unsigned_total",
	"flowforge_jtbd_hub_admin_legacy_token_uses_total",
	"flowforge_fastapi_csrf_config_error_total",
	"flowforge_fastapi_hub_cross_app_leak_total",
]


def _grep_python_src(metric_name: str) -> list[Path]:
	"""Return all .py files under python/ that reference *metric_name*."""
	python_dir = REPO_ROOT / "python"
	matches: list[Path] = []
	for py_file in python_dir.rglob("*.py"):
		if "__pycache__" in py_file.parts:
			continue
		try:
			if metric_name in py_file.read_text(encoding="utf-8"):
				matches.append(py_file)
		except (OSError, UnicodeDecodeError):
			pass
	return matches


def test_each_counter_has_source_emitter() -> None:
	"""Every counter name must appear in at least one .py file under python/."""
	missing: list[str] = []
	for counter in EXPECTED_COUNTERS:
		found = _grep_python_src(counter)
		if not found:
			missing.append(counter)

	assert not missing, (
		"The following E-75 metric counters have no emitter in python/:\n"
		+ "\n".join(f"  - {m}" for m in missing)
	)


def test_no_orphan_promql_ratchet_exists_and_is_executable() -> None:
	"""The no_orphan_promql_metrics.sh ratchet must exist and be executable."""
	ratchet = REPO_ROOT / "scripts" / "ci" / "ratchets" / "no_orphan_promql_metrics.sh"
	assert ratchet.exists(), f"Ratchet script not found: {ratchet}"
	mode = ratchet.stat().st_mode
	assert mode & stat.S_IXUSR, f"Ratchet script is not user-executable: {ratchet}"


def test_engine_fire_import_smoke() -> None:
	"""Importing flowforge.engine.fire must not raise."""
	import flowforge.engine.fire  # noqa: F401
