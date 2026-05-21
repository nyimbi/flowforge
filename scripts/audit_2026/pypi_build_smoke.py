"""Build and validate the PyPI-ready Flowforge package set."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path

from package_sets import shipping_packages
from package_sets import ShippingPackage

ROOT = Path(__file__).resolve().parents[2]


def _run(argv: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(argv), flush=True)
    subprocess.run(argv, cwd=cwd, check=True)


def _prepare_dir(path: Path, *, purpose: str) -> None:
    resolved = path.resolve()
    tmp_root = Path(tempfile.gettempdir()).resolve()
    if resolved.exists():
        if tmp_root not in (resolved, *resolved.parents):
            raise SystemExit(f"{purpose} must be under {tmp_root}: {resolved}")
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


def _wheel_distribution_key(wheel: Path) -> str:
    return _distribution_key(wheel.name.split("-", 1)[0])


def _sdist_distribution_key(sdist: Path) -> str:
    suffix = ".tar.gz"
    if not sdist.name.endswith(suffix):
        raise SystemExit(f"unsupported sdist artifact name: {sdist}")
    return _distribution_key(sdist.name[: -len(suffix)].rsplit("-", 1)[0])


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
) -> dict[str, Path]:
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
    return {key: wheel_groups[key][0] for key in expected}


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
    wheels_by_distribution = _assert_exact_artifacts_by_package(
        wheels,
        sdists,
        packages,
    )
    _assert_wheels_include_py_typed(wheels_by_distribution, packages)

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
    _run(["uv", "venv", str(venv_dir)])
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(_python_path(venv_dir)),
            "--find-links",
            str(dist_dir),
            "flowforge-cli",
        ]
    )
    _run([str(_console_script_path(venv_dir)), "--help"])
    print(
        f"pypi-build-smoke: passed for {len(packages)} packages "
        f"and {len(artifacts)} artifacts in {dist_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
