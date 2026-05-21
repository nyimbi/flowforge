"""Fail-closed release check for the first real polish-copy sidecar."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from flowforge_cli.jtbd.overrides import (
    JtbdCopyOverrides,
    ToneProfile,
    build_canonical_strings,
    load_sidecar,
    sidecar_path_for,
    validate_key_against_bundle,
)
from flowforge_cli.commands.polish_copy import _prompt_sha256


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE_REL = Path("examples/insurance_claim/jtbd-bundle.json")
_BUNDLE = _REPO_ROOT / _BUNDLE_REL
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _fail(message: str) -> int:
    print(f"audit-2026-polish-copy-sidecar: {message}", file=sys.stderr)
    return 1


def _load_bundle(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return raw


def _expected_prompt_sha256(
    bundle: dict[str, object],
    tone_profile: ToneProfile,
) -> str:
    return _prompt_sha256(build_canonical_strings(bundle), tone_profile)


def _validate_sidecar(
    sidecar: JtbdCopyOverrides, bundle: dict[str, object]
) -> str | None:
    if not sidecar.strings:
        return "sidecar has no strings; run a real LLM polish-copy authoring pass"
    missing = [
        field
        for field in ("llm_provider", "llm_model", "prompt_sha256")
        if not getattr(sidecar, field)
    ]
    if missing:
        return "sidecar missing LLM audit metadata: " + ", ".join(missing)
    if sidecar.prompt_sha256 is None or not _SHA256_RE.match(sidecar.prompt_sha256):
        return "sidecar prompt_sha256 must be a lowercase 64-character hex digest"
    expected_prompt_sha256 = _expected_prompt_sha256(bundle, sidecar.tone_profile)
    if sidecar.prompt_sha256 != expected_prompt_sha256:
        return (
            "sidecar prompt_sha256 does not match the current bundle and "
            f"tone prompt: expected {expected_prompt_sha256}"
        )
    for key in sidecar.strings:
        err = validate_key_against_bundle(key, bundle)
        if err is not None:
            return err
    return None


def check_sidecar() -> str | None:
    if not _BUNDLE.is_file():
        return f"bundle not found: {_display(_BUNDLE)}"
    sidecar_path = sidecar_path_for(_BUNDLE)
    sidecar = load_sidecar(_BUNDLE)
    if sidecar is None:
        return (
            f"missing {_display(sidecar_path)}; run `uv run flowforge polish-copy --bundle {_display(_BUNDLE)} "
            "--require-llm --commit` with ANTHROPIC_API_KEY or CLAUDE_API_KEY set "
            "and flowforge-cli[llm] installed, or with FLOWFORGE_POLISH_PROVIDER=claude-cli "
            "and a configured Claude CLI"
        )
    err = _validate_sidecar(sidecar, _load_bundle(_BUNDLE))
    if err is not None:
        return err
    return None


def main() -> int:
    err = check_sidecar()
    if err is not None:
        return _fail(err)
    print(f"audit-2026-polish-copy-sidecar: ok ({_display(sidecar_path_for(_BUNDLE))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
