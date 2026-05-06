"""LocaleCatalog + LocaleRegistry.

A catalog is one flat ``dict[str, str]`` for one language. The registry
holds many catalogs keyed by language code and resolves keys with a
fallback chain (``fr → en`` by default).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Mapping


# Default canonical languages per arch §9.4. Hosts may register
# arbitrary locales beyond this set.
DEFAULT_LANGUAGES: tuple[str, ...] = (
	"en", "fr", "es", "sw", "ar", "zh", "ja", "pt",
)


def _validate_lang(lang: str) -> str:
	assert lang, "lang must be a non-empty string"
	stripped = lang.strip()
	assert stripped, "lang must be non-empty after stripping"
	return stripped


@dataclass
class LocaleCatalog:
	"""One language's translation table.

	Stored as a flat dict keyed by ``<jtbd_id>.<jcr_path>``. Mutating
	helpers (:meth:`register`, :meth:`merge`) keep the lang and the
	entries in sync; the catalog never auto-derives or auto-translates.
	"""

	lang: str
	entries: dict[str, str] = field(default_factory=dict)

	def __post_init__(self) -> None:
		self.lang = _validate_lang(self.lang)
		# Defensive copy so callers cannot mutate after construction.
		self.entries = dict(self.entries)

	def __contains__(self, key: str) -> bool:
		return key in self.entries

	def __len__(self) -> int:
		return len(self.entries)

	def get(self, key: str, *, default: str | None = None) -> str | None:
		assert key, "key must be a non-empty string"
		return self.entries.get(key, default)

	def has(self, key: str) -> bool:
		return key in self.entries

	def keys(self) -> Iterator[str]:
		return iter(self.entries)

	def register(self, key: str, value: str) -> None:
		assert key, "key must be a non-empty string"
		assert value is not None, "value must not be None"
		self.entries[key] = value

	def merge(self, other: Mapping[str, str]) -> None:
		"""Merge *other* into this catalog. Existing keys are
		overwritten; new keys are added.
		"""
		for key, value in other.items():
			if not isinstance(key, str) or not key:
				raise ValueError(f"merge key must be a non-empty string; got {key!r}")
			if not isinstance(value, str):
				raise ValueError(f"merge value must be a string; got {type(value).__name__}")
			self.entries[key] = value

	def filter_by_jtbd(self, jtbd_id: str) -> dict[str, str]:
		"""Return the subset of entries scoped to *jtbd_id*."""
		assert jtbd_id, "jtbd_id must be non-empty"
		prefix = jtbd_id + "."
		return {
			key: value
			for key, value in self.entries.items()
			if key == jtbd_id or key.startswith(prefix)
		}


@dataclass
class LocaleRegistry:
	"""Multi-language registry with fallback chain.

	Hosts construct one registry per process and call
	:meth:`register_catalog` once per shipped language. Lookups use the
	requested language first; if the key is missing, the registry walks
	the configured fallback chain (defaults to ``["en"]``).
	"""

	default_lang: str = "en"
	fallback_chain: tuple[str, ...] = ("en",)
	catalogs: dict[str, LocaleCatalog] = field(default_factory=dict)

	def __post_init__(self) -> None:
		self.default_lang = _validate_lang(self.default_lang)

	def register_catalog(
		self,
		lang: str,
		entries: Mapping[str, str] | LocaleCatalog,
	) -> LocaleCatalog:
		"""Register or replace the catalog for *lang*."""
		lang = _validate_lang(lang)
		if isinstance(entries, LocaleCatalog):
			# Defensive: trust the lang on the catalog and ignore the
			# argument when both are present (consistency).
			catalog = LocaleCatalog(lang=lang, entries=dict(entries.entries))
		else:
			catalog = LocaleCatalog(lang=lang, entries=dict(entries))
		self.catalogs[lang] = catalog
		return catalog

	def has(self, lang: str) -> bool:
		return lang in self.catalogs

	def get(
		self,
		key: str,
		*,
		lang: str | None = None,
		fallback: bool = True,
	) -> str | None:
		"""Resolve *key* in *lang*, walking the fallback chain on miss.

		Returns ``None`` if the key is unknown in every consulted
		catalog. Callers wanting a guaranteed string should use
		:meth:`get_or_key`.
		"""
		assert key, "key must be a non-empty string"
		lang = _validate_lang(lang or self.default_lang)
		for candidate in self._lookup_order(lang, fallback):
			catalog = self.catalogs.get(candidate)
			if catalog is not None and key in catalog:
				return catalog.get(key)
		return None

	def get_or_key(
		self,
		key: str,
		*,
		lang: str | None = None,
		fallback: bool = True,
	) -> str:
		"""Like :meth:`get`, but returns *key* itself when unresolved.

		Useful for the editor surface — an untranslated label still
		renders something meaningful instead of an empty string.
		"""
		resolved = self.get(key, lang=lang, fallback=fallback)
		return resolved if resolved is not None else key

	def languages(self) -> tuple[str, ...]:
		return tuple(sorted(self.catalogs))

	def _lookup_order(self, lang: str, fallback: bool) -> list[str]:
		order = [lang]
		if not fallback:
			return order
		for fb in self.fallback_chain:
			if fb not in order:
				order.append(fb)
		return order


__all__ = ["DEFAULT_LANGUAGES", "LocaleCatalog", "LocaleRegistry"]
