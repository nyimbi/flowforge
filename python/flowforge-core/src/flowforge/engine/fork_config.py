"""Layered feature flag for parallel_fork engine dispatch (E-79).

Two conditions must both be true for fork dispatch to activate:

1.  Global:        ``FLOWFORGE_FORKS_ENABLED`` env-var is absent or non-zero
                   (default **on** as of v0.3.0 — set ``FLOWFORGE_FORKS_ENABLED=0``
                   to disable). This flipped from default-off in v0.2.0 after the
                   v0.2.0 soak period confirmed stability on the release branch.

2.  Per-workflow:  the workflow manifest's ``metadata`` dict contains
                   ``engine_features: ["parallel_fork"]`` (opt-in at authoring
                   time so existing workflows are untouched by the global flag).
"""

from __future__ import annotations

import os


def forks_enabled() -> bool:
	"""Global feature flag. Default-on in v0.3.0; set FLOWFORGE_FORKS_ENABLED=0 to disable."""
	val = os.environ.get("FLOWFORGE_FORKS_ENABLED", "1").strip().lower()
	return val not in ("0", "false", "no")


def workflow_declares_fork(wd_metadata: dict) -> bool:
	"""True iff the workflow manifest declares engine_features: [parallel_fork]."""
	features = wd_metadata.get("engine_features", [])
	return "parallel_fork" in features
