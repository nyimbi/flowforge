"""S3DocumentPortInMemory — S3-backed DocumentPort with put/get/list/delete + presigned URLs.

Implements :class:`flowforge.ports.DocumentPort` over an S3 bucket. The
adapter keeps an **in-memory** index of subject->doc-ids and per-doc
metadata (kind, classification, content-type, uploaded-at). Hosts that
need durable indexing should pair this with their own SQL store and
treat S3 as the blob backend; this adapter is sufficient for tests,
demos, and single-process deployments.

E-52 hardening (audit-fix-plan §4.2/§4.3, §7):

* DS-01: ``doc_id`` is validated against ``^[a-zA-Z0-9._-]+$`` at every
  entry point. Path-traversal shapes like ``"../../etc"`` raise
  :class:`ValueError`.
* DS-02: the canonical class is :class:`S3DocumentPortInMemory` —
  emphasising that the *index* is in-memory even though the blob layer
  is durable. The legacy name :class:`S3DocumentPort` remains importable
  but emits :class:`DeprecationWarning` on access.
* DS-03: :meth:`presigned_put_url` signs the ``Content-Type`` parameter
  so an upload with a mismatched header fails signature verification.
  :meth:`presigned_post` exposes a presigned POST policy with explicit
  ``Conditions=[["starts-with","$Content-Type", ...]]`` for hosts that
  want strict server-side enforcement.
* DS-04: :func:`sniff_filetype` performs structural detection (DOCX vs
  generic ZIP, PDF, PNG, JPEG, GIF) so the magic-bytes validator can
  catch a plain ZIP being uploaded under the DOCX content-type.

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
import re
import warnings
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Protocol


# ----------------------------------------------------------------------
# DS-01 — doc_id validation
# ----------------------------------------------------------------------


# Allowed characters: alnum + dot + underscore + dash. Matches the audit
# spec's ``^[a-zA-Z0-9._-]+$``. Slash, traversal sequences, whitespace,
# control chars are all rejected.
_DOC_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class InvalidDocIdError(ValueError):
	"""Raised when a ``doc_id`` fails the alphanumeric+._- constraint.

	Audit-fix-plan §4.2 DS-01. Subclassing ``ValueError`` keeps the
	traditional ``pytest.raises(ValueError)`` test pattern working.
	"""


def _validate_doc_id(doc_id: Any) -> str:
	"""Validate *doc_id* and return it unchanged (or raise).

	Centralised so every entry-point method shares the same gate.
	"""

	if not isinstance(doc_id, str):
		raise InvalidDocIdError(
			f"doc_id must be str, got {type(doc_id).__name__}"
		)
	if not doc_id:
		raise InvalidDocIdError("doc_id must be non-empty")
	if len(doc_id) > 255:
		raise InvalidDocIdError(f"doc_id too long ({len(doc_id)} chars; max 255)")
	if not _DOC_ID_RE.match(doc_id):
		raise InvalidDocIdError(
			f"doc_id {doc_id!r} contains disallowed characters; "
			f"must match {_DOC_ID_RE.pattern}"
		)
	return doc_id


# ----------------------------------------------------------------------
# DS-04 — filetype sniffing
# ----------------------------------------------------------------------


def _is_docx_zip(data: bytes) -> bool:
	"""Return True iff *data* is a ZIP archive carrying a DOCX manifest
	(``[Content_Types].xml`` with the ``wordprocessingml`` schema)."""

	try:
		with zipfile.ZipFile(BytesIO(data)) as z:
			names = set(z.namelist())
			if "[Content_Types].xml" not in names:
				return False
			# DOCX-specific marker: word/document.xml is the canonical body.
			return "word/document.xml" in names or any(n.startswith("word/") for n in names)
	except zipfile.BadZipFile:
		return False


def _is_xlsx_zip(data: bytes) -> bool:
	try:
		with zipfile.ZipFile(BytesIO(data)) as z:
			names = set(z.namelist())
			if "[Content_Types].xml" not in names:
				return False
			return any(n.startswith("xl/") for n in names)
	except zipfile.BadZipFile:
		return False


def _is_pptx_zip(data: bytes) -> bool:
	try:
		with zipfile.ZipFile(BytesIO(data)) as z:
			names = set(z.namelist())
			if "[Content_Types].xml" not in names:
				return False
			return any(n.startswith("ppt/") for n in names)
	except zipfile.BadZipFile:
		return False


def sniff_filetype(data: bytes) -> str:
	"""Return the most-specific MIME type for *data* via structural sniffing.

	E-52 / DS-04: distinguishes DOCX / XLSX / PPTX (which all carry
	``PK\\x03\\x04`` ZIP magic) from a generic ZIP. Falls back to
	``application/octet-stream`` for unknown bytes.

	When the optional ``python-magic`` library is installed, its
	libmagic-backed detection runs FIRST and overrides the structural
	checks for non-Office types. The Office-doc structural check always
	wins over libmagic's ``application/zip`` because libmagic does not
	open the ZIP to look for the manifest.
	"""

	if not data:
		return "application/octet-stream"

	# ZIP path: check Office-doc structure first.
	if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
		if _is_docx_zip(data):
			return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
		if _is_xlsx_zip(data):
			return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
		if _is_pptx_zip(data):
			return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
		return "application/zip"

	if data.startswith(b"%PDF-"):
		return "application/pdf"
	if data.startswith(b"\x89PNG\r\n\x1a\n"):
		return "image/png"
	if data.startswith(b"\xff\xd8\xff"):
		return "image/jpeg"
	if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
		return "image/gif"

	# Optional libmagic-backed fallback.
	try:
		import magic as _magic  # type: ignore[import-not-found]

		mime = _magic.from_buffer(data, mime=True)
		if isinstance(mime, str) and mime:
			return mime
	except (ImportError, Exception):  # pragma: no cover — defensive
		pass

	return "application/octet-stream"


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


# Office content-types whose validation requires the structural-sniff
# step (E-52 / DS-04). A bare PK header is not enough — we must confirm
# the ZIP carries the corresponding manifest.
_OFFICE_STRUCTURAL_CHECKS: dict[
	str, "callable[..., bool]"  # type: ignore[type-arg]
] = {
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document": _is_docx_zip,
	"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _is_xlsx_zip,
	"application/vnd.openxmlformats-officedocument.presentationml.presentation": _is_pptx_zip,
}


class UnsupportedMimeError(ValueError):
	"""Raised when bytes don't match the expected content-type magic."""


class MagicBytesValidator(Protocol):
	"""Hook contract: raise :class:`UnsupportedMimeError` on mismatch."""

	def __call__(self, content_type: str, data: bytes) -> None: ...


def _default_magic_validator(content_type: str, data: bytes) -> None:
	"""Permissive validator: enforce magic for known types AND require
	structural ZIP-manifest agreement for the Office content-types."""

	prefixes = DEFAULT_MAGIC_BYTES.get(content_type)
	if not prefixes:
		return
	if not any(data.startswith(p) for p in prefixes):
		raise UnsupportedMimeError(
			f"bytes do not match magic prefix for content-type {content_type!r}",
		)
	# E-52 / DS-04: a bare PK header is not enough for Office types.
	checker = _OFFICE_STRUCTURAL_CHECKS.get(content_type)
	if checker is not None and not checker(data):
		raise UnsupportedMimeError(
			f"bytes carry ZIP magic but no {content_type!r} manifest "
			f"(generic ZIP cannot be uploaded under an Office content-type)",
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


class S3DocumentPortInMemory:
	"""S3-backed DocumentPort with an in-memory index.

	The blob layer is durable (S3); the per-doc metadata + subject index
	live in process memory and are lost on restart. Hosts that need
	durable indexing should pair this with their own SQL store; the
	``InMemory`` suffix in the class name is the contract advertising
	that scope (E-52 / DS-02).

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
		self._s3: Any = client
		# subject_id -> ordered list of doc_ids
		self._subject_index: dict[str, list[str]] = {}
		# doc_id -> DocumentMeta
		self._meta: dict[str, DocumentMeta] = {}

	# ------------------------------------------------------------------ key helpers

	def _key(self, doc_id: str) -> str:
		_validate_doc_id(doc_id)
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
		_validate_doc_id(doc_id)
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
		_validate_doc_id(doc_id)
		meta = self._meta.get(doc_id)
		return meta.classification if meta else None

	async def freshness_days(self, doc_id: str) -> int | None:
		_validate_doc_id(doc_id)
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
		_validate_doc_id(doc_id)
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
		_validate_doc_id(doc_id)
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
		_validate_doc_id(doc_id)
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
		_validate_doc_id(doc_id)
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

		E-52 / DS-03: the ``Content-Type`` parameter is signed into the
		URL, so an upload with a mismatched ``Content-Type`` header
		fails S3's signature verification. Hosts that need stricter
		server-side enforcement (e.g. a ``starts-with`` prefix policy)
		should prefer :meth:`presigned_post`.

		Note: presigned PUT uploads bypass the magic-bytes validator.
		Hosts that need server-side validation should prefer :meth:`put`.
		"""
		_validate_doc_id(doc_id)
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

	async def presigned_post(
		self,
		doc_id: str,
		*,
		content_type_prefix: str = "application/octet-stream",
		expires_in: int = 3600,
		max_size_bytes: int | None = None,
	) -> dict[str, Any]:
		"""Return a presigned POST policy with explicit Content-Type
		Conditions.

		E-52 / DS-03: the returned policy carries
		``Conditions=[["starts-with","$Content-Type", content_type_prefix]]``
		so S3 server-side rejects uploads whose ``Content-Type`` header
		does not start with the prefix. Hosts that want strict MIME
		enforcement use this in preference to :meth:`presigned_put_url`.
		"""

		_validate_doc_id(doc_id)
		assert expires_in > 0, "expires_in must be positive"
		conditions: list[Any] = [
			["starts-with", "$Content-Type", content_type_prefix],
		]
		if max_size_bytes is not None:
			assert max_size_bytes > 0, "max_size_bytes must be positive"
			conditions.append(["content-length-range", 1, int(max_size_bytes)])
		return await asyncio.to_thread(
			self._s3.generate_presigned_post,
			Bucket=self._bucket,
			Key=self._key(doc_id),
			Conditions=conditions,
			ExpiresIn=expires_in,
		)

	# ------------------------------------------------------------------ test seam

	def register_meta(self, meta: DocumentMeta) -> None:
		"""Seed metadata without an upload (test helper)."""
		self._meta[meta.doc_id] = meta


# ----------------------------------------------------------------------
# DS-02 — legacy alias with DeprecationWarning
# ----------------------------------------------------------------------


def __getattr__(name: str) -> Any:
	"""Module-level ``__getattr__`` (PEP 562) for the legacy class name.

	Importing :class:`S3DocumentPort` (the pre-E-52 name) emits a
	:class:`DeprecationWarning` pointing at the canonical
	:class:`S3DocumentPortInMemory` and returns the same class.
	"""

	if name == "S3DocumentPort":
		warnings.warn(
			"S3DocumentPort is deprecated; import S3DocumentPortInMemory instead. "
			"The original class kept an in-memory subject index, which the "
			"new name advertises explicitly. The legacy name will be removed "
			"in a future release.",
			DeprecationWarning,
			stacklevel=2,
		)
		return S3DocumentPortInMemory
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
