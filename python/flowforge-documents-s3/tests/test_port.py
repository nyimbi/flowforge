"""S3DocumentPort + NoopDocumentPort tests (moto-backed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from flowforge.ports import DocumentPort
from flowforge_documents_s3 import (
	DEFAULT_MAGIC_BYTES,
	DocumentMeta,
	NoopDocumentPort,
	S3DocumentPort,
	UnsupportedMimeError,
)


pytestmark = pytest.mark.asyncio


BUCKET = "ff-docs-test"
PDF_HEADER = b"%PDF-1.4\n"
PNG_HEADER = b"\x89PNG\r\n\x1a\n"


# ---------- fixtures ---------------------------------------------------


@pytest.fixture
def s3_client():
	with mock_aws():
		client = boto3.client("s3", region_name="us-east-1")
		client.create_bucket(Bucket=BUCKET)
		yield client


@pytest.fixture
def port(s3_client) -> S3DocumentPort:
	return S3DocumentPort(BUCKET, client=s3_client)


# ---------- protocol satisfaction --------------------------------------


async def test_s3_satisfies_document_port(port: S3DocumentPort) -> None:
	assert isinstance(port, DocumentPort)


async def test_noop_satisfies_document_port() -> None:
	assert isinstance(NoopDocumentPort(), DocumentPort)


# ---------- noop -------------------------------------------------------


async def test_noop_returns_empty_everywhere() -> None:
	noop = NoopDocumentPort()
	assert await noop.list_for_subject("subject-1") == []
	assert await noop.list_for_subject("subject-1", kinds=["passport"]) == []
	await noop.attach("subject-1", "doc-1")  # no-op
	assert await noop.get_classification("doc-1") is None
	assert await noop.freshness_days("doc-1") is None


# ---------- put + get round-trip --------------------------------------


async def test_put_get_roundtrip(port: S3DocumentPort, s3_client) -> None:
	body = PDF_HEADER + b"hello world"
	meta = await port.put(
		"doc-1",
		body,
		kind="passport",
		classification="confidential",
		content_type="application/pdf",
	)
	assert isinstance(meta, DocumentMeta)
	assert meta.doc_id == "doc-1"
	assert meta.classification == "confidential"
	assert meta.size_bytes == len(body)

	# Round-trip via the adapter.
	assert await port.get("doc-1") == body

	# Sanity-check the underlying S3 object exists at the prefixed key.
	resp = s3_client.get_object(Bucket=BUCKET, Key="documents/doc-1")
	assert resp["ContentType"] == "application/pdf"
	assert resp["Metadata"]["classification"] == "confidential"
	assert resp["Metadata"]["kind"] == "passport"


# ---------- list / delete ---------------------------------------------


async def test_list_filters_by_prefix(port: S3DocumentPort) -> None:
	await port.put("alpha-1", PDF_HEADER, content_type="application/pdf")
	await port.put("alpha-2", PDF_HEADER, content_type="application/pdf")
	await port.put("beta-1", PDF_HEADER, content_type="application/pdf")

	all_docs = await port.list()
	assert {m.doc_id for m in all_docs} == {"alpha-1", "alpha-2", "beta-1"}

	alphas = await port.list(prefix="alpha-")
	assert {m.doc_id for m in alphas} == {"alpha-1", "alpha-2"}


async def test_delete_removes_from_index_and_s3(port: S3DocumentPort, s3_client) -> None:
	await port.put("doc-x", PDF_HEADER, content_type="application/pdf")
	await port.attach("subject-1", "doc-x")
	assert await port.delete("doc-x") is True

	# Subsequent delete is a no-op (returns False).
	assert await port.delete("doc-x") is False

	# Index purged.
	assert await port.list_for_subject("subject-1") == []
	assert await port.get_classification("doc-x") is None

	# S3 object gone.
	with pytest.raises(s3_client.exceptions.NoSuchKey):
		s3_client.get_object(Bucket=BUCKET, Key="documents/doc-x")


# ---------- DocumentPort surface --------------------------------------


async def test_attach_unknown_doc_raises(port: S3DocumentPort) -> None:
	with pytest.raises(KeyError):
		await port.attach("subject-1", "nope")


async def test_list_for_subject_filters_by_kind(port: S3DocumentPort) -> None:
	await port.put("p1", PDF_HEADER, kind="passport", content_type="application/pdf")
	await port.put("d1", PDF_HEADER, kind="drivers_license", content_type="application/pdf")
	await port.attach("user-1", "p1")
	await port.attach("user-1", "d1")

	all_for_user = await port.list_for_subject("user-1")
	assert {d["id"] for d in all_for_user} == {"p1", "d1"}

	just_passports = await port.list_for_subject("user-1", kinds=["passport"])
	assert [d["id"] for d in just_passports] == ["p1"]
	assert just_passports[0]["kind"] == "passport"
	assert "uploaded_at" in just_passports[0]


async def test_attach_is_idempotent(port: S3DocumentPort) -> None:
	await port.put("p1", PDF_HEADER, content_type="application/pdf")
	await port.attach("user-1", "p1")
	await port.attach("user-1", "p1")
	rows = await port.list_for_subject("user-1")
	assert len(rows) == 1


async def test_classification_and_freshness(port: S3DocumentPort) -> None:
	await port.put(
		"d1",
		PDF_HEADER,
		classification="restricted",
		content_type="application/pdf",
	)
	assert await port.get_classification("d1") == "restricted"
	assert await port.get_classification("missing") is None
	# Freshly uploaded -> 0 days old.
	assert await port.freshness_days("d1") == 0
	assert await port.freshness_days("missing") is None


async def test_freshness_days_reflects_uploaded_at(port: S3DocumentPort) -> None:
	# Seed a doc with an uploaded_at 10 days in the past.
	stale_at = datetime.now(timezone.utc) - timedelta(days=10)
	port.register_meta(
		DocumentMeta(
			doc_id="stale",
			kind="passport",
			classification="internal",
			content_type="application/pdf",
			uploaded_at=stale_at,
			size_bytes=0,
		),
	)
	days = await port.freshness_days("stale")
	assert days is not None and days >= 9


# ---------- magic-bytes validator -------------------------------------


async def test_magic_bytes_default_blocks_mismatch(port: S3DocumentPort) -> None:
	with pytest.raises(UnsupportedMimeError):
		await port.put("bad", b"not a pdf at all", content_type="application/pdf")


async def test_magic_bytes_passes_for_valid_png(port: S3DocumentPort) -> None:
	meta = await port.put("png1", PNG_HEADER + b"\x00rest", content_type="image/png")
	assert meta.content_type == "image/png"


async def test_magic_bytes_passes_for_unknown_content_type(port: S3DocumentPort) -> None:
	# Default validator is permissive for content-types it doesn't recognise.
	meta = await port.put("blob1", b"\x00\x01\x02", content_type="application/octet-stream")
	assert meta.size_bytes == 3


async def test_custom_validator_overrides_default(s3_client) -> None:
	calls: list[tuple[str, int]] = []

	def strict(content_type: str, data: bytes) -> None:
		calls.append((content_type, len(data)))
		if not data.startswith(b"OK"):
			raise UnsupportedMimeError("must start with OK")

	port = S3DocumentPort(BUCKET, client=s3_client, magic_validator=strict)
	await port.put("ok1", b"OK-data", content_type="text/plain")
	with pytest.raises(UnsupportedMimeError):
		await port.put("bad1", b"not ok", content_type="text/plain")
	assert calls == [("text/plain", 7), ("text/plain", 6)]


async def test_default_magic_bytes_table_covers_pdf_png_jpeg() -> None:
	assert "application/pdf" in DEFAULT_MAGIC_BYTES
	assert "image/png" in DEFAULT_MAGIC_BYTES
	assert "image/jpeg" in DEFAULT_MAGIC_BYTES


# ---------- presigned URLs --------------------------------------------


async def test_presigned_get_url(port: S3DocumentPort) -> None:
	await port.put("d1", PDF_HEADER, content_type="application/pdf")
	url = await port.presigned_get_url("d1", expires_in=600)
	assert url.startswith("https://") or url.startswith("http://")
	assert "documents/d1" in url
	assert "Signature" in url or "X-Amz-Signature" in url


async def test_presigned_put_url(port: S3DocumentPort) -> None:
	url = await port.presigned_put_url(
		"d2",
		content_type="application/pdf",
		expires_in=600,
	)
	assert "documents/d2" in url
	assert "Signature" in url or "X-Amz-Signature" in url


async def test_presigned_url_rejects_zero_expiry(port: S3DocumentPort) -> None:
	with pytest.raises(AssertionError):
		await port.presigned_get_url("d1", expires_in=0)


# ---------- key prefix customisation ----------------------------------


async def test_custom_key_prefix(s3_client) -> None:
	port = S3DocumentPort(BUCKET, client=s3_client, key_prefix="vault/")
	await port.put("d1", PDF_HEADER, content_type="application/pdf")
	# The object should land at vault/d1, not documents/d1.
	resp = s3_client.get_object(Bucket=BUCKET, Key="vault/d1")
	assert resp["ContentType"] == "application/pdf"


async def test_blank_key_prefix_uses_doc_id_directly(s3_client) -> None:
	port = S3DocumentPort(BUCKET, client=s3_client, key_prefix="")
	await port.put("d1", PDF_HEADER, content_type="application/pdf")
	resp = s3_client.get_object(Bucket=BUCKET, Key="d1")
	assert resp["Metadata"]["doc_id"] == "d1"
