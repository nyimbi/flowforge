"""Build and validate the PyPI-ready Flowforge package set."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRATEGIC_PACKAGES = (
	"flowforge-core",
	"flowforge-fastapi",
	"flowforge-sqlalchemy",
	"flowforge-tenancy",
	"flowforge-audit-pg",
	"flowforge-outbox-pg",
	"flowforge-rbac-static",
	"flowforge-rbac-spicedb",
	"flowforge-documents-s3",
	"flowforge-money",
	"flowforge-signing-kms",
	"flowforge-notify-multichannel",
	"flowforge-otel",
	"flowforge-cli",
	"flowforge-jtbd",
	"flowforge-jtbd-hub",
)
EXPECTED_ARTIFACTS = len(STRATEGIC_PACKAGES) * 2


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

	for package in STRATEGIC_PACKAGES:
		_run(["uv", "build", "--out-dir", str(dist_dir)], cwd=ROOT / "python" / package)

	artifacts = sorted(dist_dir.glob("*.whl")) + sorted(dist_dir.glob("*.tar.gz"))
	if len(artifacts) != EXPECTED_ARTIFACTS:
		raise SystemExit(
			f"expected {EXPECTED_ARTIFACTS} artifacts for {len(STRATEGIC_PACKAGES)} "
			f"packages, found {len(artifacts)} in {dist_dir}"
		)

	_run(["uv", "run", "--with", "twine", "python", "-m", "twine", "check", *map(str, artifacts)])
	_run(["uv", "venv", str(venv_dir)])
	_run([
		"uv",
		"pip",
		"install",
		"--python",
		str(_python_path(venv_dir)),
		"--find-links",
		str(dist_dir),
		"flowforge-cli",
	])
	_run([str(_console_script_path(venv_dir)), "--help"])
	print(
		f"pypi-build-smoke: passed for {len(STRATEGIC_PACKAGES)} packages "
		f"and {len(artifacts)} artifacts in {dist_dir}",
		flush=True,
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
