"""JTBD comment and review storage models (E-18).

Per ``framework/docs/jtbd-editor-arch.md`` §5.1 and
``framework/docs/flowforge-evolution.md`` §7.

Comments
--------
Each JTBD spec version has a comment thread keyed on
``(jtbd_id, version)``.  Comments support:

- ``@mention`` — a list of user-ids the comment notifies (hosts wire the
  :class:`flowforge.ports.notification.NotificationPort`).
- ``parent_id`` — threaded replies (one level of nesting).
- ``resolved`` — curator/author can mark a thread resolved.

Reviews
-------
A :class:`JtbdReview` is a formal sign-off on a spec version.  Only
holders of the ``jtbd.review`` permission may submit one; 4-eyes is
enforced by the API (publisher must differ from creator).

The three review decisions mirror the lifecycle state machine in
``jtbd-editor-arch.md`` §1.5: ``approve`` advances ``in_review →
published``; ``reject`` / ``request_changes`` pushes back to ``draft``.

These are **pure pydantic models** — storage (SQLAlchemy tables) is
handled by the alembic migration in ``db/alembic_bundle/versions/``
(E-1).  The models carry only business logic, not ORM concerns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _non_empty(v: str) -> str:
	if not v or not v.strip():
		raise ValueError("must be a non-empty string")
	return v


NonEmptyStr = Annotated[str, AfterValidator(_non_empty)]

ReviewDecision = Literal["approve", "reject", "request_changes"]


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# JtbdComment
# ---------------------------------------------------------------------------

class JtbdComment(BaseModel):
	"""A single comment in a JTBD spec-version thread.

	Comments are append-only.  Edits are modelled as ``replaced_by`` to
	preserve the audit chain.  Deletion is soft (``deleted=True``).
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	id: NonEmptyStr
	"""Stable comment identifier (UUID7 string)."""

	jtbd_id: NonEmptyStr
	"""The JTBD spec this comment belongs to."""

	version: NonEmptyStr
	"""Semver of the JTBD spec version (e.g., ``"1.4.0"``)."""

	author_user_id: NonEmptyStr
	"""User-id of the comment author."""

	body: NonEmptyStr
	"""Markdown-formatted comment body."""

	mentions: list[str] = Field(default_factory=list)
	"""List of ``@``-mentioned user-ids.  Populated by parsing ``body``
	for ``@<user_id>`` patterns; notification dispatch happens at the
	API layer, not here."""

	parent_id: str | None = None
	"""If set, this comment is a reply to the comment with this id."""

	resolved: bool = False
	"""Whether the thread started by this comment has been resolved.
	Only the root comment carries the resolved flag; replies inherit."""

	resolved_by_user_id: str | None = None
	"""Who marked the comment resolved (may differ from author)."""

	deleted: bool = False
	"""Soft-delete flag.  Body is replaced with ``[deleted]`` in the UI."""

	created_at: datetime = Field(default_factory=_utcnow)
	resolved_at: datetime | None = None


class NewCommentRequest(BaseModel):
	"""Input model for creating a new comment (POST /jtbd/{id}@{v}/comments)."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	body: NonEmptyStr
	parent_id: str | None = None
	mentions: list[str] = Field(default_factory=list)


class ResolveCommentRequest(BaseModel):
	"""Input model for resolving a comment thread."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	comment_id: NonEmptyStr


# ---------------------------------------------------------------------------
# JtbdReview
# ---------------------------------------------------------------------------

class JtbdReview(BaseModel):
	"""A formal review decision on a JTBD spec version.

	Decision semantics (mirrors the lifecycle state machine §1.5):

	- ``approve``          — ``in_review → published``
	- ``reject``           — ``in_review → draft``  (hard rejection)
	- ``request_changes``  — ``in_review → draft``  (reviewer wants tweaks)

	RBAC: the ``jtbd.review`` permission is required.  4-eyes check
	(reviewer ≠ version creator) is enforced at the API layer.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	id: NonEmptyStr
	"""Stable review identifier (UUID7 string)."""

	jtbd_id: NonEmptyStr
	version: NonEmptyStr

	reviewer_user_id: NonEmptyStr
	"""User-id of the reviewer (must hold ``jtbd.review`` permission)."""

	decision: ReviewDecision
	"""Outcome of the review."""

	body: str | None = None
	"""Optional prose explanation of the decision."""

	created_at: datetime = Field(default_factory=_utcnow)


class NewReviewRequest(BaseModel):
	"""Input model for submitting a review (POST /jtbd/{id}@{v}/reviews)."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	decision: ReviewDecision
	body: str | None = None


# ---------------------------------------------------------------------------
# @mention extraction helper
# ---------------------------------------------------------------------------

import re as _re

# E-59 / J-12: mention regex restricted to the host's actual user-id format.
# UMS user_ids are either a UUID7 (digits + hyphens, 36 chars) or a username
# of 1–64 chars. Both forms must:
#   * begin with an alphanumeric or underscore (no leading dot/hyphen),
#   * end with an alphanumeric or underscore (no trailing punctuation),
#   * use only alphanumeric, underscore, dot, or hyphen in between.
# Single-char usernames are accepted (the second alternation).
_MENTION_RE = _re.compile(
	r"@(?:([A-Za-z0-9_][\w.-]{0,62}[A-Za-z0-9_])|([A-Za-z0-9_]))(?!\w)"
)


def extract_mentions(body: str) -> list[str]:
	"""Return all ``@<user_id>`` tokens from *body* (deduped, ordered)."""
	seen: set[str] = set()
	out: list[str] = []
	for m in _MENTION_RE.finditer(body):
		# Group 1 = multi-char id; group 2 = single-char id; one is always set.
		uid = m.group(1) or m.group(2)
		if uid is None:
			continue
		if uid not in seen:
			seen.add(uid)
			out.append(uid)
	return out


__all__ = [
	"JtbdComment",
	"JtbdReview",
	"NewCommentRequest",
	"NewReviewRequest",
	"ResolveCommentRequest",
	"ReviewDecision",
	"extract_mentions",
]
