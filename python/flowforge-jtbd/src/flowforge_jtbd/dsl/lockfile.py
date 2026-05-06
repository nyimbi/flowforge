"""Pydantic models for the ``jtbd.lock`` artefact.

A lockfile pins every JTBD a composition includes to an exact
``(version, spec_hash, source)`` triple. The body itself hashes through
the same canonical-JSON path as specs do, so a CI run that reads the
lockfile bytes and re-hashes them can verify nothing drifted between
``flowforge jtbd lock`` and the current commit.

Layering:

* :class:`JtbdLockfilePin` — one row per pinned JTBD.
* :class:`JtbdComposition` — the project bundle's identity (the thing
  the lockfile is locking). Composition rows live in
  ``flowforge.jtbd_compositions``; this class is the in-memory view.
* :class:`JtbdLockfile` — the lockfile body itself. The
  :meth:`compute_body_hash` helper produces the canonical-JSON hash;
  the storage row in ``flowforge.jtbd_lockfiles`` records both the
  body and that hash separately so re-derivation is testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
	AfterValidator,
	BaseModel,
	ConfigDict,
	Field,
	model_validator,
)

from .spec import IdStr, SemverStr, SpecHashStr

LockfileSource = Literal["local", "jtbd-hub", "git", "filesystem"]


def _utcnow() -> datetime:
	"""Default factory for the lockfile ``generated_at`` field."""
	return datetime.now(timezone.utc)


def _utc_aware(value: datetime) -> datetime:
	"""Reject naïve datetimes; everything in the lockfile is UTC."""
	if value.tzinfo is None:
		raise ValueError("datetime must be timezone-aware (UTC)")
	return value.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_utc_aware)]


class JtbdLockfilePin(BaseModel):
	"""One pin in a lockfile body.

	Two pins for the same ``jtbd_id`` are forbidden (the lockfile must
	resolve every JTBD to exactly one version). The
	:class:`JtbdLockfile` validator enforces uniqueness across pins.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	jtbd_id: IdStr
	version: SemverStr
	spec_hash: SpecHashStr
	source: LockfileSource = "local"
	source_ref: str | None = None
	"""Free-form pointer back to the source — package@version for hub
	pins, file path for local, git ref for git, etc."""


class JtbdComposition(BaseModel):
	"""In-memory view of a ``jtbd_compositions`` row.

	A composition is a named bundle binding a list of JTBD ids; the
	:class:`JtbdLockfile` is the resolved snapshot of those ids at
	specific versions.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	id: str
	tenant_id: str | None = None
	name: str
	project_package: IdStr
	jtbd_ids: list[IdStr] = Field(default_factory=list, min_length=1)
	created_at: UtcDatetime = Field(default_factory=_utcnow)
	updated_at: UtcDatetime = Field(default_factory=_utcnow)


class JtbdLockfile(BaseModel):
	"""The on-disk ``jtbd.lock`` artefact.

	* ``schema_version`` is fixed at ``"1"`` for this release; bumping
	  it is a breaking change and triggers a migration prompt in the
	  CLI.
	* ``body_hash`` is computed via the same canonical-JSON path as
	  ``spec_hash``. It is *not* part of the canonical body — it is
	  metadata about the body — so :meth:`canonical_body` excludes it
	  for hashing.
	* ``generated_at`` defaults to ``now`` at creation time. Re-running
	  :meth:`with_body_hash` on a freshly-loaded lockfile preserves the
	  original timestamp; only the hash is recomputed.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	schema_version: Literal["1"] = "1"
	composition_id: str
	project_package: IdStr
	pins: list[JtbdLockfilePin] = Field(default_factory=list)
	generated_at: UtcDatetime = Field(default_factory=_utcnow)
	generated_by: str | None = None
	body_hash: SpecHashStr | None = None

	@model_validator(mode="after")
	def _unique_jtbd_pins(self) -> "JtbdLockfile":
		seen: set[str] = set()
		for pin in self.pins:
			if pin.jtbd_id in seen:
				raise ValueError(
					f"duplicate pin for jtbd_id={pin.jtbd_id!r} in lockfile"
					f" composition_id={self.composition_id!r}"
				)
			seen.add(pin.jtbd_id)
		return self

	def canonical_body(self) -> dict[str, object]:
		"""Return the dict shape used to compute ``body_hash``.

		Pins are sorted by ``jtbd_id`` so two lockfiles whose pin order
		differs (but whose set is equal) hash to the same value. The
		``body_hash`` field is excluded — it is computed *over* the
		body, not part of it.
		"""
		dumped = self.model_dump(mode="json", exclude_none=False)
		dumped.pop("body_hash", None)
		dumped.pop("generated_at", None)  # treated as metadata, not body
		dumped.pop("generated_by", None)
		pins = dumped.get("pins") or []
		if isinstance(pins, list):
			pins.sort(key=lambda p: p.get("jtbd_id", ""))
			dumped["pins"] = pins
		return dumped

	def compute_body_hash(self) -> str:
		"""Return the freshly-computed ``sha256:...`` for this lockfile."""
		from .canonical import spec_hash as _spec_hash

		return _spec_hash(self.canonical_body())

	def with_body_hash(self) -> "JtbdLockfile":
		"""Return a copy with ``body_hash`` populated."""
		return self.model_copy(update={"body_hash": self.compute_body_hash()})


__all__ = [
	"JtbdComposition",
	"JtbdLockfile",
	"JtbdLockfilePin",
	"LockfileSource",
	"UtcDatetime",
]
