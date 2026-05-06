"""flowforge-jtbd — JTBD canonical spec, lockfile, storage, and linter.

The package is split into two cohabiting namespaces:

* :mod:`flowforge_jtbd.dsl` (E-1) — canonical ``JtbdSpec``,
  ``JtbdBundle``, ``JtbdLockfile`` plus canonical-JSON / hash helpers.
  This is the wire-format truth.
* :mod:`flowforge_jtbd.spec` (E-4) — lint-facing models
  (``JtbdLintSpec``, lint-side ``JtbdBundle``, ``ActorRef``,
  ``RoleDef``, ``StageDecl``). The linter only needs a slim subset of
  the canonical model and stays ``extra='allow'`` so it rides forward
  through schema churn.
* :mod:`flowforge_jtbd.lint` (E-4) — the linter itself
  (``Linter``, ``LifecycleAnalyzer``, ``DependencyGraph``,
  ``ActorConsistencyAnalyzer``) plus the pluggable rule registry.

Top-level re-exports are intentionally empty so the two namespaces do
not collide on shared names like ``JtbdBundle``. Import the namespace
you need explicitly.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
