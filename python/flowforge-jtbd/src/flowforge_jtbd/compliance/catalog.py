"""Compliance catalog reader (E-23).

Loads the per-regime required-job catalog from ``catalog.yaml`` in this
package directory and exposes it as a Python dict.

The canonical YAML ships as part of the package; hosts may override by
pointing the ``JTBD_COMPLIANCE_CATALOG`` environment variable at a
replacement YAML file.

Usage::

    from flowforge_jtbd.compliance.catalog import REQUIRED_JOBS

    required = REQUIRED_JOBS.get("GDPR", set())
    # → {"data_export", "data_erasure", "consent_capture", "breach_notification"}
"""

from __future__ import annotations

import os
from importlib.resources import files as _ir_files
from pathlib import Path
from typing import Any


def _load_yaml(path: Path) -> dict[str, Any]:
	"""Load a YAML file; pyyaml is available in the flowforge-cli dep tree."""
	try:
		import yaml  # type: ignore[import-untyped]
	except ImportError as exc:  # pragma: no cover
		raise RuntimeError(
			"pyyaml is required to load the compliance catalog. "
			"Install it with: pip install pyyaml"
		) from exc
	return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_catalog() -> dict[str, frozenset[str]]:
	"""Load and parse the YAML catalog into {regime: frozenset(job_ids)}."""
	override = os.environ.get("JTBD_COMPLIANCE_CATALOG")
	if override:
		raw = _load_yaml(Path(override))
	else:
		try:
			res = _ir_files("flowforge_jtbd.compliance").joinpath("catalog.yaml")
			import yaml  # type: ignore[import-untyped]
			raw = yaml.safe_load(res.read_text())
		except (ImportError, Exception):
			# pyyaml unavailable or resource not found — fall back to empty catalog.
			return {}

	result: dict[str, frozenset[str]] = {}
	for regime, entry in (raw or {}).items():
		jobs = entry.get("required_jobs", []) if isinstance(entry, dict) else []
		result[regime] = frozenset(jobs)
	return result


# Module-level singleton — loaded once at import time.
REQUIRED_JOBS: dict[str, frozenset[str]] = _load_catalog()


def required_jobs_for(regime: str) -> frozenset[str]:
	"""Return the set of required JTBD job ids for *regime*.

	Returns an empty frozenset for unknown regimes (instead of raising)
	so callers that iterate ``jtbd.compliance`` stay robust against
	custom regime extensions.
	"""
	return REQUIRED_JOBS.get(regime, frozenset())


def missing_jobs(
	declared_compliance: list[str],
	bundle_jtbd_ids: set[str],
) -> dict[str, frozenset[str]]:
	"""Return a mapping of regime → missing job ids.

	:param declared_compliance: Compliance regimes declared on the JTBD or
	  bundle.
	:param bundle_jtbd_ids: The set of JTBD ids present in the bundle.
	:returns: Dict mapping each regime that has gaps to its missing job ids.
	  Empty dict means no gaps.
	"""
	gaps: dict[str, frozenset[str]] = {}
	for regime in declared_compliance:
		required = required_jobs_for(regime)
		absent = required - bundle_jtbd_ids
		if absent:
			gaps[regime] = absent
	return gaps


__all__ = [
	"REQUIRED_JOBS",
	"missing_jobs",
	"required_jobs_for",
]
