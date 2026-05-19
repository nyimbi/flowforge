"""flowforge-documents-s3 — S3-backed DocumentPort + noop fallback.

Two implementations of :class:`flowforge.ports.DocumentPort`:

* :class:`S3DocumentPortInMemory` — buckets documents in S3 and defaults
  to an in-memory metadata/subject index.
* :class:`SQLiteDocumentIndex` — optional stdlib-SQLite durable index
  usable with ``S3DocumentPortInMemory(index_store=...)`` when hosts need
  metadata and subject attachments to survive process restarts.
* :class:`NoopDocumentPort` — returns empty lists for hosts that have
  no document subsystem.

Both implementations expose magic-bytes validation hooks for upload
validation. ``S3DocumentPortInMemory`` additionally exposes raw blob
``put``/``get``/``list``/``delete`` plus presigned URL helpers
(``presigned_get_url``, ``presigned_put_url``, ``presigned_post`` —
the last carries explicit ``Conditions=[["starts-with","$Content-Type",
…]]`` for hosts that want strict server-side enforcement).

E-52 (audit-fix-plan §7) renames the canonical class. The legacy name
``S3DocumentPort`` remains importable but emits ``DeprecationWarning``
on access.
"""

from __future__ import annotations

import warnings
from typing import Any

from .noop import NoopDocumentPort
from .port import (
	DEFAULT_MAGIC_BYTES,
	DocumentMeta,
	DocumentIndexStore,
	InMemoryDocumentIndex,
	InvalidDocIdError,
	MagicBytesValidator,
	S3DocumentPortInMemory,
	SQLiteDocumentIndex,
	UnsupportedMimeError,
	sniff_filetype,
)


def __getattr__(name: str) -> Any:
	"""Lazy-emit DeprecationWarning when the legacy name is imported."""

	if name == "S3DocumentPort":
		warnings.warn(
			"S3DocumentPort is deprecated; import S3DocumentPortInMemory instead. "
			"The legacy name will be removed in a future release.",
			DeprecationWarning,
			stacklevel=2,
		)
		return S3DocumentPortInMemory
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
	"DEFAULT_MAGIC_BYTES",
	"DocumentMeta",
	"DocumentIndexStore",
	"InMemoryDocumentIndex",
	"InvalidDocIdError",
	"MagicBytesValidator",
	"NoopDocumentPort",
	"S3DocumentPortInMemory",
	"SQLiteDocumentIndex",
	"UnsupportedMimeError",
	"sniff_filetype",
]
