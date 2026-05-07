"""UUID7 shim — project convention per CLAUDE.md.

The historical ``uuid_extensions`` package referenced in older docs is
not on PyPI. We depend on ``uuid6`` (MIT, on PyPI) and re-export
``uuid7str`` from this module so callers don't import the third-party
package directly.

UUID7 is preferred over UUID4 for primary keys because it is
time-monotonic when sorted lexicographically — that pairs well with
B-tree indexes, audit-chain ordinals, and replay determinism.
"""

from __future__ import annotations

from uuid6 import uuid7


def uuid7str() -> str:
	"""Return a fresh UUID7 as a 36-char canonical-form string."""

	return str(uuid7())


__all__ = ["uuid7str"]
