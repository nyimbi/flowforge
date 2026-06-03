"""E-73 phase 5 — JWT token revocation list.

In-memory revocation store with TTL-based expiry and auto-eviction.
Production hosts replace this with a Redis-backed or DB-backed impl by
subclassing :class:`RevocationList` and overriding the underscore-prefixed
storage accessors.

Metric emitted:
  ``flowforge_jwt_revocation_propagation_seconds`` — histogram observation
  recording the delay (in seconds) from when :meth:`revoke` was called to
  when the token was *first* rejected by :meth:`is_revoked`.  Useful for
  alerting on stale-cache propagation lag in distributed deployments.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _RevocationEntry:
	"""One revoked (user_id, jti) pair with expiry and propagation tracking."""

	expires_at: float
	"""Unix timestamp after which the entry auto-evicts."""

	revoked_at: float
	"""Unix timestamp when :meth:`RevocationList.revoke` was called."""

	first_rejected_at: float | None = field(default=None)
	"""Unix timestamp of the first :meth:`RevocationList.is_revoked` True hit.

	Populated on the first rejection so the propagation-lag metric fires
	exactly once per revocation event.
	"""


class RevocationList:
	"""In-memory revocation list for JWT-style signed tokens.

	Thread-safety: not assumed.  Async callers serialise access through
	the engine's per-instance lock or a single-threaded event loop.

	Construction:

	.. code-block:: python

	    revocation = RevocationList()
	    revocation.revoke(user_id="alice", jti="tok-1", ttl_seconds=30)
	    assert revocation.is_revoked("alice", "tok-1")
	"""

	def __init__(self) -> None:
		# Keyed by (user_id, jti).
		self._entries: dict[tuple[str, str], _RevocationEntry] = {}

	# ------------------------------------------------------------------
	# public API
	# ------------------------------------------------------------------

	def revoke(
		self,
		user_id: str,
		jti: str,
		*,
		ttl_seconds: int = 30,
	) -> None:
		"""Mark *(user_id, jti)* as revoked for *ttl_seconds*.

		If the pair is already present the TTL is extended (last-write-wins
		semantics — a re-revocation resets the expiry clock, which is safe
		because the entry is still rejected until the new expiry).
		"""
		now = time.time()
		self._entries[(user_id, jti)] = _RevocationEntry(
			expires_at=now + ttl_seconds,
			revoked_at=now,
		)

	def is_revoked(self, user_id: str, jti: str) -> bool:
		"""Return True if *(user_id, jti)* is currently revoked.

		Auto-evicts all expired entries on each call so the in-process
		footprint stays bounded.  Emits the propagation-lag histogram
		metric on the *first* True return per revocation event.
		"""
		self._evict_expired()
		entry = self._entries.get((user_id, jti))
		if entry is None:
			return False
		now = time.time()
		if now > entry.expires_at:
			# Expired between eviction pass and this lookup (race in tests
			# with a mocked clock — handle defensively).
			del self._entries[(user_id, jti)]
			return False

		# Emit propagation-lag metric once per revocation event.
		if entry.first_rejected_at is None:
			lag = now - entry.revoked_at
			entry.first_rejected_at = now
			try:
				from flowforge import config as _cfg
				_c = _cfg.current()
				if _c.metrics is not None:
					_c.metrics.record_histogram(
						"flowforge_jwt_revocation_propagation_seconds",
						lag,
						{},
					)
			except Exception:
				pass
		return True

	# ------------------------------------------------------------------
	# internals
	# ------------------------------------------------------------------

	def _evict_expired(self) -> None:
		now = time.time()
		expired = [k for k, v in self._entries.items() if now > v.expires_at]
		for k in expired:
			del self._entries[k]

	def __len__(self) -> int:
		"""Return the number of live (non-expired) entries."""
		self._evict_expired()
		return len(self._entries)


__all__ = ["RevocationList"]
