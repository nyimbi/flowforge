"""flowforge-documents-s3 — S3-backed DocumentPort + noop fallback.

Two implementations of :class:`flowforge.ports.DocumentPort`:

* :class:`S3DocumentPort` — buckets documents in S3, keeps an in-memory
  index of ``(subject_id -> [doc_id])`` plus per-doc metadata
  (kind, classification, content-type, uploaded-at) so the Protocol
  surface is satisfied without a separate database.
* :class:`NoopDocumentPort` — returns empty lists for hosts that have
  no document subsystem.

Both implementations expose magic-bytes validation hooks for upload
validation. ``S3DocumentPort`` additionally exposes raw blob
``put``/``get``/``list``/``delete`` plus presigned-URL helpers.
"""

from __future__ import annotations

from .noop import NoopDocumentPort
from .port import (
	DEFAULT_MAGIC_BYTES,
	DocumentMeta,
	MagicBytesValidator,
	S3DocumentPort,
	UnsupportedMimeError,
)

__all__ = [
	"DEFAULT_MAGIC_BYTES",
	"DocumentMeta",
	"MagicBytesValidator",
	"NoopDocumentPort",
	"S3DocumentPort",
	"UnsupportedMimeError",
]
