"""Tests for canonical audit golden bundle helpers."""

from __future__ import annotations

import argparse
import types
from pathlib import Path

import pytest

from flowforge_audit_pg._golden import (
	GoldenIntegrityError,
	_main,
	_row_from_jsonable,
	build_golden,
	load_golden,
	recompute_row,
	write_golden,
)


def test_build_write_load_and_recompute_golden_bundle(tmp_path: Path) -> None:
	bundle = build_golden()
	assert len(bundle.rows) == 5
	assert bundle.rows[0].prev_sha256 is None
	assert bundle.rows[1].prev_sha256 == bundle.rows[0].row_sha256

	path = write_golden(tmp_path / "canonical.bin", bundle)
	loaded = load_golden(path)

	assert len(loaded.envelope_sha) == 64
	for row in loaded.rows:
		canonical, row_sha = recompute_row(row.prev_sha256, row.input)
		assert canonical == row.canonical_json_bytes
		assert row_sha == row.row_sha256


def test_write_golden_builds_default_bundle(tmp_path: Path) -> None:
	path = write_golden(tmp_path / "nested" / "canonical.bin")
	assert path.exists()
	assert len(load_golden(path).rows) == 5


def test_load_golden_rejects_bad_magic_malformed_and_tampered_payload(tmp_path: Path) -> None:
	bad_magic = tmp_path / "bad-magic.bin"
	bad_magic.write_bytes(b"not-a-bundle")
	with pytest.raises(GoldenIntegrityError, match="missing magic"):
		load_golden(bad_magic)

	malformed = tmp_path / "malformed.bin"
	malformed.write_bytes(b"FFAUDITGOLDEN\x01short")
	with pytest.raises(GoldenIntegrityError, match="malformed"):
		load_golden(malformed)

	tampered = write_golden(tmp_path / "tampered.bin")
	raw = bytearray(tampered.read_bytes())
	raw[-1] ^= 1
	tampered.write_bytes(bytes(raw))
	with pytest.raises(GoldenIntegrityError, match="mismatch"):
		load_golden(tampered)


def test_golden_cli_write_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
	path = tmp_path / "cli.bin"

	assert _main(["write", str(path)]) == 0
	assert "wrote" in capsys.readouterr().out
	assert _main(["verify", str(path)]) == 0
	assert "ok: 5 rows" in capsys.readouterr().out


def test_row_from_jsonable_leaves_invalid_iso_like_strings_unchanged() -> None:
	row = _row_from_jsonable(
		{
			"event_id": "e1",
			"prev_sha256": None,
			"input": {"occurred_at": "2026-05-20Tnot-a-date"},
			"canonical_json_bytes_hex": b"{}".hex(),
			"row_sha256": "0" * 64,
		}
	)
	assert row.input["occurred_at"] == "2026-05-20Tnot-a-date"


def test_golden_main_returns_one_for_unknown_parsed_command(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_parse_args(
		self: argparse.ArgumentParser,
		argv: list[str] | None = None,
	) -> types.SimpleNamespace:
		return types.SimpleNamespace(cmd="unknown")

	monkeypatch.setattr(argparse.ArgumentParser, "parse_args", fake_parse_args)
	assert _main(["unknown"]) == 1
