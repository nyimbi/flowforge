"""Pluggable reputation scorer for jtbd-hub packages.

The default scorer follows the §9.3 contract from
``framework/docs/jtbd-editor-arch.md``: ``downloads × stars × age_decay``.
Hosts that want a different policy (e.g., curation-weighted, penalty
for demoted packages) implement the :class:`ReputationScorer` Protocol
and pass the alternative to :func:`PackageRegistry.set_scorer`.

The scoring math is intentionally small + auditable: an author should
be able to read the source and know exactly what their score reflects.
We avoid time-of-day / TZ-dependent calculations by quantising the
age decay to whole days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

# Forward-declared to break the import cycle between registry + scorer.
# The `Package` Protocol below pins the surface the scorer needs without
# importing the concrete class.


@runtime_checkable
class ScorablePackage(Protocol):
	"""Protocol surface the scorer reads.

	Properties (read-only) so concrete implementations can compute
	``average_stars`` / ``rating_count`` lazily — Pydantic's
	``@computed_field`` and dataclass ``@property`` both qualify.
	"""

	@property
	def downloads(self) -> int: ...
	@property
	def average_stars(self) -> float: ...
	@property
	def rating_count(self) -> int: ...
	@property
	def published_at(self) -> datetime: ...
	@property
	def demoted(self) -> bool: ...


@runtime_checkable
class ReputationScorer(Protocol):
	"""Score a package on the 0..∞ scale.

	Implementations must be deterministic given the package state +
	``now``: same inputs in, same score out. Negative scores are
	allowed (a curator-weighted scorer might penalise demoted
	packages below zero).
	"""

	def score(self, package: ScorablePackage, *, now: datetime) -> float:
		...


@dataclass
class DefaultReputationScorer:
	"""``downloads × average_stars × age_decay``.

	* ``half_life_days`` controls how fast popularity decays — at 180
	  days a package retains exp(-1) ≈ 36.8% of its peak. Set to 0 to
	  disable decay entirely.
	* ``demote_factor`` multiplies the score for demoted packages.
	  Default 0.1 matches the arch's "demoted but searchable" intent.
	* ``no_ratings_penalty`` multiplies the score when a package has
	  no ratings yet — keeps unrated packages from ranking above
	  established 5-star ones. Default 0.5.
	"""

	half_life_days: float = 180.0
	demote_factor: float = 0.1
	no_ratings_penalty: float = 0.5

	def score(self, package: ScorablePackage, *, now: datetime) -> float:
		days = max(0.0, _whole_days(now - package.published_at))
		decay = (
			math.exp(-days / self.half_life_days)
			if self.half_life_days > 0
			else 1.0
		)
		stars_factor = (
			package.average_stars
			if package.rating_count > 0
			else self.no_ratings_penalty
		)
		raw = max(package.downloads, 1) * stars_factor * decay
		if package.demoted:
			raw *= self.demote_factor
		return raw


def _whole_days(delta) -> float:  # type: ignore[no-untyped-def]
	"""Return *delta* in whole days as a float (works on any tz-aware
	delta)."""
	return delta.total_seconds() / 86400.0


def utcnow() -> datetime:
	"""Convenience for tests + scorers that need a default clock."""
	return datetime.now(timezone.utc)


__all__ = [
	"DefaultReputationScorer",
	"ReputationScorer",
	"ScorablePackage",
	"utcnow",
]
