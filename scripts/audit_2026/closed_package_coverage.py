"""Run 100% statement/branch coverage gates for closed shipping packages."""

from __future__ import annotations

import subprocess
from pathlib import Path

from package_sets import shipping_packages

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    packages = shipping_packages()
    for package in packages:
        package_name = package.directory
        module = package.import_package
        print(f"closed-package-coverage: {package_name}", flush=True)
        subprocess.run(
            [
                "uv",
                "run",
                "pytest",
                "tests",
                "-q",
                f"--cov={module}",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-fail-under=100",
            ],
            cwd=ROOT / "python" / package_name,
            check=True,
        )
    print(
        f"closed-package-coverage: passed for {len(packages)} packages",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
