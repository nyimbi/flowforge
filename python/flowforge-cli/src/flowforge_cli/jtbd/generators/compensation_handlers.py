"""Per-JTBD saga compensation handler stub.

Emits a ``compensation_handlers.py`` module under
``backend/src/<pkg>/<jtbd_id>/`` that registers stub handlers for every
compensation kind the synthesiser emits on ``compensate`` transitions.

The generator is silent (returns ``None``) when the JTBD declares no
``edge_case.handle == "compensate"`` — that preserves byte-identical
regen for bundles that don't opt into saga compensation.

CONSUMES the bundle paths declared in the fixture-coverage registry —
see :mod:`flowforge_cli.jtbd.generators._fixture_registry`.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedJTBD
from .._types import GeneratedFile


# Bundle paths this generator reads — declared so the fixture-coverage
# audit can confirm at least one example exercises every input field.
CONSUMES: tuple[str, ...] = ("jtbds[].edge_cases", "jtbds[].id")


def _has_compensations(jtbd: NormalizedJTBD) -> bool:
	"""``True`` iff the JTBD has any synthesised ``compensate`` transition."""

	return any(t.get("event") == "compensate" for t in jtbd.transitions)


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile | None:
	"""Emit the compensation-handler stub when compensations are synthesised.

	Returns ``None`` (no file emitted) when the JTBD declares no
	``compensate`` edge case so existing examples regenerate
	byte-identical to the checked-in tree.
	"""

	if not _has_compensations(jtbd):
		return None

	content = render(
		"compensation_handlers.py.j2",
		project=bundle.project,
		jtbd=jtbd,
	)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/{jtbd.module_name}/compensation_handlers.py",
		content=content,
	)
