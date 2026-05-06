"""OCI-like manifest format for jtbd-hub packages (E-24).

A :class:`JtbdManifest` describes a published JTBD library package.
It is content-addressed (``bundle_hash``), cryptographically signed
(``signature`` + ``key_id``), and versioned (semver ``version``).

The hash chain provides tamper-evidence; the signature provides
authenticity. Both fields are optional at construction time so callers
can build a manifest, sign it, and then attach the signature in a
second step.

Wire format — canonical JSON fields in alphabetical order, schema
version ``"1"`` fixed::

    {
      "author": "user@example.com",
      "bundle_hash": "sha256:abcdef…",
      "description": "Insurance domain JTBD library",
      "key_id": "hmac-v1",
      "name": "flowforge-jtbd-insurance",
      "published_at": "2026-05-06T00:00:00Z",
      "schema_version": "1",
      "signature": "base64…",
      "spec_hash": "sha256:…",
      "tags": ["insurance", "claims"],
      "version": "1.0.0"
    }
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JtbdManifest(BaseModel):
	"""Manifest for a JTBD library package published to jtbd-hub."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	schema_version: str = "1"
	name: str
	version: str
	description: str | None = None
	author: str | None = None

	# Content-addressed hashes
	spec_hash: str | None = None   # sha256:… of canonical bundle JSON
	bundle_hash: str | None = None # sha256:… of the raw bundle bytes

	# Signing (set after manifest is built)
	signature: str | None = None
	key_id: str | None = None

	published_at: datetime | None = None
	tags: list[str] = Field(default_factory=list)

	# ---------- helpers ----------

	def signing_payload(self) -> bytes:
		"""Return the canonical bytes to sign / verify.

		Excludes ``signature`` and ``key_id`` (those are the result of
		signing, not the input). The encoding is canonical regardless
		of how the manifest was constructed (direct ``__init__`` vs
		``model_validate`` from JSON): every declared field whose
		value is non-None lands in the body, sorted by name. This
		makes the signature stable across HTTP round-trips through
		the hub service (the wire JSON is parsed back into a fresh
		manifest with all fields populated).
		"""
		body: dict[str, Any] = {}
		for field_name in sorted(self.__class__.model_fields):
			if field_name in ("signature", "key_id"):
				continue
			val = getattr(self, field_name)
			if val is None:
				continue
			# Empty list defaults — drop so manifests that did not
			# explicitly set a list field hash the same as those that
			# did.
			if isinstance(val, list) and len(val) == 0:
				continue
			if isinstance(val, datetime):
				val = val.isoformat()
			body[field_name] = val
		return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

	def with_signature(self, signature: str, key_id: str) -> "JtbdManifest":
		"""Return a copy with ``signature`` and ``key_id`` populated."""
		return self.model_copy(update={"signature": signature, "key_id": key_id})

	def with_timestamp(self) -> "JtbdManifest":
		"""Return a copy with ``published_at`` set to now (UTC)."""
		return self.model_copy(
			update={"published_at": datetime.now(timezone.utc)}
		)


def bundle_hash(bundle_bytes: bytes) -> str:
	"""Return ``sha256:…`` digest of raw bundle bytes."""
	return "sha256:" + hashlib.sha256(bundle_bytes).hexdigest()


def manifest_from_bundle(
	name: str,
	version: str,
	bundle_bytes: bytes,
	*,
	description: str | None = None,
	author: str | None = None,
	tags: list[str] | None = None,
) -> JtbdManifest:
	"""Build a :class:`JtbdManifest` from a raw bundle bytes blob.

	Computes ``bundle_hash`` automatically.  The caller should attach a
	``spec_hash`` if they have one (from
	:func:`flowforge_jtbd.dsl.canonical.spec_hash`).
	"""
	from ..dsl.canonical import canonical_json

	try:
		parsed = json.loads(bundle_bytes)
		shash = "sha256:" + hashlib.sha256(canonical_json(parsed)).hexdigest()
	except Exception:
		shash = None

	return JtbdManifest(
		name=name,
		version=version,
		description=description,
		author=author,
		bundle_hash=bundle_hash(bundle_bytes),
		spec_hash=shash,
		tags=tags or [],
	)


__all__ = [
	"JtbdManifest",
	"bundle_hash",
	"manifest_from_bundle",
]
