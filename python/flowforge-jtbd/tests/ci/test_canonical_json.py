"""Canonical-JSON encoder pins down the byte-stable hash contract."""

from __future__ import annotations

import hashlib

import pytest
from flowforge_jtbd.dsl.canonical import (
	CanonicalJsonError,
	canonical_json,
	spec_hash,
)


def test_keys_are_sorted_and_whitespace_omitted() -> None:
	out = canonical_json({"b": 2, "a": 1, "c": [3, 2, 1]})
	assert out == b'{"a":1,"b":2,"c":[3,2,1]}'


def test_nested_keys_sorted_recursively() -> None:
	out = canonical_json(
		{"outer": {"z": 1, "a": {"y": 2, "b": 3}, "m": [1, 2]}}
	)
	assert out == b'{"outer":{"a":{"b":3,"y":2},"m":[1,2],"z":1}}'


def test_unicode_passes_through_without_ascii_escape() -> None:
	# Without ensure_ascii=False this would emit "é" — the
	# canonical form keeps the original UTF-8 byte sequence.
	out = canonical_json({"name": "café"})
	assert out == '{"name":"café"}'.encode("utf-8")


def test_nfc_normalisation_collapses_combining_forms() -> None:
	# "é" composed (U+00E9) and decomposed (U+0065 + U+0301) hash the
	# same after NFC normalisation.
	composed = canonical_json({"x": "é"})
	decomposed = canonical_json({"x": "é"})
	assert composed == decomposed


def test_floats_are_rejected() -> None:
	with pytest.raises(CanonicalJsonError):
		canonical_json({"amount": 1.5})


def test_nan_and_infinity_rejected_explicitly() -> None:
	with pytest.raises(CanonicalJsonError):
		canonical_json({"amount": float("nan")})
	with pytest.raises(CanonicalJsonError):
		canonical_json({"amount": float("inf")})


def test_sets_are_rejected() -> None:
	with pytest.raises(CanonicalJsonError):
		canonical_json({"tags": {"a", "b"}})


def test_non_string_key_rejected() -> None:
	with pytest.raises(CanonicalJsonError):
		canonical_json({1: "value"})


def test_tuple_normalises_to_list() -> None:
	out = canonical_json({"items": (1, 2, 3)})
	assert out == b'{"items":[1,2,3]}'


def test_array_order_preserved() -> None:
	out = canonical_json({"items": [3, 1, 2]})
	assert out == b'{"items":[3,1,2]}'


def test_booleans_and_null_lowercase() -> None:
	out = canonical_json({"a": True, "b": False, "c": None})
	assert out == b'{"a":true,"b":false,"c":null}'


def test_spec_hash_format_and_determinism() -> None:
	body = {
		"id": "claim_intake",
		"version": "1.0.0",
		"actor": {"role": "intake_clerk"},
	}
	h1 = spec_hash(body)
	h2 = spec_hash(body)
	assert h1 == h2
	assert h1.startswith("sha256:")
	digest = h1.split(":", 1)[1]
	assert len(digest) == 64
	assert all(c in "0123456789abcdef" for c in digest)


def test_spec_hash_changes_when_content_changes() -> None:
	a = spec_hash({"id": "claim_intake"})
	b = spec_hash({"id": "claim_intake_2"})
	assert a != b


def test_spec_hash_independent_of_input_key_order() -> None:
	a = spec_hash({"a": 1, "b": 2})
	b = spec_hash({"b": 2, "a": 1})
	assert a == b


def test_spec_hash_known_fixture() -> None:
	# Anchor the canonical JSON output against an explicit byte string
	# so future code paths that touch the encoder cannot drift it
	# silently.
	body = {"id": "claim_intake", "version": "1.0.0"}
	canonical = canonical_json(body)
	assert canonical == b'{"id":"claim_intake","version":"1.0.0"}'
	expected = "sha256:" + hashlib.sha256(canonical).hexdigest()
	assert spec_hash(body) == expected
