"""DocumentPort — list/attach/classify documents on subjects."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DocumentPort(Protocol):
	"""Document subsystem facade.

	Hosts that don't have a document subsystem use the noop impl which
	returns empty lists; engine guard ``documents_complete`` evaluates
	to false.
	"""

	async def list_for_subject(
		self,
		subject_id: str,
		kinds: list[str] | None = None,
	) -> list[dict[str, Any]]:
		"""Return doc descriptors for *subject_id*, optionally filtered by kind."""
		...

	async def attach(self, subject_id: str, doc_id: str) -> None:
		"""Attach an existing document row to *subject_id*."""

	async def get_classification(self, doc_id: str) -> str | None:
		"""Return the document's PII classification (e.g., ``confidential``)."""
		...

	async def freshness_days(self, doc_id: str) -> int | None:
		"""Return the document's age in days; ``None`` if unknown."""
		...
