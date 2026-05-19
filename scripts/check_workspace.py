#!/usr/bin/env python3
"""Sanity-check that workspace members are registered and classified.

Run from repo root: ``python scripts/check_workspace.py``.
Exit code 0 = all good, 1 = missing files.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PythonMember:
	name: str
	path: Path
	package_enabled: bool


@dataclass(frozen=True)
class JsMember:
	name: str
	path: Path
	private: bool


def _load_toml(path: Path) -> dict:
	with path.open("rb") as fh:
		return tomllib.load(fh)


def python_members() -> list[PythonMember]:
	root = _load_toml(REPO / "pyproject.toml")
	members = root["tool"]["uv"]["workspace"]["members"]
	out: list[PythonMember] = []
	for member in members:
		path = REPO / member
		if not member.startswith("python/"):
			continue
		data = _load_toml(path / "pyproject.toml")
		name = str(data["project"]["name"])
		package_enabled = bool(data.get("tool", {}).get("uv", {}).get("package", True))
		out.append(PythonMember(name=name, path=path, package_enabled=package_enabled))
	return sorted(out, key=lambda m: m.name)


def js_workspace_names() -> list[str]:
	"""Read the simple package list from pnpm-workspace.yaml.

	The file is intentionally a tiny package list. Keeping this parser
	narrow avoids adding a YAML dependency to the gate.
	"""

	names: list[str] = []
	in_packages = False
	for raw in (REPO / "js" / "pnpm-workspace.yaml").read_text().splitlines():
		line = raw.strip()
		if line == "packages:":
			in_packages = True
			continue
		if in_packages and line and not line.startswith("-"):
			break
		if in_packages and line.startswith("-"):
			names.append(line.removeprefix("-").strip().strip('"').strip("'"))
	return names


def js_members() -> list[JsMember]:
	out: list[JsMember] = []
	for rel in js_workspace_names():
		path = REPO / "js" / rel
		data = json.loads((path / "package.json").read_text())
		out.append(
			JsMember(
				name=str(data["name"]),
				path=path,
				private=bool(data.get("private", False)),
			)
		)
	return sorted(out, key=lambda m: m.name)


def _check_py(member: PythonMember) -> list[str]:
	missing: list[str] = []
	for required in ("pyproject.toml", "src", "tests"):
		if not (member.path / required).exists():
			missing.append(str(member.path.relative_to(REPO) / required))
	if member.package_enabled:
		for required in ("README.md", "CHANGELOG.md"):
			if not (member.path / required).exists():
				missing.append(str(member.path.relative_to(REPO) / required))
	return missing


def _check_js(member: JsMember) -> list[str]:
	missing: list[str] = []
	for required in ("package.json",):
		if not (member.path / required).exists():
			missing.append(str(member.path.relative_to(REPO) / required))
	if not member.private:
		for required in ("README.md", "CHANGELOG.md"):
			if not (member.path / required).exists():
				missing.append(str(member.path.relative_to(REPO) / required))
	return missing


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--list-python", action="store_true")
	parser.add_argument("--list-js", action="store_true")
	args = parser.parse_args(argv)

	py = python_members()
	js = js_members()

	if args.list_python:
		for member in py:
			print(member.path.name)
		return 0
	if args.list_js:
		for member in js:
			print(member.path.name)
		return 0

	missing: list[str] = []
	for member in py:
		missing.extend(_check_py(member))
	for member in js:
		missing.extend(_check_js(member))

	if missing:
		print("workspace check failed; missing files:")
		for item in missing:
			print(f"  - {item}")
		return 1

	shipping_py = sum(1 for member in py if member.package_enabled)
	starter_py = len(py) - shipping_py
	private_js = sum(1 for member in js if member.private)
	print(
		"workspace OK: "
		f"{len(py)} python pkgs ({shipping_py} shipping, {starter_py} starter), "
		f"{len(js)} js pkgs ({private_js} private)"
	)
	return 0


if __name__ == "__main__":
	sys.exit(main())
