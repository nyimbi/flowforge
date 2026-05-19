"""Translation sidecar loading for JTBD generation.

The canonical JTBD bundle intentionally stays free of authored
translations. Hosts that want populated non-default catalogs place
closed-key JSON files beside the bundle under ``i18n/<lang>.json``;
``jtbd-generate`` merges those values into the generated catalogs.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_i18n_sidecars(
	bundle_path: Path,
	*,
	declared_languages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict[str, str]]:
	"""Load ``<bundle-dir>/i18n/*.json`` as ``{lang: {key: value}}``.

	Missing directories mean "no translations". Values must be strings;
	unknown keys are checked later by the generator after it has built the
	closed English keyset. When *declared_languages* is provided, sidecar
	filenames must match the bundle's declared language tags exactly.
	"""

	assert bundle_path is not None
	sidecar_dir = bundle_path.parent / "i18n"
	if not sidecar_dir.is_dir():
		return {}
	catalogs: dict[str, dict[str, str]] = {}
	for path in sorted(sidecar_dir.glob("*.json")):
		raw = json.loads(path.read_text(encoding="utf-8"))
		if not isinstance(raw, dict):
			raise ValueError(f"{path}: expected a JSON object")
		catalog: dict[str, str] = {}
		for key, value in raw.items():
			if not isinstance(key, str):
				raise ValueError(f"{path}: translation key must be a string")
			if not isinstance(value, str):
				raise ValueError(f"{path}: translation value for {key!r} must be a string")
			catalog[key] = value
		catalogs[path.stem] = catalog
	if declared_languages is not None:
		declared = set(declared_languages)
		extra = sorted(set(catalogs) - declared)
		if extra:
			raise ValueError(
				"undeclared i18n sidecar locale(s): "
				+ ", ".join(extra)
				+ ". Add the locale to project.languages or rename the sidecar."
			)
	return catalogs


__all__ = ["load_i18n_sidecars"]
