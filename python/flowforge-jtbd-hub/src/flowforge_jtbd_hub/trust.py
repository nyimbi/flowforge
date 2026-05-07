"""Trust-file resolution for ``flowforge jtbd install`` (per arch §11.16).

The CLI / hub server consults the same lookup chain so a package that
verifies on the server also verifies on the client (modulo whatever
extra keys the client trusts on top of the hub-curated set).

Resolution order:

1. Explicit path passed to :func:`resolve_trust_config` (CLI ``--trust-file``).
2. ``FLOWFORGE_TRUST_FILE`` env var.
3. ``~/.flowforge/trust.yaml`` (per-user).
4. ``/etc/flowforge/trust.yaml`` (system).
5. ``[tool.flowforge.trust]`` table in a ``pyproject.toml`` (project-level).
6. Built-in default (empty trust set, ``verified_publishers_only=False``).

The first source to return a valid config wins. Missing files do NOT
raise — they fall through to the next lookup. Invalid YAML / mistyped
fields raise :class:`TrustConfigError` so the caller can surface the
mistake instead of silently trusting nothing.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TrustConfigError(ValueError):
	"""Raised when a discovered trust file is malformed."""


class TrustedKey(BaseModel):
	"""One trusted signing key entry."""

	model_config = ConfigDict(extra="forbid")

	id: str
	name: str | None = None


class TrustConfig(BaseModel):
	"""User-configurable trust state for package installs."""

	model_config = ConfigDict(extra="forbid")

	trusted_signing_keys: list[TrustedKey] = Field(default_factory=list)
	verified_publishers_only: bool = False
	"""When True, install refuses any package without the ``verified``
	hub-badge regardless of whether the signing key is trusted."""

	trust_verified_badge: bool = False
	"""When True, hub-curated ``verified`` keys are trusted implicitly
	(in addition to ``trusted_signing_keys``)."""

	verified_signing_keys: list[TrustedKey] = Field(default_factory=list)
	"""Hub-curated keys whose packages get the ``verified`` badge.
	Populated by the hub at config-load time when reading the canonical
	trust file shipped with the deployment."""

	def trusted_key_ids(self) -> list[str]:
		"""Return the flat list of key ids the caller trusts."""
		ids: list[str] = [k.id for k in self.trusted_signing_keys]
		if self.trust_verified_badge:
			ids.extend(k.id for k in self.verified_signing_keys)
		return ids

	def is_key_trusted(self, key_id: str | None) -> bool:
		if key_id is None:
			return False
		return key_id in self.trusted_key_ids()


@dataclass
class TrustResolution:
	"""Where a config came from + the resolved value."""

	config: TrustConfig
	source: str
	"""Human-readable origin: ``"flag"`` / ``"env"`` / ``"~/.flowforge"`` /
	``"/etc/flowforge"`` / ``"pyproject"`` / ``"default"``."""

	probed: list[str] = field(default_factory=list)
	"""Every path the resolver consulted (in order). Useful for the CLI's
	``--explain-trust`` flag."""


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


# E-58 / JH-05: cross-platform path resolution via platformdirs.
# On Linux this still maps to ``~/.config/flowforge/trust.yaml`` and
# ``/etc/xdg/flowforge/trust.yaml``-equivalent locations; on macOS it's
# ``~/Library/Application Support/flowforge/trust.yaml`` and
# ``/Library/Application Support/flowforge/trust.yaml``; on Windows it
# resolves under ``%APPDATA%`` / ``%PROGRAMDATA%`` as expected.
_USER_TRUST_PATH = (
	Path(platformdirs.user_config_dir("flowforge", appauthor=False)) / "trust.yaml"
)
_SYSTEM_TRUST_PATH = (
	Path(platformdirs.site_config_dir("flowforge", appauthor=False)) / "trust.yaml"
)


def resolve_trust_config(
	*,
	flag_path: str | os.PathLike[str] | None = None,
	env: Mapping[str, str] | None = None,
	user_path: str | os.PathLike[str] | None = None,
	system_path: str | os.PathLike[str] | None = None,
	pyproject_path: str | os.PathLike[str] | None = None,
) -> TrustResolution:
	"""Resolve a :class:`TrustConfig` along the §11.16 lookup chain.

	Each source is parsed only when reached; missing files fall through
	to the next source. Malformed files raise :class:`TrustConfigError`.

	Tests pass explicit paths to keep the resolver hermetic; production
	leaves them ``None`` and the function reads the OS-level defaults.
	"""

	env_map: Mapping[str, str] = env if env is not None else os.environ
	user = Path(user_path) if user_path is not None else _USER_TRUST_PATH
	system = Path(system_path) if system_path is not None else _SYSTEM_TRUST_PATH
	pyproject = Path(pyproject_path) if pyproject_path is not None else None
	probed: list[str] = []

	# 1. Explicit flag path.
	if flag_path is not None:
		path = Path(flag_path)
		probed.append(str(path))
		if path.is_file():
			return TrustResolution(
				config=_load_yaml_trust(path),
				source="flag",
				probed=probed,
			)
		raise TrustConfigError(
			f"--trust-file path does not exist: {path}"
		)

	# 2. Environment variable.
	env_value = env_map.get("FLOWFORGE_TRUST_FILE")
	if env_value:
		env_path = Path(env_value)
		probed.append(str(env_path))
		if env_path.is_file():
			return TrustResolution(
				config=_load_yaml_trust(env_path),
				source="env",
				probed=probed,
			)
		raise TrustConfigError(
			f"FLOWFORGE_TRUST_FILE points at a missing file: {env_path}"
		)

	# 3. Per-user trust.
	probed.append(str(user))
	if user.is_file():
		return TrustResolution(
			config=_load_yaml_trust(user),
			source=str(user),
			probed=probed,
		)

	# 4. System-level trust.
	probed.append(str(system))
	if system.is_file():
		return TrustResolution(
			config=_load_yaml_trust(system),
			source=str(system),
			probed=probed,
		)

	# 5. pyproject.toml table.
	if pyproject is not None:
		probed.append(str(pyproject))
		if pyproject.is_file():
			cfg = _load_pyproject_trust(pyproject)
			if cfg is not None:
				return TrustResolution(
					config=cfg,
					source=str(pyproject),
					probed=probed,
				)

	# 6. Built-in default.
	return TrustResolution(
		config=TrustConfig(),
		source="default",
		probed=probed,
	)


def _load_yaml_trust(path: Path) -> TrustConfig:
	try:
		raw = yaml.safe_load(path.read_text("utf-8")) or {}
	except yaml.YAMLError as exc:
		raise TrustConfigError(f"invalid YAML in {path}: {exc}") from exc
	if not isinstance(raw, dict):
		raise TrustConfigError(f"trust file {path} must be a mapping")
	try:
		return TrustConfig.model_validate(raw)
	except ValidationError as exc:
		# E-58 / JH-06: narrowed from bare ``except Exception`` so that
		# OOM, KeyboardInterrupt, and unrelated bugs propagate instead
		# of being re-wrapped as a (misleading) TrustConfigError.
		raise TrustConfigError(f"invalid trust config in {path}: {exc}") from exc


def _load_pyproject_trust(path: Path) -> TrustConfig | None:
	with path.open("rb") as fh:
		data = tomllib.load(fh)
	tool = data.get("tool", {})
	flowforge = tool.get("flowforge", {}) if isinstance(tool, dict) else {}
	trust = flowforge.get("trust") if isinstance(flowforge, dict) else None
	if not trust:
		return None
	if not isinstance(trust, dict):
		raise TrustConfigError(
			f"[tool.flowforge.trust] in {path} must be a table"
		)
	try:
		return TrustConfig.model_validate(trust)
	except ValidationError as exc:
		# E-58 / JH-06: narrowed from bare ``except Exception``.
		raise TrustConfigError(
			f"invalid trust config in {path} [tool.flowforge.trust]: {exc}"
		) from exc


def merge_trusted_keys(
	*configs: TrustConfig,
) -> TrustConfig:
	"""Union the trusted-key sets across multiple configs.

	Useful for tools that want to combine the hub-side curated set
	(``verified_signing_keys``) with the local user trust file.
	"""
	keys: dict[str, TrustedKey] = {}
	verified: dict[str, TrustedKey] = {}
	verified_only = False
	trust_badge = False
	for cfg in configs:
		for k in cfg.trusted_signing_keys:
			keys[k.id] = k
		for k in cfg.verified_signing_keys:
			verified[k.id] = k
		if cfg.verified_publishers_only:
			verified_only = True
		if cfg.trust_verified_badge:
			trust_badge = True
	return TrustConfig(
		trusted_signing_keys=list(keys.values()),
		verified_signing_keys=list(verified.values()),
		verified_publishers_only=verified_only,
		trust_verified_badge=trust_badge,
	)


def trust_set_from_keys(keys: Iterable[str]) -> TrustConfig:
	"""Convenience builder used by tests."""
	return TrustConfig(
		trusted_signing_keys=[TrustedKey(id=k) for k in keys],
	)


__all__ = [
	"TrustConfig",
	"TrustConfigError",
	"TrustResolution",
	"TrustedKey",
	"merge_trusted_keys",
	"resolve_trust_config",
	"trust_set_from_keys",
]
