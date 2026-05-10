"""Per-bundle aggregator: ``workflows/reachability_summary.md``.

v0.3.0 W4a / item 4 of :doc:`docs/improvements`. Aggregates each
JTBD's reachability state (count of reachable / unreachable / with
unwritable vars / skipped) into a single bundle-level markdown
artefact. The per-JTBD generator
:mod:`flowforge_cli.jtbd.generators.reachability` produces one
``reachability.json`` (z3 installed) or one ``reachability_skipped.txt``
(z3 not installed) per JTBD; this aggregator surfaces the bundle-wide
view without re-running z3.

Per the engineering plan principle 2 (per-bundle generators must be
aggregations), the summary is one file per bundle, not per JTBD. The
content is byte-identical across regens regardless of whether z3 is
installed because the per-JTBD generator already emits a placeholder
file in the absence of the extra; this aggregator records *which*
artefact landed for each JTBD.

Determinism guarantees:

* JTBDs sorted by ``id`` before listing.
* Section headings fixed; line ordering deterministic.
* No timestamp, no host info.
"""

from __future__ import annotations

from typing import Any

from . import reachability as _reach
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer — same surface as the per-JTBD
# generator; the aggregator reads every per-JTBD ``reachability.json``
# in spirit (we don't reload from disk; we re-derive from the same
# normalized bundle) so the registry mirrors the per-JTBD CONSUMES.
CONSUMES: tuple[str, ...] = (
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].id",
	"jtbds[].initial_state",
	"jtbds[].states",
	"jtbds[].title",
	"jtbds[].transitions",
)


def _z3_available() -> bool:
	"""Return ``True`` when ``z3-solver`` is importable.

	Mirrors the per-JTBD generator's probe so the summary lines up
	with whichever artefact landed (``reachability.json`` vs
	``reachability_skipped.txt``).
	"""

	try:
		import z3  # noqa: F401
	except ImportError:
		return False
	return True


def _row_for_jtbd(jtbd: NormalizedJTBD, z3_ok: bool) -> dict[str, Any]:
	"""Build the summary row for *jtbd*. Pure function."""

	if not z3_ok:
		return {
			"id": jtbd.id,
			"title": jtbd.title,
			"artefact": f"workflows/{jtbd.id}/reachability_skipped.txt",
			"status": "skipped",
			"total": len(jtbd.transitions),
			"reachable": None,
			"unreachable": None,
			"with_unwritable_vars": None,
		}
	report = _reach._build_report(jtbd)
	summary = report["summary"]
	return {
		"id": jtbd.id,
		"title": jtbd.title,
		"artefact": f"workflows/{jtbd.id}/reachability.json",
		"status": "ok" if summary["unreachable"] == 0 and summary["with_unwritable_vars"] == 0 else "warn",
		"total": summary["total"],
		"reachable": summary["reachable"],
		"unreachable": summary["unreachable"],
		"with_unwritable_vars": summary["with_unwritable_vars"],
	}


def _format_cell(value: Any) -> str:
	"""Render a cell value for the markdown table."""

	if value is None:
		return "—"
	return str(value)


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	"""Emit one ``workflows/reachability_summary.md`` per bundle."""

	z3_ok = _z3_available()
	rows = [_row_for_jtbd(jt, z3_ok) for jt in sorted(bundle.jtbds, key=lambda j: j.id)]

	lines: list[str] = []
	lines.append("# Reachability summary")
	lines.append("")
	lines.append(f"Bundle: `{bundle.project.package}`")
	lines.append("")
	if z3_ok:
		lines.append(
			"`z3-solver` is installed; per-JTBD reports live at "
			"`workflows/<id>/reachability.json`."
		)
	else:
		lines.append(
			"`z3-solver` is **not installed** — install with "
			"`pip install 'flowforge-cli[reachability]'` to populate the "
			"per-JTBD reports. The per-JTBD placeholder files live at "
			"`workflows/<id>/reachability_skipped.txt`."
		)
	lines.append("")
	lines.append("| JTBD | Title | Status | Total | Reachable | Unreachable | Unwritable vars | Artefact |")
	lines.append("|------|-------|--------|-------|-----------|-------------|-----------------|----------|")
	for row in rows:
		lines.append(
			"| `{id}` | {title} | {status} | {total} | {reachable} | {unreachable} | {unwritable} | `{artefact}` |".format(
				id=row["id"],
				title=row["title"],
				status=row["status"],
				total=_format_cell(row["total"]),
				reachable=_format_cell(row["reachable"]),
				unreachable=_format_cell(row["unreachable"]),
				unwritable=_format_cell(row["with_unwritable_vars"]),
				artefact=row["artefact"],
			)
		)
	lines.append("")

	return GeneratedFile(
		path="workflows/reachability_summary.md",
		content="\n".join(lines) + "\n",
	)
