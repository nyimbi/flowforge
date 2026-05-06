"""Project-level llm.txt generator (E-29).

Per ``framework/docs/flowforge-evolution.md`` §13 + ``jtbd-editor-arch
.md`` §11.2. Reads a JTBD bundle and renders a project-tailored
``llm.txt`` from the Jinja2 template at
``flowforge_cli/templates/llm.txt.jinja``.

Pure function so the CLI subcommand and the ``flowforge new
--emit-llmtxt`` flag share the same rendering path. Time stamps use
the caller-supplied ``now`` clock to keep the output deterministic in
tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_TEMPLATE_NAME = "llm.txt.jinja"


def _template_root() -> Path:
	return Path(__file__).resolve().parent / "templates"


def _jinja_env() -> Environment:
	return Environment(
		loader=FileSystemLoader(str(_template_root())),
		autoescape=False,
		keep_trailing_newline=True,
		undefined=StrictUndefined,
	)


def render_llmtxt(
	bundle: dict[str, Any],
	*,
	bundle_path: str | Path = "workflows/jtbd_bundle.json",
	now: Callable[[], datetime] | None = None,
) -> str:
	"""Render a project ``llm.txt`` from *bundle*.

	*bundle* must be a JTBD bundle dict (already-loaded JSON / YAML);
	the renderer never reads from disk so callers can synthesise
	bundles in tests without temporary files.

	*bundle_path* is recorded in the rendered text as the human-
	readable provenance pointer; pass the relative path the user will
	see in their checkout.

	*now* lets tests pin the timestamp; production callers should leave
	it at the default UTC clock.
	"""
	assert bundle is not None, "bundle must not be None"
	assert "project" in bundle, "bundle.project is required"
	project = bundle.get("project") or {}
	assert project.get("name"), "bundle.project.name is required"
	assert project.get("package"), "bundle.project.package is required"

	clock = now or (lambda: datetime.now(tz=timezone.utc))
	generated_at = clock().strftime("%Y-%m-%d %H:%M:%S")

	env = _jinja_env()
	template = env.get_template(_TEMPLATE_NAME)
	return template.render(
		project=project,
		jtbds=bundle.get("jtbds") or [],
		shared=bundle.get("shared") or {},
		bundle_path=str(bundle_path),
		generated_at=generated_at,
	)


def write_llmtxt(
	bundle: dict[str, Any],
	*,
	out_path: Path,
	bundle_path: str | Path = "workflows/jtbd_bundle.json",
	now: Callable[[], datetime] | None = None,
) -> Path:
	"""Render and write the file. Returns the resolved output path."""
	text = render_llmtxt(bundle, bundle_path=bundle_path, now=now)
	out_path.parent.mkdir(parents=True, exist_ok=True)
	out_path.write_text(text, encoding="utf-8")
	return out_path


__all__ = ["render_llmtxt", "write_llmtxt"]
