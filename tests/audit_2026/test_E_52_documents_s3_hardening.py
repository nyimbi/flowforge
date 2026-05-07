"""E-52 — Documents-S3 hardening (audit-fix-plan §4.2/§4.3 DS-01..04, §7).

Findings:
- DS-01 (P1): ``doc_id`` validated against ``^[a-zA-Z0-9._-]+$``;
  ``doc_id = "../../etc"`` raises ``ValueError``.
- DS-02 (P1): class renamed ``S3DocumentPortInMemory``; old name
  ``S3DocumentPort`` re-exported with ``DeprecationWarning``.
- DS-03 (P2): ``presigned_put_url`` signs ``Content-Type`` so an attempt
  to upload with a wrong content-type fails signature verification on
  the S3 side.
- DS-04 (P2): real filetype sniffing distinguishes DOCX (PK ZIP carrying
  ``[Content_Types].xml``) from a generic ZIP archive.
"""

from __future__ import annotations

import io
import warnings
import zipfile
from typing import Any

import pytest


def _make_docx_bytes() -> bytes:
	"""Build a minimal DOCX (a ZIP with ``[Content_Types].xml``)."""

	buf = io.BytesIO()
	with zipfile.ZipFile(buf, mode="w") as z:
		z.writestr(
			"[Content_Types].xml",
			'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
		)
		z.writestr("word/document.xml", "<doc/>")
	return buf.getvalue()


def _make_plain_zip_bytes() -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, mode="w") as z:
		z.writestr("readme.txt", "hello")
	return buf.getvalue()


# ---------------------------------------------------------------------------
# DS-01 — doc_id validation
# ---------------------------------------------------------------------------


def test_DS_01_doc_id_validated_rejects_path_traversal() -> None:
	"""Constructor + every ``doc_id``-taking method rejects path-traversal
	shapes."""

	from flowforge_documents_s3.port import S3DocumentPortInMemory

	port = S3DocumentPortInMemory(bucket="b", client=_StubS3())

	bad_ids = [
		"../../etc",
		"../etc/passwd",
		"a/b/c",
		"foo bar",  # whitespace
		"foo;rm -rf /",
		"",
		"foo$bar",
		"\\windows\\system32",
		"‮txt.exe",  # right-to-left override
	]
	import asyncio

	async def _run() -> None:
		for bad in bad_ids:
			with pytest.raises(ValueError):
				await port.put(bad, b"data", content_type="application/octet-stream")
			with pytest.raises(ValueError):
				await port.get(bad)
			with pytest.raises(ValueError):
				await port.attach("subj-1", bad)
			with pytest.raises(ValueError):
				await port.delete(bad)
			with pytest.raises(ValueError):
				await port.presigned_get_url(bad)
			with pytest.raises(ValueError):
				await port.presigned_put_url(bad)

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_run())
	finally:
		loop.close()


def test_DS_01_doc_id_validated_accepts_legitimate_ids() -> None:
	"""Legitimate ids (alphanumeric + ``._-``) pass."""

	from flowforge_documents_s3.port import S3DocumentPortInMemory

	import asyncio

	port = S3DocumentPortInMemory(bucket="b", client=_StubS3())

	good_ids = [
		"doc-123",
		"doc_456",
		"doc.789",
		"DOC-2026-001",
		"a",
		"0123456789",
	]

	async def _run() -> None:
		for good in good_ids:
			# put, get, presigned_* must not raise on legit id
			await port.put(good, b"data", content_type="application/octet-stream")
			await port.presigned_get_url(good)
			await port.presigned_put_url(good)

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_run())
	finally:
		loop.close()


# ---------------------------------------------------------------------------
# DS-02 — class rename + deprecation alias
# ---------------------------------------------------------------------------


def test_DS_02_old_class_name_emits_deprecation_warning() -> None:
	"""Importing the legacy name ``S3DocumentPort`` from the package
	emits a ``DeprecationWarning`` pointing at the new name."""

	import importlib

	# Reset the module to ensure the warning fires (cached imports
	# wouldn't re-trigger filterwarnings inside the module).
	module_name = "flowforge_documents_s3.port"
	import sys

	if module_name in sys.modules:
		del sys.modules[module_name]
	if "flowforge_documents_s3" in sys.modules:
		del sys.modules["flowforge_documents_s3"]

	with warnings.catch_warnings(record=True) as caught:
		warnings.simplefilter("always")
		mod = importlib.import_module(module_name)
		# Legacy name is exported.
		assert hasattr(mod, "S3DocumentPort")
		# New name is the canonical class.
		assert hasattr(mod, "S3DocumentPortInMemory")
		# Touching the legacy name fires the deprecation warning.
		legacy = mod.S3DocumentPort
		assert legacy is mod.S3DocumentPortInMemory
		# At least one DeprecationWarning was emitted.
		dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
		assert dep, f"no DeprecationWarning fired; got {[w.category.__name__ for w in caught]}"
		assert any("S3DocumentPortInMemory" in str(w.message) for w in dep)


def test_DS_02_inmemory_suffix_in_class_name() -> None:
	"""The new class name ends in ``InMemory`` to convey index durability scope."""

	from flowforge_documents_s3.port import S3DocumentPortInMemory

	assert S3DocumentPortInMemory.__name__ == "S3DocumentPortInMemory"


# ---------------------------------------------------------------------------
# DS-03 — presigned PUT signs ContentType
# ---------------------------------------------------------------------------


def test_DS_03_presigned_put_url_signs_content_type() -> None:
	"""The presigned URL passes Content-Type into ``generate_presigned_url``
	so S3 rejects uploads with a mismatched header."""

	from flowforge_documents_s3.port import S3DocumentPortInMemory

	import asyncio

	stub = _StubS3()
	port = S3DocumentPortInMemory(bucket="b", client=stub)

	async def _run() -> None:
		await port.presigned_put_url("doc-1", content_type="application/pdf")

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_run())
	finally:
		loop.close()

	# The stub recorded the Params it received.
	last = stub.presigned_calls[-1]
	assert last["ClientMethod"] == "put_object"
	assert last["Params"]["ContentType"] == "application/pdf"
	assert last["Params"]["Bucket"] == "b"


def test_DS_03_presigned_post_returns_conditions_list() -> None:
	"""The new ``presigned_post`` helper returns a presigned POST policy
	with explicit ``Conditions=[['starts-with','$Content-Type', ...]]``
	so a host that wants strict server-side enforcement can opt in."""

	from flowforge_documents_s3.port import S3DocumentPortInMemory

	import asyncio

	stub = _StubS3()
	port = S3DocumentPortInMemory(bucket="b", client=stub)

	async def _run() -> None:
		await port.presigned_post("doc-1", content_type_prefix="application/pdf")

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_run())
	finally:
		loop.close()

	post = stub.presigned_post_calls[-1]
	conditions = post["Conditions"]
	assert ["starts-with", "$Content-Type", "application/pdf"] in conditions


# ---------------------------------------------------------------------------
# DS-04 — real filetype sniffing distinguishes DOCX from generic ZIP
# ---------------------------------------------------------------------------


def test_DS_04_filetype_sniff_distinguishes_docx_from_zip() -> None:
	"""``sniff_filetype(bytes)`` returns ``application/vnd.openxml...``
	for a DOCX archive and ``application/zip`` for a plain ZIP."""

	from flowforge_documents_s3.port import sniff_filetype

	docx_bytes = _make_docx_bytes()
	plain_zip = _make_plain_zip_bytes()

	docx_type = sniff_filetype(docx_bytes)
	zip_type = sniff_filetype(plain_zip)

	assert docx_type == (
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	), f"DOCX mis-detected as {docx_type!r}"
	assert zip_type == "application/zip", f"plain ZIP mis-detected as {zip_type!r}"


def test_DS_04_filetype_sniff_falls_back_for_unknown_bytes() -> None:
	"""Bytes with no recognised magic return ``application/octet-stream``."""

	from flowforge_documents_s3.port import sniff_filetype

	assert sniff_filetype(b"random bytes here") == "application/octet-stream"


def test_DS_04_put_validates_against_real_filetype() -> None:
	"""``put`` uses sniffed type when caller declares DOCX but bytes are
	a plain ZIP — the magic-bytes validator now rejects it."""

	from flowforge_documents_s3.port import (
		S3DocumentPortInMemory,
		UnsupportedMimeError,
	)
	import asyncio

	port = S3DocumentPortInMemory(bucket="b", client=_StubS3())

	async def _run() -> None:
		# Plain ZIP bytes uploaded under DOCX content-type → reject.
		with pytest.raises(UnsupportedMimeError):
			await port.put(
				"doc-1",
				_make_plain_zip_bytes(),
				content_type=(
					"application/vnd.openxmlformats-officedocument.wordprocessingml.document"
				),
			)
		# Real DOCX → passes.
		await port.put(
			"doc-2",
			_make_docx_bytes(),
			content_type=(
				"application/vnd.openxmlformats-officedocument.wordprocessingml.document"
			),
		)

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_run())
	finally:
		loop.close()


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _StubS3:
	"""Capture-only S3 stub for unit-test reach."""

	def __init__(self) -> None:
		self.put_calls: list[dict[str, Any]] = []
		self.get_calls: list[dict[str, Any]] = []
		self.delete_calls: list[dict[str, Any]] = []
		self.presigned_calls: list[dict[str, Any]] = []
		self.presigned_post_calls: list[dict[str, Any]] = []

	def put_object(self, **kw: Any) -> dict[str, Any]:
		self.put_calls.append(kw)
		return {"ETag": "stub-etag"}

	def get_object(self, **kw: Any) -> dict[str, Any]:
		self.get_calls.append(kw)

		class _Body:
			def read(self) -> bytes:
				return b"stub"

			def close(self) -> None:
				pass

		return {"Body": _Body()}

	def delete_object(self, **kw: Any) -> dict[str, Any]:
		self.delete_calls.append(kw)
		return {}

	def generate_presigned_url(self, ClientMethod: str, **kw: Any) -> str:
		self.presigned_calls.append({"ClientMethod": ClientMethod, **kw})
		return f"https://example/{ClientMethod}"

	def generate_presigned_post(self, **kw: Any) -> dict[str, Any]:
		self.presigned_post_calls.append(kw)
		return {"url": "https://example/post", "fields": {}}
