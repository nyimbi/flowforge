"""Fixture-registry primer for v0.3.0 W0.

Declares which bundle/normalized fields each generator consumes so the
generator-fixture-coverage test (Pre-mortem Scenario 1 of
:doc:`docs/v0.3.0-engineering-plan` §5) can assert:

* **Forward**: at least one example bundle populates each declared field.
* **Reverse**: every ``bundle.<field>`` / ``jtbd.<field>`` attribute access
  in a generator under ``flowforge_cli/jtbd/generators/`` is declared
  here.

This file is the W0 *primer* — only the W0 generators register here for
now. The full bidirectional AST-walk test lands later (see executor
residual risk #2 in the v0.3.0 engineering plan).

Path grammar:

* ``project.<field>`` — bundle-level project field
* ``jtbds[].<field>`` — repeated per-JTBD field
* ``jtbds[].fields[].<field>`` — repeated field-of-JTBD subfield
* dotted path is matched verbatim against the dataclass attribute path

Adding a new entry: each generator that lands in
:mod:`flowforge_cli.jtbd.generators` MUST also expose a module-level
``CONSUMES: tuple[str, ...]`` re-stating the same paths, so a static
import in the test layer can verify the registry and the generator
agree.
"""

from __future__ import annotations


# Mapping: generator module name → tuple of dotted bundle/JTBD paths consumed.
# Sorted for deterministic iteration in the test layer.
_REGISTRY: dict[str, tuple[str, ...]] = {
	"compensation_handlers": (
		"jtbds[].edge_cases",
		"jtbds[].id",
	),
	"diagram": (
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].sla_breach_seconds",
		"jtbds[].states",
		"jtbds[].title",
		"jtbds[].transitions",
	),
	"frontend": (
		"jtbds[].class_name",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].pii",
		"jtbds[].fields[].required",
		"jtbds[].fields[].validation",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.frontend.form_renderer",
		"project.package",
	),
	"migration_safety": (
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].required",
		"jtbds[].fields[].sa_type",
		"jtbds[].id",
		"jtbds[].initial_state",
		"jtbds[].table_name",
		"jtbds[].title",
		"project.package",
	),
	"openapi": (
		"jtbds[].audit_topics",
		"jtbds[].fields",
		"jtbds[].fields[].id",
		"jtbds[].fields[].kind",
		"jtbds[].fields[].label",
		"jtbds[].fields[].required",
		"jtbds[].fields[].validation",
		"jtbds[].id",
		"jtbds[].permissions",
		"jtbds[].title",
		"jtbds[].url_segment",
		"project.name",
	),
}


def get(generator_name: str) -> tuple[str, ...]:
	"""Return the declared CONSUMES tuple for *generator_name*.

	Returns an empty tuple if the generator hasn't registered yet —
	intentionally permissive while the registry is still primed; the
	W0+ coverage test will harden this into a hard failure once every
	generator declares its CONSUMES.
	"""

	assert isinstance(generator_name, str), "generator_name must be a string"
	return _REGISTRY.get(generator_name, ())


def all_generators() -> tuple[str, ...]:
	"""Return the sorted list of generators registered here."""

	return tuple(sorted(_REGISTRY.keys()))


def register(generator_name: str, consumes: tuple[str, ...]) -> None:
	"""Test-only helper: register a generator's CONSUMES at runtime.

	Production code must declare CONSUMES at module load time. This is
	a hatch for tests that want to validate registry round-trips
	without polluting the global state across processes. Idempotent.
	"""

	assert isinstance(generator_name, str), "generator_name must be a string"
	assert isinstance(consumes, tuple), "consumes must be a tuple"
	_REGISTRY[generator_name] = tuple(sorted(consumes))
