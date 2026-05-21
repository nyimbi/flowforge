"""Build and validate the PyPI-ready Flowforge package set."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile
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


def _assert_wheels_include_py_typed(
    wheels: list[Path],
    packages: tuple[ShippingPackage, ...],
) -> None:
    wheel_contents: dict[Path, set[str]] = {}
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            wheel_contents[wheel] = set(archive.namelist())

    missing: list[str] = []
    for package in packages:
        marker_path = f"{package.import_package.replace('.', '/')}/py.typed"
        if not any(marker_path in names for names in wheel_contents.values()):
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
    _assert_wheels_include_py_typed(wheels, packages)

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
