"""parallel_fork / parallel_join engine helpers (E-74 scaffold).

These functions are NOT YET WIRED through ``engine.fire()`` — they exist
so callers and tests can build against a stable API while the wiring
lands. See ``framework/docs/design/E-74-parallel-fork-engine-wiring.md``.

Importing this module is safe; it has no side effects on the engine.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from flowforge._uuid7 import uuid7str
from flowforge.engine.tokens import Token, TokenSet

if TYPE_CHECKING:
	from flowforge.dsl.workflow_def import TransitionDef


class RegionStillForkedError(Exception):
	"""Raised when a primary ``fire()`` is attempted on a state whose
	region still has live tokens. Callers must drain via per-token
	``fire(..., token_id=...)`` first."""


class TokenAlreadyConsumedError(Exception):
	"""Raised when ``fire(..., token_id=X)`` is called for a token that
	was already advanced past its terminal join."""


def make_fork_tokens(
	*,
	region: str,
	branches: Iterable["TransitionDef"],
) -> list[Token]:
	"""Allocate one ``Token`` per outgoing branch transition.

	Token IDs are uuid7 (E-39). For replay determinism (E-74 R-3),
	callers replaying a recorded fire-trace should set
	``flowforge.engine._fork._uuid_factory`` to a deterministic source
	keyed on ``(instance_id, region, branch_index)``.
	"""
	tokens: list[Token] = []
	for branch in branches:
		token = Token(
			id=_uuid_factory(),
			region=region,
			state=branch.to,
		)
		tokens.append(token)
	return tokens


def all_branches_joined(
	tokens: TokenSet,
	region: str,
) -> bool:
	"""``True`` iff zero tokens remain in ``region``."""
	return tokens.count_in_region(region) == 0


def consume_token(tokens: TokenSet, token_id: str) -> None:
	"""Remove a token after its branch reaches the join.

	Raises ``TokenAlreadyConsumedError`` if the token was previously
	consumed (idempotency guard for at-least-once replay)."""
	if not _has_token(tokens, token_id):
		raise TokenAlreadyConsumedError(
			f"token already consumed or unknown: {token_id}"
		)
	tokens.remove(token_id)


def _has_token(tokens: TokenSet, token_id: str) -> bool:
	return any(t.id == token_id for t in tokens.list())


# Indirection for E-74 R-3 (replay determinism). Override in tests via
# monkeypatch when replaying recorded traces.
_uuid_factory = uuid7str
