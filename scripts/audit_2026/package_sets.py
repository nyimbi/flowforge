"""Shared package-set discovery for audit-2026 release gates."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ShippingPackage:
    """A Python workspace package that is enabled for distribution."""

    directory: str
    import_package: str


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _workspace_python_members() -> tuple[str, ...]:
    root = _load_toml(ROOT / "pyproject.toml")
    return tuple(
        member.removeprefix("python/")
        for member in root["tool"]["uv"]["workspace"]["members"]
        if member.startswith("python/")
    )


def _is_package_enabled(pyproject: dict) -> bool:
    return bool(pyproject.get("tool", {}).get("uv", {}).get("package", True))


def _import_package(pyproject: dict, *, directory: str) -> str:
    try:
        package_path = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
            "packages"
        ][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(
            f"{directory}: shipping package must declare a wheel package"
        ) from exc
    prefix = "src/"
    if not isinstance(package_path, str) or not package_path.startswith(prefix):
        raise SystemExit(
            f"{directory}: unsupported wheel package path {package_path!r}"
        )
    return package_path.removeprefix(prefix).replace("/", ".")


def shipping_packages() -> tuple[ShippingPackage, ...]:
    packages: list[ShippingPackage] = []
    for directory in _workspace_python_members():
        pyproject = _load_toml(ROOT / "python" / directory / "pyproject.toml")
        if not _is_package_enabled(pyproject):
            continue
        packages.append(
            ShippingPackage(
                directory=directory,
                import_package=_import_package(pyproject, directory=directory),
            )
        )
    return tuple(packages)
