"""S3DocumentPort — S3-backed DocumentPort with put/get/list/delete + presigned URLs.

Implements :class:`flowforge.ports.DocumentPort` over an S3 bucket. The
adapter keeps an **in-memory** index of subject->doc-ids and per-doc
metadata (kind, classification, content-type, uploaded-at). Hosts that
need durable indexing should pair this with their own SQL store and
treat S3 as the blob backend; this adapter is sufficient for tests,
demos, and single-process deployments.

Magic-bytes validation runs on every ``put`` via the
:class:`MagicBytesValidator` hook. The default validator is permissive;
strict hosts pass an allow-list of ``content_type -> magic_prefixes``.

Only the ``boto3`` synchronous client is used; calls are wrapped in
``asyncio.to_thread`` so the adapter is safe to call from async
engines. boto3 is an optional install (``pip install
flowforge-documents-s3[s3]``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


# ----------------------------------------------------------------------
# Magic-bytes validation
# ----------------------------------------------------------------------


# Conservative default magic-byte prefixes (hex). Empty list means
# "accept anything"; hosts override per-content-type as needed.
DEFAULT_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
	"application/pdf": (b"%PDF-",),
	"image/png": (b"\x89PNG\r\n\x1a\n",),
	"image/jpeg": (b"\xff\xd8\xff",),
	"image/gif": (b"GIF87a", b"GIF89a"),
	"application/zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document": (b"PK\x03\x04",),
	"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
}


class UnsupportedMimeError(ValueError):
	"""Raised when bytes don't match the expected content-type magic."""


class MagicBytesValidator(Protocol):
	"""Hook contract: raise :class:`UnsupportedMimeError` on mismatch."""

	def __call__(self, content_type: str, data: bytes) -> None: ...


def _default_magic_validator(content_type: str, data: bytes) -> None:
	"""Permissive validator: enforce magic only for known content types."""
	prefixes = DEFAULT_MAGIC_BYTES.get(content_type)
	if not prefixes:
		return
	if not any(data.startswith(p) for p in prefixes):
		raise UnsupportedMimeError(
			f"bytes do not match magic prefix for content-type {content_type!r}",
		)


# ----------------------------------------------------------------------
# Per-document metadata
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentMeta:
	"""Metadata persisted alongside the S3 object.

	The adapter stores these as S3 object metadata (``x-amz-meta-*``)
	and also keeps a parallel in-memory copy keyed by ``doc_id`` so
	reads don't need a HEAD round-trip.
	"""

	doc_id: str
	kind: str = "unknown"
	classification: str = "internal"
	content_type: str = "application/octet-stream"
	uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
	size_bytes: int = 0
	subject_ids: tuple[str, ...] = ()


# ----------------------------------------------------------------------
# S3 adapter
# ----------------------------------------------------------------------


class S3DocumentPort:
	"""S3-backed DocumentPort.

	Args:
		bucket: S3 bucket name. Must already exist.
		client: A boto3 S3 client. Pass ``None`` to construct one
			from the environment via ``boto3.client('s3')``.
		key_prefix: Prefix prepended to every object key
			(default: ``"documents/"``).
		magic_validator: Override the default magic-bytes validator.
			Pass a no-op lambda to disable validation entirely.
	"""

	def __init__(
		self,
		bucket: str,
		*,
		client: Any | None = None,
		key_prefix: str = "documents/",
		magic_validator: MagicBytesValidator | None = None,
	) -> None:
		assert bucket and isinstance(bucket, str), "bucket required"
		assert isinstance(key_prefix, str), "key_prefix must be str"
		self._bucket = bucket
		self._prefix = key_prefix.rstrip("/") + "/" if key_prefix else ""
		self._validate_magic: MagicBytesValidator = (
			magic_validator if magic_validator is not None else _default_magic_validator
		)
		if client is None:
			import boto3  # type: ignore[import-untyped]

			client = boto3.client("s3")
		self._s3 = client
		# subject_id -> ordered list of doc_ids
		self._subject_index: dict[str, list[str]] = {}
		# doc_id -> DocumentMeta
		self._meta: dict[str, DocumentMeta] = {}

	# ------------------------------------------------------------------ key helpers

	def _key(self, doc_id: str) -> str:
		assert doc_id, "doc_id required"
		return f"{self._prefix}{doc_id}"

	# ------------------------------------------------------------------ DocumentPort protocol

	async def list_for_subject(
		self,
		subject_id: str,
		kinds: list[str] | None = None,
	) -> list[dict[str, Any]]:
		"""Return descriptors of every doc attached to *subject_id*.

		Each descriptor is shaped::

			{
				"id": doc_id,
				"kind": kind,
				"classification": classification,
				"content_type": content_type,
				"uploaded_at": iso8601,
				"size_bytes": int,
			}
		"""
		assert isinstance(subject_id, str) and subject_id, "subject_id required"
		ids = self._subject_index.get(subject_id, [])
		kind_set = set(kinds) if kinds else None
		out: list[dict[str, Any]] = []
		for doc_id in ids:
			meta = self._meta.get(doc_id)
			if meta is None:
				continue
			if kind_set is not None and meta.kind not in kind_set:
				continue
			out.append(_descriptor(meta))
		return out

	async def attach(self, subject_id: str, doc_id: str) -> None:
		"""Attach an existing document to *subject_id*.

		The document must already exist (created via :meth:`put`). The
		index is idempotent: re-attaching the same pair is a no-op.
		"""
		assert isinstance(subject_id, str) and subject_id, "subject_id required"
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		if doc_id not in self._meta:
			raise KeyError(f"document {doc_id!r} not found; call put() first")
		ids = self._subject_index.setdefault(subject_id, [])
		if doc_id not in ids:
			ids.append(doc_id)
		# Keep meta.subject_ids in sync (frozen dataclass -> replace).
		meta = self._meta[doc_id]
		if subject_id not in meta.subject_ids:
			self._meta[doc_id] = DocumentMeta(
				doc_id=meta.doc_id,
				kind=meta.kind,
				classification=meta.classification,
				content_type=meta.content_type,
				uploaded_at=meta.uploaded_at,
				size_bytes=meta.size_bytes,
				subject_ids=tuple([*meta.subject_ids, subject_id]),
			)

	async def get_classification(self, doc_id: str) -> str | None:
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		meta = self._meta.get(doc_id)
		return meta.classification if meta else None

	async def freshness_days(self, doc_id: str) -> int | None:
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		meta = self._meta.get(doc_id)
		if meta is None:
			return None
		delta = datetime.now(timezone.utc) - meta.uploaded_at
		return max(delta.days, 0)

	# ------------------------------------------------------------------ blob API

	async def put(
		self,
		doc_id: str,
		data: bytes,
		*,
		kind: str = "unknown",
		classification: str = "internal",
		content_type: str = "application/octet-stream",
	) -> DocumentMeta:
		"""Upload *data* under *doc_id* and register classification metadata.

		Runs the magic-bytes validator before the upload; raises
		:class:`UnsupportedMimeError` on mismatch.
		"""
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		assert isinstance(data, (bytes, bytearray)), "data must be bytes"
		self._validate_magic(content_type, bytes(data))
		key = self._key(doc_id)
		metadata = {
			"kind": kind,
			"classification": classification,
			"doc_id": doc_id,
		}
		await asyncio.to_thread(
			self._s3.put_object,
			Bucket=self._bucket,
			Key=key,
			Body=bytes(data),
			ContentType=content_type,
			Metadata=metadata,
		)
		meta = DocumentMeta(
			doc_id=doc_id,
			kind=kind,
			classification=classification,
			content_type=content_type,
			size_bytes=len(data),
		)
		self._meta[doc_id] = meta
		assert doc_id in self._meta
		return meta

	async def get(self, doc_id: str) -> bytes:
		"""Download the bytes for *doc_id* from S3."""
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		key = self._key(doc_id)
		resp = await asyncio.to_thread(
			self._s3.get_object,
			Bucket=self._bucket,
			Key=key,
		)
		body = resp["Body"]
		try:
			return await asyncio.to_thread(body.read)
		finally:
			close = getattr(body, "close", None)
			if close is not None:
				close()

	async def list(self, prefix: str | None = None) -> list[DocumentMeta]:
		"""List every locally-known document, optionally filtered by *prefix*.

		``prefix`` matches against ``doc_id`` (not the S3 key).
		"""
		out: list[DocumentMeta] = []
		for doc_id, meta in self._meta.items():
			if prefix is None or doc_id.startswith(prefix):
				out.append(meta)
		return out

	async def delete(self, doc_id: str) -> bool:
		"""Delete the S3 object and forget local metadata.

		Returns ``True`` if the doc existed locally, ``False`` otherwise.
		"""
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		key = self._key(doc_id)
		await asyncio.to_thread(
			self._s3.delete_object,
			Bucket=self._bucket,
			Key=key,
		)
		existed = doc_id in self._meta
		self._meta.pop(doc_id, None)
		for ids in self._subject_index.values():
			if doc_id in ids:
				ids.remove(doc_id)
		return existed

	# ------------------------------------------------------------------ presigned URLs

	async def presigned_get_url(self, doc_id: str, *, expires_in: int = 3600) -> str:
		"""Return a presigned GET URL for *doc_id*."""
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		assert expires_in > 0, "expires_in must be positive"
		return await asyncio.to_thread(
			self._s3.generate_presigned_url,
			"get_object",
			Params={"Bucket": self._bucket, "Key": self._key(doc_id)},
			ExpiresIn=expires_in,
		)

	async def presigned_put_url(
		self,
		doc_id: str,
		*,
		content_type: str = "application/octet-stream",
		expires_in: int = 3600,
	) -> str:
		"""Return a presigned PUT URL for *doc_id*.

		Note: presigned uploads bypass the magic-bytes validator. Hosts
		that need server-side validation should prefer :meth:`put`.
		"""
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		assert expires_in > 0, "expires_in must be positive"
		return await asyncio.to_thread(
			self._s3.generate_presigned_url,
			"put_object",
			Params={
				"Bucket": self._bucket,
				"Key": self._key(doc_id),
				"ContentType": content_type,
			},
			ExpiresIn=expires_in,
		)

	# ------------------------------------------------------------------ test seam

	def register_meta(self, meta: DocumentMeta) -> None:
		"""Seed metadata without an upload (test helper)."""
		self._meta[meta.doc_id] = meta


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _descriptor(meta: DocumentMeta) -> dict[str, Any]:
	return {
		"id": meta.doc_id,
		"kind": meta.kind,
		"classification": meta.classification,
		"content_type": meta.content_type,
		"uploaded_at": meta.uploaded_at.isoformat(),
		"size_bytes": meta.size_bytes,
	}
