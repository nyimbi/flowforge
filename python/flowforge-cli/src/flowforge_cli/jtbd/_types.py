"""Tiny module that owns :class:`GeneratedFile`.

Lives in its own file so generator submodules can import it without
pulling in the pipeline (which would create a circular import).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedFile:
	"""One generated artefact: relative path + textual contents."""

	path: str
	content: str
