# flowforge-documents-s3

S3-backed document store adapter for flowforge, with magic-bytes validation and presigned URL helpers.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install "flowforge-documents-s3[s3]"      # runtime (boto3)
uv pip install "flowforge-documents-s3[dev]"     # adds moto + pytest
```

## What it does

`S3DocumentPortInMemory` implements `flowforge.ports.DocumentPort` over an S3 bucket. The blob layer is durable (S3 objects); the per-doc metadata and subject index live in process memory. The `InMemory` suffix in the class name is the contract: hosts that need durable indexing should pair this adapter with their own SQL store and treat S3 as the blob backend only.

Every `put` call runs the magic-bytes validator before the upload. The default validator checks known content-type signatures (PDF, PNG, JPEG, GIF, ZIP, DOCX, XLSX) and — for Office document types — opens the ZIP to confirm the correct internal manifest is present, not just the bare `PK` header. Both the validator and the structural sniff can be overridden or disabled per adapter instance.

`NoopDocumentPort` is a drop-in for hosts that have no document subsystem. It returns empty lists for everything and never raises; workflows that gate on document presence stall predictably rather than crashing.

boto3 is synchronous; all calls are wrapped in `asyncio.to_thread` so the adapter is safe to call from async code.

## Quick start

```python
import boto3
from flowforge_documents_s3 import S3DocumentPortInMemory

port = S3DocumentPortInMemory(
	bucket="my-bucket",
	client=boto3.client("s3"),
	key_prefix="documents/",
)

# Upload with validation
meta = await port.put(
	"passport-doc-123",
	pdf_bytes,
	kind="passport",
	classification="confidential",
	content_type="application/pdf",
)

# Attach to a subject (idempotent)
await port.attach(subject_id="user-42", doc_id="passport-doc-123")

# List documents for a subject
rows = await port.list_for_subject("user-42", kinds=["passport"])

# Presigned GET URL
url = await port.presigned_get_url("passport-doc-123", expires_in=600)

# Presigned PUT (Content-Type signed into URL — DS-03)
put_url = await port.presigned_put_url(
	"passport-doc-123",
	content_type="application/pdf",
	expires_in=300,
)

# Presigned POST with server-side Content-Type enforcement
post_policy = await port.presigned_post(
	"passport-doc-123",
	content_type_prefix="application/pdf",
	max_size_bytes=10 * 1024 * 1024,
)
```

Noop fallback:

```python
from flowforge_documents_s3 import NoopDocumentPort
port = NoopDocumentPort()
rows = await port.list_for_subject("user-42")  # always []
```

## Public API

- `S3DocumentPortInMemory(bucket, *, client, key_prefix, magic_validator)` — main adapter
- `S3DocumentPortInMemory.put(doc_id, data, *, kind, classification, content_type)` — upload + index
- `S3DocumentPortInMemory.get(doc_id)` — download bytes
- `S3DocumentPortInMemory.list(prefix=None)` — list locally-known docs
- `S3DocumentPortInMemory.delete(doc_id)` — remove S3 object + local index entry
- `S3DocumentPortInMemory.attach(subject_id, doc_id)` — link doc to subject (idempotent)
- `S3DocumentPortInMemory.list_for_subject(subject_id, kinds=None)` — list docs by subject
- `S3DocumentPortInMemory.presigned_get_url(doc_id, *, expires_in)` — presigned GET
- `S3DocumentPortInMemory.presigned_put_url(doc_id, *, content_type, expires_in)` — presigned PUT with signed Content-Type
- `S3DocumentPortInMemory.presigned_post(doc_id, *, content_type_prefix, expires_in, max_size_bytes)` — presigned POST with policy conditions
- `NoopDocumentPort` — empty-result fallback
- `DocumentMeta` — frozen dataclass with `doc_id`, `kind`, `classification`, `content_type`, `uploaded_at`, `size_bytes`, `subject_ids`
- `MagicBytesValidator` — `Protocol` for the upload validation hook
- `sniff_filetype(data)` — structural MIME detection (DOCX/XLSX/PPTX vs generic ZIP, PDF, PNG, JPEG, GIF)
- `DEFAULT_MAGIC_BYTES` — default prefix table used by the built-in validator
- `InvalidDocIdError` — raised on invalid `doc_id` (subclasses `ValueError`)
- `UnsupportedMimeError` — raised when bytes fail magic-bytes validation (subclasses `ValueError`)

Note: `S3DocumentPort` (the pre-audit name) still imports but emits `DeprecationWarning` and returns `S3DocumentPortInMemory`.

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `bucket` | required | S3 bucket name; must already exist |
| `key_prefix` | `"documents/"` | Prepended to every S3 object key |
| `magic_validator` | built-in | Pass a no-op lambda to disable; pass a custom callable to extend |

AWS credentials and region come from the standard boto3 credential chain (env vars, `~/.aws/credentials`, instance profile).

## Audit-2026 hardening

- **DS-01** (E-52): `doc_id` is validated against `^[a-zA-Z0-9._-]+$` at every entry point (`put`, `get`, `delete`, `attach`, presigned URL methods); path-traversal strings like `"../../etc/passwd"` raise `InvalidDocIdError` before touching S3
- **DS-02** (E-52): the canonical class is `S3DocumentPortInMemory`; the `InMemory` suffix advertises that the subject index is process-local; the legacy name `S3DocumentPort` emits `DeprecationWarning` and maps to the same class
- **DS-03** (E-52): `presigned_put_url` signs the `ContentType` parameter into the URL so S3 rejects uploads with a mismatched header; `presigned_post` carries `Conditions=[["starts-with","$Content-Type", prefix]]` for strict server-side MIME enforcement
- **DS-04** (E-52): `sniff_filetype` performs structural detection — it opens ZIP archives to check for the DOCX/XLSX/PPTX manifest; a generic ZIP uploaded under an Office content-type fails the magic-bytes validator even though both carry the `PK\x03\x04` header

## Compatibility

- Python 3.11+
- `boto3` (optional; install with `[s3]` extra)
- `moto[s3]` (optional; install with `[dev]` extra for tests)
- `python-magic` (optional; used by `sniff_filetype` as a libmagic fallback for non-Office types)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge-core`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-signing-kms`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-signing-kms)
- [`flowforge-audit-pg`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-audit-pg)
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
