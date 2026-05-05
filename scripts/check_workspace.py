#!/usr/bin/env python3
"""Sanity-check that every workspace member has the required boilerplate.

Run from repo root: ``python framework/scripts/check_workspace.py``.
Exit code 0 = all good, 1 = missing files.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PY_PKGS = [
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
	"flowforge-cli",
]

JS_PKGS = [
	"flowforge-types",
	"flowforge-renderer",
	"flowforge-runtime-client",
	"flowforge-step-adapters",
	"flowforge-designer",
]


def _check_py(pkg: str) -> list[str]:
	missing: list[str] = []
	root = REPO / "python" / pkg
	for required in ("pyproject.toml", "README.md", "CHANGELOG.md"):
		if not (root / required).exists():
			missing.append(f"python/{pkg}/{required}")
	return missing


def _check_js(pkg: str) -> list[str]:
	missing: list[str] = []
	root = REPO / "js" / pkg
	for required in ("package.json", "README.md", "CHANGELOG.md"):
		if not (root / required).exists():
			missing.append(f"js/{pkg}/{required}")
	return missing


def main() -> int:
	missing: list[str] = []
	for pkg in PY_PKGS:
		missing.extend(_check_py(pkg))
	for pkg in JS_PKGS:
		missing.extend(_check_js(pkg))

	if missing:
		print("workspace check failed; missing files:")
		for m in missing:
			print(f"  - {m}")
		return 1

	print(f"workspace OK: {len(PY_PKGS)} python pkgs, {len(JS_PKGS)} js pkgs")
	return 0


if __name__ == "__main__":
	sys.exit(main())
