"""Layered feature flag for parallel_fork engine dispatch (E-79).

Two conditions must both be true for fork dispatch to activate:

1.  Global:        ``FLOWFORGE_FORKS_ENABLED`` env-var is ``1`` / ``true`` / ``yes``
                   (default **off** for v0.2.0; will flip to default-on in v0.3.0
                   after soak on the v0.2.0 release branch).

2.  Per-workflow:  the workflow manifest's ``metadata`` dict contains
                   ``engine_features: ["parallel_fork"]`` (opt-in at authoring
                   time so existing workflows are untouched when the global flag
                   is later toggled).
"""

from __future__ import annotations

import os


def forks_enabled() -> bool:
	"""Global feature flag. Default-off in v0.2.0; default-on in v0.3.0 after soak."""
	return os.environ.get("FLOWFORGE_FORKS_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def workflow_declares_fork(wd_metadata: dict) -> bool:
	"""True iff the workflow manifest declares engine_features: [parallel_fork]."""
	features = wd_metadata.get("engine_features", [])
	return "parallel_fork" in features
