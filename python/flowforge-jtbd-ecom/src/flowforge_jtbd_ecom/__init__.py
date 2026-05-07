"""flowforge JTBD domain library — E-Commerce.

Subdomains: Catalog, order, fulfillment.

This package follows the audit-2026 domain-pkg ``__init__.py`` standard
(E-51 / D-03): a single ``load_bundle()`` helper exposes the example
bundle that ships under ``examples/bundle.yaml``. Tests, smoke
fixtures, and downstream consumers all go through this entrypoint.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Any


DOMAIN: str = "ecom"
DISPLAY_NAME: str = "E-Commerce"
SUBDOMAINS: str = "Catalog, order, fulfillment"


def load_bundle() -> dict[str, Any]:
	"""Load the shipped ``examples/bundle.yaml`` and return it as a dict.

	The bundle's top-level keys follow the JTBD bundle schema:
	``project``, ``shared``, ``jtbds``. Returns a fresh dict every call —
	mutating the result will not affect subsequent calls.
	"""
	import yaml  # local import keeps base import cheap

	resource = files(__package__) / "examples" / "bundle.yaml"
	with resource.open("rb") as fh:
		data = yaml.safe_load(fh)
	if not isinstance(data, dict):
		raise ValueError(
			f"{__package__}/examples/bundle.yaml did not parse to a dict"
		)
	return data


__all__ = ["DOMAIN", "DISPLAY_NAME", "SUBDOMAINS", "load_bundle"]
