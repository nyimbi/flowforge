"""Parallel-region tokens (for ``parallel_fork`` / ``parallel_join`` states).

A token represents one running parallel branch. The fork creates N
tokens; the join consumes them as branches complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Token:
	id: str
	region: str
	state: str
	context: dict[str, Any] = field(default_factory=dict)


class TokenSet:
	"""Bag of tokens for one instance."""

	def __init__(self) -> None:
		self._tokens: dict[str, Token] = {}

	def add(self, token: Token) -> None:
		self._tokens[token.id] = token

	def remove(self, token_id: str) -> None:
		self._tokens.pop(token_id, None)

	def list(self) -> list[Token]:
		return list(self._tokens.values())

	def count_in_region(self, region: str) -> int:
		return sum(1 for t in self._tokens.values() if t.region == region)
