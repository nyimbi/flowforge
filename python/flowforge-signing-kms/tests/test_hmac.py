"""Tests for HmacDevSigning — local-dev HMAC-SHA256 backend."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from flowforge_signing_kms import hmac_dev as hmac_dev_module
from flowforge_signing_kms.hmac_dev import HmacDevSigning


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def run(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# basic sign / verify
# ---------------------------------------------------------------------------


def test_hmac_public_validation_does_not_use_optimized_out_asserts() -> None:
    source = inspect.getsource(hmac_dev_module)
    assert "assert " not in source
    assert "flowforge-dev-secret-not-for-production" not in source


def test_sign_returns_bytes():
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    sig = run(signer.sign_payload(b"hello"))
    assert isinstance(sig, bytes)
    assert len(sig) == 32  # SHA-256 digest is 32 bytes


def test_verify_valid_signature():
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    payload = b"some workflow payload"
    sig = run(signer.sign_payload(payload))
    assert run(signer.verify(payload, sig, "k1")) is True


def test_verify_wrong_payload_fails():
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    sig = run(signer.sign_payload(b"original"))
    assert run(signer.verify(b"tampered", sig, "k1")) is False


def test_verify_unknown_key_id_raises():
    """SK-02: verifying with a key_id the signer does not know raises ``UnknownKeyId``.

    Distinct from "wrong signature" so callers can audit the configuration error
    separately from a tampered payload.
    """
    from flowforge_signing_kms.errors import UnknownKeyId

    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    sig = run(signer.sign_payload(b"payload"))
    with pytest.raises(UnknownKeyId):
        run(signer.verify(b"payload", sig, "k2"))


def test_verify_wrong_secret_fails():
    signer_a = HmacDevSigning(secret="secret-a", key_id="k1")
    signer_b = HmacDevSigning(secret="secret-b", key_id="k1")
    sig = run(signer_a.sign_payload(b"payload"))
    assert run(signer_b.verify(b"payload", sig, "k1")) is False


def test_verify_truncated_signature_fails():
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    sig = run(signer.sign_payload(b"payload"))
    assert run(signer.verify(b"payload", sig[:16], "k1")) is False


def test_sign_payload_rejects_non_bytes() -> None:
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    with pytest.raises(TypeError, match="payload must be bytes"):
        run(signer.sign_payload("payload"))  # type: ignore[arg-type]


def test_verify_rejects_invalid_argument_shapes() -> None:
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    sig = run(signer.sign_payload(b"payload"))

    with pytest.raises(TypeError, match="payload must be bytes"):
        run(signer.verify("payload", sig, "k1"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="signature must be bytes"):
        run(signer.verify(b"payload", "sig", "k1"))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="key_id must be a non-empty str"):
        run(signer.verify(b"payload", sig, ""))


def test_bytearray_payloads_remain_supported() -> None:
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    payload: Any = bytearray(b"payload")
    sig = run(signer.sign_payload(payload))
    signature: Any = bytearray(sig)
    assert run(signer.verify(payload, signature, "k1")) is True


# ---------------------------------------------------------------------------
# current_key_id
# ---------------------------------------------------------------------------


def test_current_key_id_explicit():
    signer = HmacDevSigning(secret="s3cr3t", key_id="my-key-42")
    assert signer.current_key_id() == "my-key-42"


def test_current_key_id_deterministic():
    signer = HmacDevSigning(secret="s3cr3t", key_id="k1")
    assert signer.current_key_id() == signer.current_key_id()


# ---------------------------------------------------------------------------
# env-var defaults
# ---------------------------------------------------------------------------


def test_env_secret_used_when_no_arg(monkeypatch):
    monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "env-secret")
    monkeypatch.setenv("FLOWFORGE_SIGNING_KEY_ID", "env-key")
    signer = HmacDevSigning()
    assert signer.current_key_id() == "env-key"
    sig = run(signer.sign_payload(b"data"))
    assert run(signer.verify(b"data", sig, "env-key")) is True


def test_env_secret_uses_default_key_id_when_key_env_missing(monkeypatch):
    monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "env-secret")
    monkeypatch.delenv("FLOWFORGE_SIGNING_KEY_ID", raising=False)
    signer = HmacDevSigning()
    assert signer.current_key_id() == "dev-key-1"


def test_no_env_no_arg_raises_runtime_error(monkeypatch):
    """SK-01: instantiating without secret material raises ``RuntimeError``.

    Operators must either pass ``secret=``, set ``FLOWFORGE_SIGNING_SECRET``,
    or use the explicit key-map form.
    """
    monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("FLOWFORGE_SIGNING_KEY_ID", raising=False)
    monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)
    with pytest.raises(RuntimeError, match="explicit secret required"):
        HmacDevSigning()


def test_empty_single_key_material_is_rejected(monkeypatch) -> None:
    monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("FLOWFORGE_SIGNING_KEY_ID", raising=False)

    with pytest.raises(ValueError, match="resolved secret"):
        HmacDevSigning(secret="", key_id="k1")
    with pytest.raises(ValueError, match="resolved key_id"):
        HmacDevSigning(secret="secret", key_id="")


def test_insecure_default_flag_does_not_enable_hardcoded_secret(monkeypatch):
    monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("FLOWFORGE_SIGNING_KEY_ID", raising=False)
    monkeypatch.setenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", "1")

    with pytest.raises(RuntimeError, match="explicit secret required"):
        HmacDevSigning()


def test_explicit_secret_uses_env_key_id_when_key_id_missing(monkeypatch):
    monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
    monkeypatch.setenv("FLOWFORGE_SIGNING_KEY_ID", "dev-env-key")
    monkeypatch.setenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", "1")
    signer = HmacDevSigning(secret="explicit-secret")
    assert signer.current_key_id() == "dev-env-key"


# ---------------------------------------------------------------------------
# key rotation simulation
# ---------------------------------------------------------------------------


def test_signature_from_old_key_verifiable_via_key_map():
    """SK-02: rotation via key map keeps the old key id valid for verification.

    Sign with v1, rotate to v2 (carrying both keys in the map), verify the v1
    signature against v1 — succeeds.
    """
    v1 = HmacDevSigning(keys={"key-v1": "secret-v1"}, current_key_id="key-v1")
    rotated = HmacDevSigning(
        keys={"key-v1": "secret-v1", "key-v2": "secret-v2"},
        current_key_id="key-v2",
    )

    payload = b"important document hash"
    sig_v1 = run(v1.sign_payload(payload))

    assert run(rotated.verify(payload, sig_v1, "key-v1")) is True


def test_key_map_rejects_empty_or_missing_current_key() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        HmacDevSigning(keys={}, current_key_id="k1")
    with pytest.raises(ValueError, match="current_key_id="):
        HmacDevSigning(keys={"k1": "secret"})
    with pytest.raises(ValueError, match="not in keys"):
        HmacDevSigning(keys={"k1": "secret"}, current_key_id="k2")


def test_key_map_rejects_invalid_shapes() -> None:
    with pytest.raises(TypeError, match="keys must be dict"):
        HmacDevSigning(keys=[("k1", "secret")], current_key_id="k1")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="entries"):
        HmacDevSigning(keys={"k1": b"secret"}, current_key_id="k1")  # type: ignore[dict-item]


def test_constructor_rejects_mixed_single_key_and_key_map_forms() -> None:
    with pytest.raises(ValueError, match="pass either"):
        HmacDevSigning(
            secret="secret", key_id="k1", keys={"k1": "secret"}, current_key_id="k1"
        )


def test_known_key_ids_are_sorted() -> None:
    signer = HmacDevSigning(
        keys={"key-b": "secret-b", "key-a": "secret-a"},
        current_key_id="key-b",
    )
    assert signer.known_key_ids() == ["key-a", "key-b"]


def test_new_signatures_isolated_per_key_id():
    """SK-02: each key id has its own secret; cross-key verifies fail correctly.

    A signature produced under ``key-v2`` does not verify under ``key-v1``
    (both because the key_id is bound into the HMAC input AND because the
    secrets are distinct entries in the key map).
    """
    signer = HmacDevSigning(
        keys={"key-v1": "secret-v1", "key-v2": "secret-v2"},
        current_key_id="key-v2",
    )
    payload = b"payload"
    sig_v2 = run(signer.sign_payload(payload))
    assert run(signer.verify(payload, sig_v2, "key-v2")) is True
    assert run(signer.verify(payload, sig_v2, "key-v1")) is False


# ---------------------------------------------------------------------------
# protocol compliance
# ---------------------------------------------------------------------------


def test_satisfies_signing_port_protocol():
    """HmacDevSigning must satisfy the runtime_checkable SigningPort Protocol."""
    from flowforge.ports.signing import SigningPort

    signer = HmacDevSigning(secret="s", key_id="k")
    assert isinstance(signer, SigningPort)
