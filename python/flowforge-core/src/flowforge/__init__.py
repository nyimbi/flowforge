"""flowforge — portable workflow framework core.

Public API surface (see ``docs/workflow-framework-portability.md``).
"""

from __future__ import annotations

from .version import __version__
from . import config

__all__ = ["__version__", "config"]
