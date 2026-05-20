from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from flowforge.engine import _fork
from flowforge.engine.subworkflow import SubworkflowHandle
from flowforge.engine.timers import elapsed_seconds, fire_at, sla_percent
from flowforge.engine.tokens import Token, TokenSet


def test_token_set_tracks_tokens_by_region() -> None:
	tokens = TokenSet()
	tokens.add(Token(id="a", region="parallel-review", state="review_a"))
	tokens.add(Token(id="b", region="parallel-review", state="review_b"))
	tokens.add(Token(id="c", region="other", state="review_c"))

	assert [token.id for token in tokens.list()] == ["a", "b", "c"]
	assert tokens.count_in_region("parallel-review") == 2
	assert tokens.count_in_region("missing") == 0

	tokens.remove("a")
	tokens.remove("unknown")

	assert [token.id for token in tokens.list()] == ["b", "c"]
	assert tokens.count_in_region("parallel-review") == 1


def test_timer_helpers_bound_sla_percent() -> None:
	started = datetime(2026, 1, 1, tzinfo=timezone.utc)
	now = datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc)

	assert elapsed_seconds(started, now) == 30
	assert sla_percent(started, 60, now) == 50
	assert sla_percent(started, 0, now) == 0
	assert sla_percent(now, 60, started) == 0
	assert sla_percent(started, 10, now) == 100
	assert fire_at(started, 45).isoformat() == "2026-01-01T00:00:45+00:00"


def test_subworkflow_handle_defaults_context() -> None:
	handle = SubworkflowHandle(
		parent_instance_id="parent-1",
		child_instance_id="child-1",
		subworkflow_key="kyc_review",
	)

	assert handle.depth == 1
	assert handle.context == {}

	other = SubworkflowHandle(
		parent_instance_id="parent-2",
		child_instance_id="child-2",
		subworkflow_key="kyc_review",
	)
	handle.context["decision"] = "approved"
	assert other.context == {}


def test_make_fork_tokens_and_consume_token(monkeypatch: pytest.MonkeyPatch) -> None:
	ids = iter(["tok-1", "tok-2"])
	monkeypatch.setattr(_fork, "_uuid_factory", lambda: next(ids))

	@dataclass
	class Branch:
		to: str

	tokens = TokenSet()
	for token in _fork.make_fork_tokens(
		region="parallel-review",
		branches=[Branch("review_a"), Branch("review_b")],
	):
		tokens.add(token)

	assert [(token.id, token.region, token.state) for token in tokens.list()] == [
		("tok-1", "parallel-review", "review_a"),
		("tok-2", "parallel-review", "review_b"),
	]
	assert not _fork.all_branches_joined(tokens, "parallel-review")

	_fork.consume_token(tokens, "tok-1")
	assert tokens.count_in_region("parallel-review") == 1

	_fork.consume_token(tokens, "tok-2")
	assert _fork.all_branches_joined(tokens, "parallel-review")

	with pytest.raises(_fork.TokenAlreadyConsumedError, match="tok-2"):
		_fork.consume_token(tokens, "tok-2")
