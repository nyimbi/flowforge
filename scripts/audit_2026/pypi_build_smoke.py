"""Build and validate the PyPI-ready Flowforge package set."""

from __future__ import annotations

import argparse
import email.message
import email.parser
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from collections.abc import Mapping
from pathlib import Path

from package_sets import shipping_packages
from package_sets import ShippingPackage

ROOT = Path(__file__).resolve().parents[2]
INTERNAL_DEPENDENCY_LOWER_BOUND = ">=0.1.0"
INTERNAL_DEPENDENCY_UPPER_BOUND = "<0.2.0"


def _run(argv: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(argv), flush=True)
    subprocess.run(argv, cwd=cwd, check=True)


def _prepare_dir(path: Path, *, purpose: str) -> None:
    resolved = path.resolve()
    tmp_root = Path(tempfile.gettempdir()).resolve()
    if tmp_root not in (resolved, *resolved.parents):
        raise SystemExit(f"{purpose} must be under {tmp_root}: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _console_script_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "flowforge.exe"
    return venv_dir / "bin" / "flowforge"


def _python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _distribution_key(name: str) -> str:
    """Normalize a distribution name the way wheel/sdist filenames do."""

    return re.sub(r"[-_.]+", "-", name).lower()


def _workspace_distribution_keys() -> frozenset[str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        root = tomllib.load(handle)
    names: set[str] = set()
    for member in root["tool"]["uv"]["workspace"]["members"]:
        if not member.startswith("python/"):
            continue
        pyproject = tomllib.loads((ROOT / member / "pyproject.toml").read_text())
        names.add(_distribution_key(pyproject["project"]["name"]))
    return frozenset(names)


def _shipping_distribution_keys(
    packages: tuple[ShippingPackage, ...],
) -> frozenset[str]:
    return frozenset(
        _distribution_key(package.distribution_name) for package in packages
    )


def _wheel_distribution_key(wheel: Path) -> str:
    return _distribution_key(wheel.name.split("-", 1)[0])


def _sdist_distribution_key(sdist: Path) -> str:
    suffix = ".tar.gz"
    if not sdist.name.endswith(suffix):
        raise SystemExit(f"unsupported sdist artifact name: {sdist}")
    return _distribution_key(sdist.name[: -len(suffix)].rsplit("-", 1)[0])


def _wheel_metadata_path(wheel: Path, wheel_names: set[str]) -> str:
    metadata_files = [
        name for name in wheel_names if name.endswith(".dist-info/METADATA")
    ]
    if len(metadata_files) != 1:
        raise SystemExit(
            f"{wheel.name}: expected exactly one wheel METADATA file, "
            f"found {len(metadata_files)}"
        )
    metadata_path = metadata_files[0]
    metadata_dir = metadata_path.rsplit("/", 1)[0]
    metadata_distribution = metadata_dir.removesuffix(".dist-info").rsplit("-", 1)[0]
    wheel_distribution = _wheel_distribution_key(wheel)
    if _distribution_key(metadata_distribution) != wheel_distribution:
        raise SystemExit(
            f"{wheel.name}: wheel METADATA distribution {metadata_distribution!r} "
            f"does not match wheel filename distribution {wheel_distribution!r}"
        )
    return metadata_path


def _group_by_distribution(
    artifacts: list[Path],
    *,
    kind: str,
) -> dict[str, list[Path]]:
    key_fn = _wheel_distribution_key if kind == "wheel" else _sdist_distribution_key
    grouped: dict[str, list[Path]] = {}
    for artifact in artifacts:
        grouped.setdefault(key_fn(artifact), []).append(artifact)
    return grouped


def _assert_exact_artifacts_by_package(
    wheels: list[Path],
    sdists: list[Path],
    packages: tuple[ShippingPackage, ...],
) -> tuple[dict[str, Path], dict[str, Path]]:
    expected = {
        _distribution_key(package.distribution_name): package for package in packages
    }
    wheel_groups = _group_by_distribution(wheels, kind="wheel")
    sdist_groups = _group_by_distribution(sdists, kind="sdist")
    issues: list[str] = []
    for key, package in expected.items():
        package_wheels = wheel_groups.get(key, [])
        package_sdists = sdist_groups.get(key, [])
        if len(package_wheels) != 1:
            issues.append(
                f"{package.distribution_name}: expected 1 wheel, "
                f"found {len(package_wheels)}"
            )
        if len(package_sdists) != 1:
            issues.append(
                f"{package.distribution_name}: expected 1 sdist, "
                f"found {len(package_sdists)}"
            )
    unexpected_wheels = sorted(set(wheel_groups) - set(expected))
    unexpected_sdists = sorted(set(sdist_groups) - set(expected))
    if unexpected_wheels:
        issues.append(
            f"unexpected wheel distribution(s): {', '.join(unexpected_wheels)}"
        )
    if unexpected_sdists:
        issues.append(
            f"unexpected sdist distribution(s): {', '.join(unexpected_sdists)}"
        )
    if issues:
        raise SystemExit(
            "built artifacts do not match the shipping package set:\n  "
            + "\n  ".join(issues)
        )
    return (
        {key: wheel_groups[key][0] for key in expected},
        {key: sdist_groups[key][0] for key in expected},
    )


def _assert_wheels_include_py_typed(
    wheels_by_distribution: Mapping[str, Path],
    packages: tuple[ShippingPackage, ...],
) -> None:
    wheel_contents: dict[Path, set[str]] = {}
    for wheel in wheels_by_distribution.values():
        with zipfile.ZipFile(wheel) as archive:
            wheel_contents[wheel] = set(archive.namelist())

    missing: list[str] = []
    for package in packages:
        wheel = wheels_by_distribution[_distribution_key(package.distribution_name)]
        marker_path = f"{package.import_package.replace('.', '/')}/py.typed"
        if marker_path not in wheel_contents[wheel]:
            missing.append(f"{package.directory}: {marker_path}")
    if missing:
        raise SystemExit(
            "built wheels are missing PEP 561 typing markers:\n  "
            + "\n  ".join(missing)
        )


def _assert_artifacts_include_license_files(
    wheels_by_distribution: Mapping[str, Path],
    sdists_by_distribution: Mapping[str, Path],
    packages: tuple[ShippingPackage, ...],
) -> None:
    missing: list[str] = []
    for package in packages:
        key = _distribution_key(package.distribution_name)
        wheel = wheels_by_distribution[key]
        with zipfile.ZipFile(wheel) as archive:
            wheel_names = set(archive.namelist())
        metadata_path = _wheel_metadata_path(wheel, wheel_names)
        wheel_license_path = f"{metadata_path.rsplit('/', 1)[0]}/licenses/LICENSE"
        if wheel_license_path not in wheel_names:
            missing.append(f"{package.directory}: wheel LICENSE")

        sdist = sdists_by_distribution[key]
        with tarfile.open(sdist) as archive:
            sdist_names = set(archive.getnames())
        sdist_root = sdist.name.removesuffix(".tar.gz")
        if f"{sdist_root}/LICENSE" not in sdist_names:
            missing.append(f"{package.directory}: sdist LICENSE")

    if missing:
        raise SystemExit(
            "built artifacts are missing declared license files:\n  "
            + "\n  ".join(missing)
        )


def _wheel_metadata(wheel: Path) -> email.message.Message:
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        metadata_path = _wheel_metadata_path(wheel, wheel_names)
        metadata = archive.read(metadata_path).decode("utf-8")
    return email.parser.Parser().parsestr(metadata)


def _sdist_metadata(sdist: Path) -> email.message.Message:
    with tarfile.open(sdist) as archive:
        sdist_root = sdist.name.removesuffix(".tar.gz")
        metadata_path = f"{sdist_root}/PKG-INFO"
        if metadata_path not in archive.getnames():
            raise SystemExit(
                f"{sdist.name}: expected top-level sdist PKG-INFO at {metadata_path}"
            )
        member = archive.extractfile(metadata_path)
        if member is None:
            raise SystemExit(f"{sdist.name}: could not read sdist PKG-INFO")
        metadata = member.read().decode("utf-8")
    return email.parser.Parser().parsestr(metadata)


def _wheel_requires_dist(wheel: Path) -> list[str]:
    return list(_wheel_metadata(wheel).get_all("Requires-Dist", []) or [])


def _sdist_requires_dist(sdist: Path) -> list[str]:
    return list(_sdist_metadata(sdist).get_all("Requires-Dist", []) or [])


def _assert_artifact_metadata_names(
    wheels_by_distribution: Mapping[str, Path],
    sdists_by_distribution: Mapping[str, Path],
    packages: tuple[ShippingPackage, ...],
) -> None:
    issues: list[str] = []
    for package in packages:
        key = _distribution_key(package.distribution_name)
        wheel_name = _wheel_metadata(wheels_by_distribution[key]).get("Name", "")
        if _distribution_key(wheel_name) != key:
            issues.append(
                f"{package.directory}: wheel METADATA Name {wheel_name!r} "
                f"does not match {package.distribution_name!r}"
            )
        sdist_name = _sdist_metadata(sdists_by_distribution[key]).get("Name", "")
        if _distribution_key(sdist_name) != key:
            issues.append(
                f"{package.directory}: sdist PKG-INFO Name {sdist_name!r} "
                f"does not match {package.distribution_name!r}"
            )
    if issues:
        raise SystemExit(
            "built artifact metadata names do not match the shipping package set:\n  "
            + "\n  ".join(issues)
        )


def _requirement_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    return _distribution_key(match.group(1)) if match else ""


def _requirement_specifiers(requirement: str) -> frozenset[str]:
    requirement_without_marker = requirement.split(";", 1)[0].strip()
    name_match = re.match(r"\s*[A-Za-z0-9_.-]+", requirement_without_marker)
    if not name_match:
        return frozenset()
    specifiers = requirement_without_marker[name_match.end() :].strip()
    if specifiers.startswith("["):
        extras_end = specifiers.find("]")
        if extras_end == -1:
            return frozenset()
        specifiers = specifiers[extras_end + 1 :].strip()
    return frozenset(
        normalized
        for specifier in specifiers.split(",")
        if (normalized := re.sub(r"\s+", "", specifier.strip()))
    )


def _has_required_internal_dependency_bounds(requirement: str) -> bool:
    specifiers = _requirement_specifiers(requirement)
    return specifiers == frozenset(
        {INTERNAL_DEPENDENCY_LOWER_BOUND, INTERNAL_DEPENDENCY_UPPER_BOUND}
    )


def _assert_artifact_internal_dependencies_bounded(
    wheels_by_distribution: Mapping[str, Path],
    sdists_by_distribution: Mapping[str, Path],
    *,
    internal_distribution_keys: frozenset[str],
    shipping_distribution_keys: frozenset[str],
) -> None:
    unbounded: list[str] = []
    unpublished: list[str] = []
    for distribution_key, wheel in wheels_by_distribution.items():
        for requirement in _wheel_requires_dist(wheel):
            name = _requirement_name(requirement)
            if name not in internal_distribution_keys:
                continue
            if name not in shipping_distribution_keys:
                unpublished.append(f"{distribution_key} wheel: {requirement}")
            if not _has_required_internal_dependency_bounds(requirement):
                unbounded.append(f"{distribution_key} wheel: {requirement}")
    for distribution_key, sdist in sdists_by_distribution.items():
        for requirement in _sdist_requires_dist(sdist):
            name = _requirement_name(requirement)
            if name not in internal_distribution_keys:
                continue
            if name not in shipping_distribution_keys:
                unpublished.append(f"{distribution_key} sdist: {requirement}")
            if not _has_required_internal_dependency_bounds(requirement):
                unbounded.append(f"{distribution_key} sdist: {requirement}")
    issues: list[str] = []
    if unpublished:
        issues.append(
            "unpublished internal Flowforge dependencies:\n  "
            + "\n  ".join(unpublished)
        )
    if unbounded:
        issues.append(
            "unbounded internal Flowforge dependencies:\n  " + "\n  ".join(unbounded)
        )
    if issues:
        raise SystemExit(
            "built artifacts publish invalid dependencies:\n" + "\n".join(issues)
        )


def _shipping_import_check_code(packages: tuple[ShippingPackage, ...]) -> str:
    modules = sorted(package.import_package for package in packages)
    return (
        "import importlib\n"
        f"modules = {modules!r}\n"
        "for module in modules:\n"
        "    importlib.import_module(module)\n"
        "print(f'imported {len(modules)} shipping packages')\n"
    )


def _assert_clean_venv_installs_shipping_packages(
    packages: tuple[ShippingPackage, ...],
    *,
    venv_dir: Path,
    wheels_by_distribution: Mapping[str, Path],
) -> None:
    wheel_paths = [
        str(wheels_by_distribution[_distribution_key(package.distribution_name)])
        for package in packages
    ]
    _run(["uv", "venv", str(venv_dir)])
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(_python_path(venv_dir)),
            *wheel_paths,
        ]
    )
    _run([str(_python_path(venv_dir)), "-c", _shipping_import_check_code(packages)])
    _run([str(_console_script_path(venv_dir)), "--help"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "flowforge-pypi-readiness-dist",
        help="Temporary directory for built wheel/sdist artifacts.",
    )
    parser.add_argument(
        "--venv-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "flowforge-cli-wheel-smoke",
        help="Temporary virtualenv used for the flowforge-cli wheel smoke.",
    )
    args = parser.parse_args(argv)

    dist_dir = args.dist_dir.resolve()
    venv_dir = args.venv_dir.resolve()
    _prepare_dir(dist_dir, purpose="dist-dir")
    _prepare_dir(venv_dir, purpose="venv-dir")

    packages = shipping_packages()
    expected_artifacts = len(packages) * 2
    for package in packages:
        _run(
            ["uv", "build", "--out-dir", str(dist_dir)],
            cwd=ROOT / "python" / package.directory,
        )

    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    artifacts = wheels + sdists
    if len(artifacts) != expected_artifacts:
        raise SystemExit(
            f"expected {expected_artifacts} artifacts for {len(packages)} "
            f"packages, found {len(artifacts)} in {dist_dir}"
        )
    if len(wheels) != len(packages) or len(sdists) != len(packages):
        raise SystemExit(
            f"expected {len(packages)} wheels and {len(packages)} sdists, "
            f"found {len(wheels)} wheels and {len(sdists)} sdists in {dist_dir}"
        )
    wheels_by_distribution, sdists_by_distribution = _assert_exact_artifacts_by_package(
        wheels,
        sdists,
        packages,
    )
    _assert_artifact_metadata_names(
        wheels_by_distribution,
        sdists_by_distribution,
        packages,
    )
    _assert_wheels_include_py_typed(wheels_by_distribution, packages)
    _assert_artifacts_include_license_files(
        wheels_by_distribution,
        sdists_by_distribution,
        packages,
    )
    _assert_artifact_internal_dependencies_bounded(
        wheels_by_distribution,
        sdists_by_distribution,
        internal_distribution_keys=_workspace_distribution_keys(),
        shipping_distribution_keys=_shipping_distribution_keys(packages),
    )

    _run(
        [
            "uv",
            "run",
            "--with",
            "twine",
            "python",
            "-m",
            "twine",
            "check",
            *map(str, artifacts),
        ]
    )
    _assert_clean_venv_installs_shipping_packages(
        packages,
        venv_dir=venv_dir,
        wheels_by_distribution=wheels_by_distribution,
    )
    print(
        f"pypi-build-smoke: passed for {len(packages)} packages "
        f"and {len(artifacts)} artifacts in {dist_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
