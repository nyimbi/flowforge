"""NoopDocumentPort — empty-result DocumentPort for hosts without docs."""

from __future__ import annotations

from typing import Any


class NoopDocumentPort:
	"""DocumentPort impl that pretends no documents exist anywhere.

	Useful when a host doesn't ship a document subsystem; the engine
	guard ``documents_complete`` will evaluate to ``False`` so workflows
	that gate on documents stall predictably instead of crashing.
	"""

	async def list_for_subject(
		self,
		subject_id: str,
		kinds: list[str] | None = None,
	) -> list[dict[str, Any]]:
		assert isinstance(subject_id, str) and subject_id, "subject_id required"
		return []

	async def attach(self, subject_id: str, doc_id: str) -> None:
		assert isinstance(subject_id, str) and subject_id, "subject_id required"
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		return None

	async def get_classification(self, doc_id: str) -> str | None:
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		return None

	async def freshness_days(self, doc_id: str) -> int | None:
		assert isinstance(doc_id, str) and doc_id, "doc_id required"
		return None
