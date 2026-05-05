# flowforge-documents-s3

S3-backed `DocumentPort` adapter for flowforge, plus a `NoopDocumentPort`
fallback for hosts that don't ship a document subsystem.

## Install

```bash
pip install flowforge-documents-s3[s3]      # runtime (boto3)
pip install flowforge-documents-s3[dev]     # adds moto + pytest
```

## Usage

```python
import boto3
from flowforge_documents_s3 import S3DocumentPort

port = S3DocumentPort(
    bucket="my-bucket",
    client=boto3.client("s3"),
    key_prefix="documents/",
)

await port.put(
    "doc-123",
    pdf_bytes,
    kind="passport",
    classification="confidential",
    content_type="application/pdf",
)
await port.attach(subject_id="user-42", doc_id="doc-123")

rows = await port.list_for_subject("user-42", kinds=["passport"])
url = await port.presigned_get_url("doc-123", expires_in=600)
```

The adapter satisfies `flowforge.ports.DocumentPort` and adds:

- `put(doc_id, data, *, kind, classification, content_type)` — upload + index
- `get(doc_id)` — download bytes
- `list(prefix=None)` — list locally-tracked docs
- `delete(doc_id)` — remove blob + index entry
- `presigned_get_url(doc_id, *, expires_in)` and `presigned_put_url(...)`
- `MagicBytesValidator` hook (default validator covers PDF, PNG, JPEG, GIF, ZIP, DOCX, XLSX)

## Testing

The test suite uses `moto[s3]`; no live AWS credentials required.

```bash
uv run pytest framework/python/flowforge-documents-s3
```

## Noop fallback

```python
from flowforge_documents_s3 import NoopDocumentPort
port = NoopDocumentPort()  # returns [] / None for everything
```
