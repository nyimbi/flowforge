# flowforge-documents-s3 changelog

## 0.1.0 (U09)

- `S3DocumentPort` — DocumentPort impl over S3 with put/get/list/delete + presigned URLs.
- `NoopDocumentPort` — empty-result DocumentPort for hosts without docs.
- `DocumentMeta` dataclass exposing kind, classification, content-type, uploaded-at, size-bytes.
- `SQLiteDocumentIndex` — dependency-free durable metadata and subject-index store for hosts that need S3 blobs plus restart-safe lookup.
- `MagicBytesValidator` hook with default coverage for PDF, PNG, JPEG, GIF, ZIP, DOCX, XLSX.
- Tests with `moto[s3]`; no live AWS required.
