"""Lint output model.

Mirrors the validator output shape in
``framework/docs/jtbd-editor-arch.md`` §2.5.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Severity = Literal["error", "warning", "info"]


class Issue(BaseModel):
	"""A single lint finding.

	The ``rule`` field carries a stable identifier; UI / CLI consumers
	may key off it for severity overrides or fix suggestions. Optional
	contextual fields are populated only when relevant — e.g.,
	``cycle`` is set by the dependency analyzer, ``role`` by the actor
	analyzer.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	severity: Severity
	rule: str
	message: str
	fixhint: str | None = None
	doc_url: str | None = None
	# Contextual fields. Populated only when relevant.
	stage: str | None = None
	role: str | None = None
	context: str | None = None
	cycle: list[str] | None = None
	related_jtbds: list[str] = Field(default_factory=list)
	extra: dict[str, Any] = Field(default_factory=dict)


class JtbdResult(BaseModel):
	"""Issues collected for a single JTBD."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	jtbd_id: str
	version: str
	issues: list[Issue] = Field(default_factory=list)


class LintReport(BaseModel):
	"""Top-level lint output.

	``ok`` is ``False`` iff at least one issue across all results has
	severity ``"error"``.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	ok: bool
	results: list[JtbdResult] = Field(default_factory=list)
	# Bundle-level issues that are not bound to a specific JTBD (e.g.,
	# a dependency cycle that spans several specs).
	bundle_issues: list[Issue] = Field(default_factory=list)
	# Optional helper output. Populated only when DependencyGraph runs
	# without errors.
	topological_order: list[str] | None = None

	def errors(self) -> list[Issue]:
		out: list[Issue] = list(self.bundle_issues)
		for result in self.results:
			out.extend(issue for issue in result.issues if issue.severity == "error")
		return [issue for issue in out if issue.severity == "error"]

	def warnings(self) -> list[Issue]:
		out: list[Issue] = list(self.bundle_issues)
		for result in self.results:
			out.extend(issue for issue in result.issues if issue.severity == "warning")
		return [issue for issue in out if issue.severity == "warning"]


__all__ = ["Issue", "JtbdResult", "LintReport", "Severity"]
