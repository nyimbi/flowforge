"""Shared jinja2 environment for jtbd generators.

Every generator imports :func:`render` and feeds it a template name +
context. Keeping the env factory in one place guarantees identical
whitespace, undefined-handling, and filter sets across templates so the
deterministic snapshot tests stay byte-stable.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _templates_root() -> Path:
	return Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
	env = Environment(
		loader=FileSystemLoader(str(_templates_root())),
		autoescape=False,
		keep_trailing_newline=True,
		undefined=StrictUndefined,
		trim_blocks=True,
		lstrip_blocks=True,
	)
	env.filters["to_json"] = _to_json
	env.filters["py_repr"] = _py_repr
	return env


def _to_json(value: Any, indent: int = 2) -> str:
	return json.dumps(value, indent=indent, sort_keys=True, default=str)


def _py_repr(value: Any) -> str:
	return repr(value)


def render(template: str, **context: Any) -> str:
	"""Render *template* with *context*, returning the result string."""

	return _env().get_template(template).render(**context)
