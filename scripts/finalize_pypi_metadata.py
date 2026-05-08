"""One-shot script: stamp PyPI-publishable metadata onto every strategic
flowforge-* package.

Adds the missing PEP 621 fields that twine / PyPI care about:
  - license = { file = "LICENSE" }
  - authors = [{ name = "Nyimbi Odero, Datacraft", email = ... }]
  - keywords (per-package)
  - classifiers (shared baseline + per-package extras)
  - [project.urls] (homepage, repository, issues, changelog)
  - license-files (PEP 639) so the LICENSE ships in the wheel

Idempotent: running twice produces no diff (looks for the marker
``# pypi-metadata-stamped``).

Usage::

    uv run python framework/scripts/finalize_pypi_metadata.py
    # validate by running `uv build` per pkg
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]


# 15 strategic / shipping packages.  The 30 jtbd-* domain libraries are
# not stamped here — they ship as starter scaffolds (E-48a) and don't
# go to PyPI in this iteration.
STRATEGIC_PACKAGES = [
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
	"flowforge-jtbd",
	"flowforge-jtbd-hub",
]


# Per-package keyword + classifier extras. Baseline classifiers are
# defined in ``_BASELINE_CLASSIFIERS`` below and shared across every
# strategic package.
_PER_PKG_KEYWORDS: dict[str, list[str]] = {
	"flowforge-core": ["workflow", "engine", "dsl", "state-machine", "audit-trail"],
	"flowforge-fastapi": ["workflow", "fastapi", "websocket", "starlette"],
	"flowforge-sqlalchemy": ["workflow", "sqlalchemy", "alembic", "snapshot-store"],
	"flowforge-tenancy": ["workflow", "multi-tenant", "row-level-security", "postgresql"],
	"flowforge-audit-pg": ["workflow", "audit-trail", "hash-chain", "soc2", "hipaa", "postgresql"],
	"flowforge-outbox-pg": ["workflow", "transactional-outbox", "postgresql", "asyncpg"],
	"flowforge-rbac-static": ["workflow", "rbac", "authorization", "yaml-config"],
	"flowforge-rbac-spicedb": ["workflow", "rbac", "spicedb", "zanzibar"],
	"flowforge-documents-s3": ["workflow", "documents", "s3", "presigned-urls"],
	"flowforge-money": ["workflow", "money", "decimal", "currency", "fx"],
	"flowforge-signing-kms": ["workflow", "kms", "hmac", "aws-kms", "gcp-kms", "signing"],
	"flowforge-notify-multichannel": ["workflow", "notifications", "smtp", "twilio", "fcm", "webhook", "slack"],
	"flowforge-cli": ["workflow", "cli", "typer", "scaffolding"],
	"flowforge-jtbd": ["workflow", "jtbd", "jobs-to-be-done", "lockfile", "ai", "lint"],
	"flowforge-jtbd-hub": ["workflow", "jtbd", "registry", "package-hub", "trust"],
}

_BASELINE_CLASSIFIERS: list[str] = [
	"Development Status :: 4 - Beta",
	"Intended Audience :: Developers",
	"Intended Audience :: Information Technology",
	"License :: OSI Approved :: Apache Software License",
	"Operating System :: OS Independent",
	"Programming Language :: Python",
	"Programming Language :: Python :: 3",
	"Programming Language :: Python :: 3.11",
	"Programming Language :: Python :: 3.12",
	"Programming Language :: Python :: 3.13",
	"Topic :: Software Development :: Libraries",
	"Topic :: Software Development :: Libraries :: Python Modules",
	"Topic :: System :: Distributed Computing",
	"Framework :: AsyncIO",
	"Framework :: FastAPI",
	"Framework :: Pydantic",
	"Framework :: Pydantic :: 2",
	"Typing :: Typed",
]


_AUTHORS_BLOCK = (
	'authors = [{ name = "Nyimbi Odero, Datacraft", email = "nyimbi@gmail.com" }]\n'
	'maintainers = [{ name = "Nyimbi Odero, Datacraft", email = "nyimbi@gmail.com" }]\n'
)

_LICENSE_BLOCK = 'license = "Apache-2.0"\nlicense-files = ["LICENSE", "../../LICENSE"]\n'

_REPO_URL = "https://github.com/nyimbi/ums"
_PROJECT_URLS = textwrap.dedent(
	f"""\
	[project.urls]
	Homepage = "{_REPO_URL}"
	Documentation = "{_REPO_URL}/tree/main/framework/docs"
	Repository = "{_REPO_URL}"
	Issues = "{_REPO_URL}/issues"
	Changelog = "{_REPO_URL}/blob/main/framework/CHANGELOG.md"
	"""
)

_MARKER = "# pypi-metadata-stamped"


def _stamp_pyproject(path: Path, pkg_name: str) -> bool:
	"""Stamp PEP 621 PyPI metadata onto *path*. Return True if modified."""

	text = path.read_text(encoding="utf-8")
	if _MARKER in text:
		return False

	# Build the additions block. We insert immediately after `description = ...`
	# inside the `[project]` table so the order is sensible (PEP 621 ordering
	# isn't enforced but human-readability is).
	keywords = _PER_PKG_KEYWORDS.get(pkg_name, ["workflow"])
	keywords_toml = ", ".join(f'"{k}"' for k in keywords)
	classifiers_toml = ",\n".join(f'\t"{c}"' for c in _BASELINE_CLASSIFIERS)

	block = (
		_LICENSE_BLOCK
		+ _AUTHORS_BLOCK
		+ f'keywords = [{keywords_toml}]\n'
		+ "classifiers = [\n"
		+ classifiers_toml
		+ ",\n]\n"
	)

	# Find insertion point: end of [project] table.  Strategy: locate the
	# `[project.optional-dependencies]` or next `[` block, insert just before
	# it. Fallback: append after `dependencies = [...]`.
	import re

	# Insert block right after `description = ...` line.
	description_re = re.compile(r'^description\s*=\s*"[^"]*"$', re.MULTILINE)
	m = description_re.search(text)
	if not m:
		print(f"  WARN: {pkg_name}: no description= line; skipping", file=sys.stderr)
		return False

	insertion = block + _MARKER + "\n"
	new_text = text[: m.end()] + "\n" + insertion + text[m.end() :]

	# Append [project.urls] just before the [build-system] table for
	# locality (PEP 621 allows it anywhere in [project]; we keep the
	# `[project.urls]` table separate for readability).
	build_system_re = re.compile(r"^\[build-system\]", re.MULTILINE)
	bm = build_system_re.search(new_text)
	if bm is None:
		# No build-system; append at end.
		new_text = new_text.rstrip() + "\n\n" + _PROJECT_URLS
	else:
		new_text = (
			new_text[: bm.start()]
			+ _PROJECT_URLS
			+ "\n"
			+ new_text[bm.start() :]
		)

	path.write_text(new_text, encoding="utf-8")
	return True


def main() -> int:
	updated = 0
	skipped = 0
	missing: list[str] = []
	for pkg in STRATEGIC_PACKAGES:
		path = FRAMEWORK_ROOT / "python" / pkg / "pyproject.toml"
		if not path.exists():
			missing.append(pkg)
			continue
		if _stamp_pyproject(path, pkg):
			updated += 1
			print(f"  stamped: {pkg}")
		else:
			skipped += 1
			print(f"  skipped (already stamped): {pkg}")

	if missing:
		print(f"\nMISSING pyprojects ({len(missing)}): {missing}", file=sys.stderr)
		return 2

	print(f"\nfinalize_pypi_metadata: stamped {updated}, skipped {skipped} (already done).")
	return 0


if __name__ == "__main__":
	sys.exit(main())
