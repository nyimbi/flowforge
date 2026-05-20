"""Run 100% statement/branch coverage gates for closed shipping packages."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLOSED_PACKAGE_COVERAGE = (
	("flowforge-tenancy", "flowforge_tenancy"),
	("flowforge-rbac-static", "flowforge_rbac_static"),
	("flowforge-rbac-spicedb", "flowforge_rbac_spicedb"),
	("flowforge-money", "flowforge_money"),
	("flowforge-otel", "flowforge_otel"),
	("flowforge-signing-kms", "flowforge_signing_kms"),
	("flowforge-outbox-pg", "flowforge_outbox_pg"),
)


def main() -> int:
	for package, module in CLOSED_PACKAGE_COVERAGE:
		print(f"closed-package-coverage: {package}", flush=True)
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
			cwd=ROOT / "python" / package,
			check=True,
		)
	print(
		f"closed-package-coverage: passed for {len(CLOSED_PACKAGE_COVERAGE)} packages",
		flush=True,
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
