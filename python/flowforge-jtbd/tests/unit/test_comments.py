"""Tests for E-18 — JtbdComment + JtbdReview models.

Covers model validation, field defaults, extract_mentions helper,
and request models.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from flowforge_jtbd.db.comments import (
	JtbdComment,
	JtbdReview,
	NewCommentRequest,
	NewReviewRequest,
	ResolveCommentRequest,
	extract_mentions,
)


# ---------------------------------------------------------------------------
# JtbdComment
# ---------------------------------------------------------------------------

def _comment(**overrides: object) -> JtbdComment:
	base = {
		"id": "cmt-1",
		"jtbd_id": "claim_intake",
		"version": "1.4.0",
		"author_user_id": "alice",
		"body": "This looks good to me.",
	}
	return JtbdComment.model_validate({**base, **overrides})


def test_comment_basic_fields() -> None:
	c = _comment()
	assert c.id == "cmt-1"
	assert c.jtbd_id == "claim_intake"
	assert c.version == "1.4.0"
	assert c.author_user_id == "alice"
	assert c.body == "This looks good to me."


def test_comment_defaults() -> None:
	c = _comment()
	assert c.mentions == []
	assert c.parent_id is None
	assert c.resolved is False
	assert c.deleted is False
	assert c.resolved_by_user_id is None
	assert c.resolved_at is None
	assert isinstance(c.created_at, datetime)


def test_comment_with_mentions() -> None:
	c = _comment(mentions=["bob", "carol"])
	assert c.mentions == ["bob", "carol"]


def test_comment_with_parent_id() -> None:
	c = _comment(parent_id="cmt-0")
	assert c.parent_id == "cmt-0"


def test_comment_resolved_fields() -> None:
	now = datetime.now(timezone.utc)
	c = _comment(resolved=True, resolved_by_user_id="bob", resolved_at=now)
	assert c.resolved is True
	assert c.resolved_by_user_id == "bob"
	assert c.resolved_at == now


def test_comment_empty_id_raises() -> None:
	with pytest.raises(ValidationError):
		_comment(id="")


def test_comment_empty_body_raises() -> None:
	with pytest.raises(ValidationError):
		_comment(body="   ")


def test_comment_empty_author_raises() -> None:
	with pytest.raises(ValidationError):
		_comment(author_user_id="")


def test_comment_extra_field_raises() -> None:
	with pytest.raises(ValidationError):
		JtbdComment.model_validate({
			"id": "x", "jtbd_id": "y", "version": "1.0.0",
			"author_user_id": "u", "body": "b", "unknown_field": 1,
		})


# ---------------------------------------------------------------------------
# JtbdReview
# ---------------------------------------------------------------------------

def _review(**overrides: object) -> JtbdReview:
	base = {
		"id": "rev-1",
		"jtbd_id": "claim_intake",
		"version": "1.4.0",
		"reviewer_user_id": "carol",
		"decision": "approve",
	}
	return JtbdReview.model_validate({**base, **overrides})


def test_review_basic_fields() -> None:
	r = _review()
	assert r.id == "rev-1"
	assert r.jtbd_id == "claim_intake"
	assert r.reviewer_user_id == "carol"
	assert r.decision == "approve"


def test_review_decisions_all_valid() -> None:
	for d in ("approve", "reject", "request_changes"):
		r = _review(decision=d)
		assert r.decision == d


def test_review_invalid_decision_raises() -> None:
	with pytest.raises(ValidationError):
		_review(decision="defer")


def test_review_body_optional() -> None:
	r = _review()
	assert r.body is None


def test_review_with_body() -> None:
	r = _review(body="Missing audit stage.")
	assert r.body == "Missing audit stage."


def test_review_created_at_default() -> None:
	r = _review()
	assert isinstance(r.created_at, datetime)


# ---------------------------------------------------------------------------
# NewCommentRequest
# ---------------------------------------------------------------------------

def test_new_comment_request_minimal() -> None:
	req = NewCommentRequest(body="Looks good.")
	assert req.body == "Looks good."
	assert req.parent_id is None
	assert req.mentions == []


def test_new_comment_request_with_mentions() -> None:
	req = NewCommentRequest(body="@alice LGTM", mentions=["alice"])
	assert req.mentions == ["alice"]


def test_new_comment_request_empty_body_raises() -> None:
	with pytest.raises(ValidationError):
		NewCommentRequest(body="")


# ---------------------------------------------------------------------------
# NewReviewRequest
# ---------------------------------------------------------------------------

def test_new_review_request() -> None:
	req = NewReviewRequest(decision="approve")
	assert req.decision == "approve"
	assert req.body is None


def test_new_review_request_with_body() -> None:
	req = NewReviewRequest(decision="request_changes", body="Add audit stage.")
	assert req.body == "Add audit stage."


def test_new_review_request_invalid_decision_raises() -> None:
	with pytest.raises(ValidationError):
		NewReviewRequest(decision="maybe")


# ---------------------------------------------------------------------------
# ResolveCommentRequest
# ---------------------------------------------------------------------------

def test_resolve_comment_request() -> None:
	req = ResolveCommentRequest(comment_id="cmt-42")
	assert req.comment_id == "cmt-42"


def test_resolve_comment_request_empty_id_raises() -> None:
	with pytest.raises(ValidationError):
		ResolveCommentRequest(comment_id="")


# ---------------------------------------------------------------------------
# extract_mentions
# ---------------------------------------------------------------------------

def test_extract_mentions_basic() -> None:
	assert extract_mentions("@alice and @bob") == ["alice", "bob"]


def test_extract_mentions_empty() -> None:
	assert extract_mentions("no mentions here") == []


def test_extract_mentions_deduped() -> None:
	assert extract_mentions("@alice @alice") == ["alice"]


def test_extract_mentions_preserves_order() -> None:
	assert extract_mentions("@carol @bob @alice") == ["carol", "bob", "alice"]


def test_extract_mentions_with_dots() -> None:
	assert extract_mentions("@john.doe LGTM") == ["john.doe"]


def test_extract_mentions_multiple_in_body() -> None:
	body = "Hey @alice, @bob thinks @carol should review."
	result = extract_mentions(body)
	assert "alice" in result
	assert "bob" in result
	assert "carol" in result
	assert len(result) == 3
