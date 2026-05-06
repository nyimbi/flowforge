"""JTBD exporter plugin SDK (E-21).

Defines the :class:`JtbdExporter` Protocol and :class:`ExporterRegistry`
for converting :class:`~flowforge_jtbd.dsl.spec.JtbdSpec` objects to
external formats (BPMN, user-story-map, ARIS, …).

Two reference exporters ship in this package:

- :mod:`.bpmn` — simplified BPMN 2.0 XML (community, optional).
- :mod:`.storymap` — user-story-map JSON format.

Custom exporters register via :func:`register`::

    from flowforge_jtbd.exporters import register, ExporterRegistry
    from my_plugin import ArisExporter

    register(ArisExporter())

    # or with a custom registry:
    registry = ExporterRegistry()
    registry.register(ArisExporter())
    result = registry.export("aris", spec, bundle)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..dsl.spec import JtbdBundle, JtbdSpec


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class JtbdExporter(Protocol):
	"""Convert a :class:`~flowforge_jtbd.dsl.spec.JtbdSpec` to an external format.

	Implementors must carry a stable string ``exporter_id`` (e.g.
	``"bpmn"``, ``"storymap"``) and a ``export`` method that returns the
	converted representation as a plain ``str`` (UTF-8 text regardless of
	whether the target format is XML, JSON, Markdown, etc.).

	Both ``spec`` and ``bundle`` are provided so exporters may draw on
	shared bundle metadata (project name, domain, roles).  Exporters that
	only need the spec may ignore ``bundle``.
	"""

	exporter_id: str

	def export(self, spec: JtbdSpec, bundle: JtbdBundle | None = None) -> str:
		"""Convert *spec* to the external format string.

		:param spec: The JTBD spec to convert.
		:param bundle: Optional enclosing bundle for context.
		:returns: Converted representation as a UTF-8 string.
		"""
		...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ExporterRegistry:
	"""Holds registered :class:`JtbdExporter` implementations.

	The module-level :data:`_default_registry` instance is used by the
	convenience functions :func:`register` and :func:`export`.
	"""

	def __init__(self) -> None:
		self._exporters: dict[str, JtbdExporter] = {}

	def register(self, exporter: JtbdExporter) -> None:
		"""Register *exporter* by its ``exporter_id``.

		Raises :exc:`ValueError` on duplicate ids unless ``overwrite=True``
		is called explicitly (use :meth:`replace` for that).
		"""
		assert isinstance(exporter, JtbdExporter), (
			f"{type(exporter).__name__!r} does not implement the JtbdExporter protocol "
			"(missing exporter_id or export method)"
		)
		eid = exporter.exporter_id
		if eid in self._exporters:
			raise ValueError(
				f"Exporter {eid!r} is already registered. "
				"Use replace() to overwrite."
			)
		self._exporters[eid] = exporter

	def replace(self, exporter: JtbdExporter) -> None:
		"""Register *exporter*, overwriting any existing entry with the same id."""
		assert isinstance(exporter, JtbdExporter)
		self._exporters[exporter.exporter_id] = exporter

	def unregister(self, exporter_id: str) -> None:
		"""Remove an exporter by id. Silently no-ops if not registered."""
		self._exporters.pop(exporter_id, None)

	def get(self, exporter_id: str) -> JtbdExporter | None:
		"""Return the exporter with *exporter_id*, or ``None``."""
		return self._exporters.get(exporter_id)

	def ids(self) -> list[str]:
		"""Return sorted list of registered exporter ids."""
		return sorted(self._exporters.keys())

	def export(
		self,
		exporter_id: str,
		spec: JtbdSpec,
		bundle: JtbdBundle | None = None,
	) -> str:
		"""Look up *exporter_id* and run the export.

		:raises KeyError: if *exporter_id* is not registered.
		"""
		exporter = self._exporters.get(exporter_id)
		if exporter is None:
			raise KeyError(
				f"No exporter registered for {exporter_id!r}. "
				f"Available: {self.ids()}"
			)
		return exporter.export(spec, bundle)


# ---------------------------------------------------------------------------
# Module-level default registry + convenience functions
# ---------------------------------------------------------------------------

_default_registry = ExporterRegistry()


def register(exporter: JtbdExporter) -> None:
	"""Register *exporter* in the default module-level registry."""
	_default_registry.register(exporter)


def export(
	exporter_id: str,
	spec: JtbdSpec,
	bundle: JtbdBundle | None = None,
) -> str:
	"""Export *spec* via the named exporter from the default registry."""
	return _default_registry.export(exporter_id, spec, bundle)


def available_exporters() -> list[str]:
	"""Return sorted ids of exporters registered in the default registry."""
	return _default_registry.ids()


__all__ = [
	"ExporterRegistry",
	"JtbdExporter",
	"available_exporters",
	"export",
	"register",
]
