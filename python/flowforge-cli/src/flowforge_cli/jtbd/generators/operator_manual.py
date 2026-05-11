"""Per-JTBD generator: operator-facing MDX manual.

W4b / item 20. Emits ``docs/jtbd/<id>.mdx`` per JTBD — a self-contained
operator manual rendered from the bundle's authored prose (situation +
motivation + outcome + success_criteria), the synthesised state diagram
(via :mod:`flowforge_cli.jtbd.generators.diagram`'s mermaid source), the
form-spec field catalog, the bundle's audit-topic taxonomy, and the
synthesised permission catalog.

Pure markdown + fenced ``mermaid`` blocks — no JSX components are
required, so the output is valid MDX in any MDX 2 / 3 renderer that
treats markdown fences as plain ``<pre><code>``. The MDX file lives at
``docs/jtbd/<id>.mdx`` inside the generated tree; relative paths from
that location:

* ``../../workflows/<id>/diagram.mmd`` — sibling mermaid source.
* ``../../workflows/<id>/form_spec.json`` — sibling form-spec source.
* ``../../frontend/`` — top-level frontend app the JTBD's Step.tsx
  renders into.
* ``../../../screenshots/frontend/Step.<viewport>.png`` — W3 visual-
  regression baselines under the example root (outside ``generated/``).
  The MDX references this path unconditionally as the documented
  convention; renderers show a broken-image fallback if no baseline is
  present (which is the W3-pending state for every example today). The
  generator deliberately does *not* probe the filesystem — that would
  break Principle 1 (determinism non-negotiable) of the v0.3.0
  engineering plan, since the same bundle would emit different bytes
  depending on which host's working tree it ran against.

Determinism guarantees:

* All iterations sort by declared bundle order (success_criteria,
  fields) or by ``normalize`` invariants (audit_topics +
  permissions are already sorted / dedup'd upstream).
* No timestamp, no random ids, no filesystem probe.
* The embedded mermaid source is the same string the W1 generator
  emits to ``workflows/<id>/diagram.mmd``, so the manual and the
  workflow diagram never drift apart on regen.

Two regens against the same bundle produce byte-identical MDX output —
``scripts/check_all.sh`` step 8 (regen-diff) is the gate.
"""

from __future__ import annotations

from .._render import render
from ..normalize import NormalizedBundle, NormalizedField, NormalizedJTBD
from .._types import GeneratedFile
from . import diagram


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].actor_role",
	"jtbds[].audit_topics",
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].kind",
	"jtbds[].fields[].label",
	"jtbds[].fields[].pii",
	"jtbds[].fields[].required",
	"jtbds[].id",
	"jtbds[].motivation",
	"jtbds[].outcome",
	"jtbds[].permissions",
	"jtbds[].situation",
	"jtbds[].success_criteria",
	"jtbds[].title",
	"project.name",
	"project.package",
)


# Permission action → human-readable verb phrase. Permissions are emitted
# by :func:`transforms.derive_permissions` as ``<jtbd_id>.<action>``; the
# trailing segment determines the phrasing. The closed-set actions
# (``read`` / ``submit`` / ``review`` / ``approve`` / ``reject`` /
# ``escalate``) are the only ones the synthesiser ever emits today; the
# fallback path keeps the renderer honest if the synthesiser grows new
# actions later (Principle 1: determinism over correctness — the
# fallback is a stable string, not a runtime check that flakes).
_PERMISSION_VERB: dict[str, str] = {
	"approve": "approve a record that has cleared review",
	"escalate": "escalate a record to the next authority tier",
	"read": "read records owned by this JTBD",
	"reject": "reject a record outright (no compensating workflow)",
	"review": "review a submitted record",
	"submit": "submit a new record into the workflow",
}


# Audit-topic event → human-readable template. :func:`transforms.derive_audit_topics`
# emits topics shaped ``<jtbd_id>.<event>`` where ``<event>`` is one of
# the closed set below, plus ``<edge_id>`` / ``<edge_id>_rejected`` /
# ``<edge_id>_returned`` for declared edge cases. The closed-set keys
# get a canonical phrase; edge-case tails fall through to the
# underscore-to-space fallback in :func:`_audit_topic_summary`.
_AUDIT_TEMPLATE: dict[str, str] = {
	"approved": "Approval event — a reviewer signed off on the record.",
	"escalated": "Escalation event — the record crossed an authority tier and was routed to a senior approver.",
	"submitted": "Submission event — the workflow's initial state was committed.",
}


def _permission_summary(perm: str) -> str:
	"""Return a one-line human-readable summary for *perm*.

	Permissions are shaped ``<jtbd_id>.<action>``; if the action is in
	the closed set above we return the canonical phrase, else we fall
	back to a bare-action rendering. Pure function: same input → same
	output.
	"""

	assert isinstance(perm, str), "perm must be a string"
	_, _, action = perm.rpartition(".")
	if not action:
		# Shared (cross-JTBD) permissions that lack the ``<jtbd>.`` prefix
		# fall here. We can't infer an action; emit a stable bare summary.
		return f"holds the shared permission `{perm}`"
	return _PERMISSION_VERB.get(action, f"perform `{action}` on records for this JTBD")


def _audit_topic_summary(topic: str, jtbd_id: str) -> str:
	"""Return a one-line human-readable summary for an audit *topic*.

	Topics are shaped ``<jtbd_id>.<event>``. The closed-set events get a
	canonical template; edge-case events (``<edge>_rejected`` /
	``<edge>_returned`` / bare ``<edge>``) fall back to a structured
	template with underscores converted to spaces. Pure function: same
	input → same output.
	"""

	assert isinstance(topic, str), "topic must be a string"
	assert isinstance(jtbd_id, str), "jtbd_id must be a string"
	prefix = f"{jtbd_id}."
	tail = topic[len(prefix):] if topic.startswith(prefix) else topic
	canonical = _AUDIT_TEMPLATE.get(tail)
	if canonical is not None:
		return canonical
	# Edge-case topics: ``<edge_id>`` / ``<edge_id>_rejected`` /
	# ``<edge_id>_returned`` per :func:`transforms.derive_audit_topics`.
	if tail.endswith("_rejected"):
		edge = tail[: -len("_rejected")].replace("_", " ")
		return f"Edge-case rejection — the `{edge}` branch terminated the workflow."
	if tail.endswith("_returned"):
		edge = tail[: -len("_returned")].replace("_", " ")
		return f"Loop-back event — the `{edge}` branch returned the record for revision."
	human = tail.replace("_", " ")
	return f"Edge-case branch — the `{human}` route was taken."


def _field_bullet(field: NormalizedField) -> str:
	"""Build the markdown bullet line for one data-capture *field*.

	Pre-built in Python (rather than via inline jinja2 conditionals)
	because :data:`flowforge_cli.jtbd._render._env` configures the
	environment with ``trim_blocks=True``, which silently consumes the
	literal newline after any ``{% endif %}`` placed at end of line.
	Building the line here keeps the template a clean substitution and
	keeps the bullet's optional flag suffixes (`, required`, `, PII`)
	deterministic and easy to unit-test in isolation.
	"""

	parts: list[str] = [
		f"- **{field.label}** (`{field.id}`) — `{field.kind}`",
	]
	if field.required:
		parts.append(", required")
	if field.pii:
		parts.append(", PII")
	return "".join(parts)


def build_mdx(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> str:
	"""Render the operator manual MDX for *jtbd*.

	Pure function — same ``(bundle, jtbd)`` → same bytes. The embedded
	mermaid source is computed via :func:`diagram.build_mmd` so the
	manual and the workflow's ``diagram.mmd`` never drift apart on regen.
	"""

	diagram_mmd = diagram.build_mmd(bundle, jtbd)
	field_bullets = [_field_bullet(f) for f in jtbd.fields]
	audit_lines = [
		(topic, _audit_topic_summary(topic, jtbd.id))
		for topic in jtbd.audit_topics
	]
	permission_lines = [
		(perm, _permission_summary(perm)) for perm in jtbd.permissions
	]
	return render(
		"operator_manual.mdx.j2",
		project=bundle.project,
		bundle=bundle,
		jtbd=jtbd,
		diagram_mmd=diagram_mmd,
		field_bullets=field_bullets,
		audit_lines=audit_lines,
		permission_lines=permission_lines,
	)


def generate(bundle: NormalizedBundle, jtbd: NormalizedJTBD) -> GeneratedFile:
	"""Emit ``docs/jtbd/<id>.mdx`` (operator manual) per JTBD.

	Per-JTBD generator — one file per JTBD. The output is pure markdown
	with fenced mermaid blocks; no JSX components, so any MDX renderer
	that accepts markdown can render the file untouched.
	"""

	content = build_mdx(bundle, jtbd)
	return GeneratedFile(
		path=f"docs/jtbd/{jtbd.id}.mdx",
		content=content,
	)
