"""DMN decision table Pydantic models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HitPolicy(str, Enum):
	"""DMN hit policy — controls how many matching rules contribute to output."""

	FIRST = "FIRST"
	"""Return the first matching rule's output (DMN default)."""

	UNIQUE = "UNIQUE"
	"""Exactly one rule must match; raises DmnEvaluationError if zero or many match."""

	ANY = "ANY"
	"""All matching rules must produce the same output; raises if outputs differ."""

	ALL = "ALL"
	"""Return outputs from ALL matching rules as a list."""

	COLLECT = "COLLECT"
	"""Return outputs from all matching rules (same as ALL but more explicit)."""


class CompareOp(str, Enum):
	"""Comparison operator for a :class:`DmnCondition`."""

	EQ = "eq"
	NE = "ne"
	LT = "lt"
	LE = "le"
	GT = "gt"
	GE = "ge"
	IN = "in"
	NOT_IN = "not_in"
	CONTAINS = "contains"
	NOT_CONTAINS = "not_contains"
	STARTS_WITH = "starts_with"
	ENDS_WITH = "ends_with"
	NULL = "null"
	NOT_NULL = "not_null"
	BETWEEN = "between"


class DmnCondition(BaseModel):
	"""A single condition in a DMN rule.

	The ``field`` is a dot-notation path into the evaluation context
	(e.g., ``"applicant.credit_score"``).  The ``op`` is one of the
	:class:`CompareOp` values.  ``value`` is the comparison target;
	for ``BETWEEN`` it must be a two-element list ``[low, high]``.
	"""

	model_config = ConfigDict(extra="forbid")

	field: str
	op: CompareOp
	value: Any = None

	@model_validator(mode="after")
	def _validate_between(self) -> "DmnCondition":
		if self.op == CompareOp.BETWEEN:
			if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
				raise ValueError("BETWEEN operator requires value=[low, high]")
		return self


class DmnRule(BaseModel):
	"""One row in a DMN decision table."""

	model_config = ConfigDict(extra="forbid")

	id: str
	conditions: list[DmnCondition] = Field(default_factory=list)
	outputs: dict[str, Any] = Field(default_factory=dict)
	annotation: str = ""
	"""Human-readable note — not used in evaluation."""


class DmnTable(BaseModel):
	"""A DMN 1.3-style decision table.

	Attributes:
		id: Unique identifier for the table (used in error messages).
		name: Human-readable display name.
		hit_policy: How matching rules are combined (FIRST, UNIQUE, ANY, ALL).
		input_fields: Optional list of expected input field paths for
		              documentation purposes. Not enforced at eval time.
		output_fields: Optional list of expected output field names.
		rules: Ordered list of :class:`DmnRule` instances.
	"""

	model_config = ConfigDict(extra="forbid")

	id: str
	name: str = ""
	hit_policy: HitPolicy = HitPolicy.FIRST
	input_fields: list[str] = Field(default_factory=list)
	output_fields: list[str] = Field(default_factory=list)
	rules: list[DmnRule] = Field(default_factory=list)


__all__ = ["HitPolicy", "CompareOp", "DmnCondition", "DmnRule", "DmnTable"]
