"""Verify that the PyPI artifact checksum manifest matches dist artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from package_sets import shipping_packages


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIST_DIR = ROOT / "dist"
DEFAULT_MANIFEST = (
    ROOT / "docs" / "audit-2026" / "external-release-pypi-artifacts-current.json"
)


def _artifact_kind(path: Path) -> str:
    if path.name.endswith(".tar.gz"):
        return "sdist"
    if path.name.endswith(".whl"):
        return "wheel"
    raise SystemExit(f"unsupported PyPI artifact type: {path}")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _artifact_entry(path: Path) -> dict[str, object]:
    return {
        "filename": path.name,
        "kind": _artifact_kind(path),
        "path": _display_path(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"artifact manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"artifact manifest is not valid JSON: {path}") from exc
    if not isinstance(manifest, dict):
        raise SystemExit(f"artifact manifest must be a JSON object: {path}")
    return manifest


def _manifest_artifacts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise SystemExit("artifact manifest must contain an artifacts list")
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            raise SystemExit(f"artifact manifest entry {index} must be an object")
        normalized.append(entry)
    return normalized


def _expected_release_artifact_count() -> int:
    return len(shipping_packages()) * 2


def verify_manifest(
    *,
    dist_dir: Path,
    manifest_path: Path,
    expected_artifact_count: int | None = None,
) -> None:
    if expected_artifact_count is None:
        expected_artifact_count = _expected_release_artifact_count()
    manifest = _load_manifest(manifest_path)
    if manifest.get("schema_version") != 1:
        raise SystemExit("artifact manifest schema_version must be 1")

    artifacts = sorted(
        [*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")],
        key=lambda item: item.name,
    )
    actual_by_name = {
        artifact.name: _artifact_entry(artifact) for artifact in artifacts
    }
    manifest_entries = _manifest_artifacts(manifest)
    manifest_by_name: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for entry in manifest_entries:
        filename = entry.get("filename")
        if not isinstance(filename, str) or not filename:
            raise SystemExit("artifact manifest entry missing filename")
        if filename in manifest_by_name:
            duplicates.append(filename)
        manifest_by_name[filename] = entry
    if duplicates:
        raise SystemExit(
            "artifact manifest has duplicate filename entries: "
            + ", ".join(sorted(set(duplicates)))
        )

    expected_count = manifest.get("artifact_count")
    if expected_count != len(manifest_entries):
        raise SystemExit(
            "artifact manifest artifact_count does not match artifacts list: "
            f"{expected_count!r} != {len(manifest_entries)}"
        )
    if expected_count != expected_artifact_count:
        raise SystemExit(
            "artifact manifest artifact_count does not match shipping package set: "
            f"{expected_count!r} != {expected_artifact_count}"
        )
    if expected_count != len(actual_by_name):
        raise SystemExit(
            "artifact manifest artifact_count does not match dist artifacts: "
            f"{expected_count!r} != {len(actual_by_name)}"
        )

    missing = sorted(set(actual_by_name) - set(manifest_by_name))
    stale = sorted(set(manifest_by_name) - set(actual_by_name))
    issues: list[str] = []
    if missing:
        issues.append("missing from manifest: " + ", ".join(missing))
    if stale:
        issues.append("stale manifest entries: " + ", ".join(stale))

    comparable_fields = ("kind", "path", "sha256", "size_bytes")
    for filename, actual in actual_by_name.items():
        manifest_entry = manifest_by_name.get(filename)
        if manifest_entry is None:
            continue
        for field in comparable_fields:
            if manifest_entry.get(field) != actual[field]:
                issues.append(
                    f"{filename}: {field} mismatch "
                    f"{manifest_entry.get(field)!r} != {actual[field]!r}"
                )

    if issues:
        raise SystemExit(
            "artifact manifest does not match dist artifacts:\n  " + "\n  ".join(issues)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)

    verify_manifest(
        dist_dir=args.dist_dir.resolve(),
        manifest_path=args.manifest.resolve(),
    )
    print(
        f"pypi-artifact-manifest: verified {args.manifest} against {args.dist_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
