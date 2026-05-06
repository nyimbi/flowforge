"""Linter core for JTBD bundles.

Implements ticket E-4 of the JTBD Editor evolution plan
(see ``framework/docs/flowforge-evolution.md`` §4 and
``framework/docs/jtbd-editor-arch.md`` §2).

Public API:

- :class:`Linter` — top-level orchestrator. Runs the lifecycle,
  dependency, and actor analyzers plus any registered rule packs and
  returns a :class:`LintReport`.
- :class:`LifecycleAnalyzer` — completeness analysis.
- :class:`DependencyGraph` — cycle detection + topological order.
- :class:`ActorConsistencyAnalyzer` — capacity / authority checks.
- :class:`RuleRegistry`, :class:`JtbdRule`, :class:`JtbdRulePack` —
  pluggable rule machinery for per-domain extensions (E-5 ships the
  first packs).
- :class:`Issue`, :class:`JtbdResult`, :class:`LintReport` — output
  data model.
"""

from __future__ import annotations

from .actors import ActorConsistencyAnalyzer
from .dependencies import DependencyCycle, DependencyGraph
from .glossary import GlossaryConflictRule, GlossaryConflictRulePack, builtin_glossary_pack
from .quality import LowQualityRule, LowQualityRulePack
from .lifecycle import LifecycleAnalyzer
from .linter import Linter
from .registry import (
	JtbdRule,
	JtbdRulePack,
	RuleRegistry,
	StaticRulePack,
)
from .results import (
	Issue,
	JtbdResult,
	LintReport,
	Severity,
)

__all__ = [
	"ActorConsistencyAnalyzer",
	"DependencyCycle",
	"DependencyGraph",
	"GlossaryConflictRule",
	"GlossaryConflictRulePack",
	"Issue",
	"JtbdResult",
	"JtbdRule",
	"JtbdRulePack",
	"LifecycleAnalyzer",
	"LintReport",
	"Linter",
	"RuleRegistry",
	"Severity",
	"StaticRulePack",
	"builtin_glossary_pack",
	"LowQualityRule",
	"LowQualityRulePack",
]
