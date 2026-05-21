"""Trust resolver lookup-chain tests."""

from __future__ import annotations

import pytest
from flowforge_jtbd_hub.trust import (
	TrustConfig,
	TrustConfigError,
	TrustedKey,
	merge_trusted_keys,
	resolve_trust_config,
	trust_set_from_keys,
)


def _write_yaml(path, body: str) -> None:  # type: ignore[no-untyped-def]
	path.write_text(body, "utf-8")


def test_default_when_no_sources_match(tmp_path) -> None:  # type: ignore[no-untyped-def]
	resolution = resolve_trust_config(
		flag_path=None,
		env={},
		user_path=tmp_path / "missing-user.yaml",
		system_path=tmp_path / "missing-system.yaml",
	)
	assert resolution.source == "default"
	assert resolution.config.trusted_signing_keys == []


def test_flag_path_wins_over_other_sources(tmp_path) -> None:  # type: ignore[no-untyped-def]
	flag = tmp_path / "trust-flag.yaml"
	_write_yaml(
		flag,
		"trusted_signing_keys:\n  - id: kms:flag-key\n    name: from-flag\n",
	)
	user = tmp_path / "user.yaml"
	_write_yaml(
		user,
		"trusted_signing_keys:\n  - id: kms:user-key\n",
	)
	resolution = resolve_trust_config(
		flag_path=flag,
		env={"FLOWFORGE_TRUST_FILE": str(user)},
		user_path=user,
	)
	assert resolution.source == "flag"
	ids = [k.id for k in resolution.config.trusted_signing_keys]
	assert ids == ["kms:flag-key"]


def test_env_path_wins_over_user_and_system(tmp_path) -> None:  # type: ignore[no-untyped-def]
	env_file = tmp_path / "env.yaml"
	_write_yaml(
		env_file,
		"trusted_signing_keys:\n  - id: kms:env-key\n",
	)
	user = tmp_path / "user.yaml"
	_write_yaml(
		user,
		"trusted_signing_keys:\n  - id: kms:user-key\n",
	)
	resolution = resolve_trust_config(
		env={"FLOWFORGE_TRUST_FILE": str(env_file)},
		user_path=user,
	)
	assert resolution.source == "env"
	ids = [k.id for k in resolution.config.trusted_signing_keys]
	assert ids == ["kms:env-key"]


def test_env_path_pointing_at_missing_file_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
	missing = tmp_path / "missing-env.yaml"
	with pytest.raises(TrustConfigError, match="FLOWFORGE_TRUST_FILE"):
		resolve_trust_config(env={"FLOWFORGE_TRUST_FILE": str(missing)})


def test_user_path_used_when_no_flag_or_env(tmp_path) -> None:  # type: ignore[no-untyped-def]
	user = tmp_path / "user.yaml"
	_write_yaml(
		user,
		(
			"trusted_signing_keys:\n"
			"  - id: kms:flowforge-publisher\n"
			"verified_publishers_only: true\n"
			"trust_verified_badge: false\n"
		),
	)
	resolution = resolve_trust_config(
		env={},
		user_path=user,
		system_path=tmp_path / "system-missing.yaml",
	)
	assert resolution.source == str(user)
	assert resolution.config.verified_publishers_only is True


def test_system_path_used_when_user_absent(tmp_path) -> None:  # type: ignore[no-untyped-def]
	sys_file = tmp_path / "system.yaml"
	_write_yaml(
		sys_file,
		"trusted_signing_keys:\n  - id: kms:system-key\n",
	)
	resolution = resolve_trust_config(
		env={},
		user_path=tmp_path / "no-user.yaml",
		system_path=sys_file,
	)
	assert resolution.source == str(sys_file)
	ids = [k.id for k in resolution.config.trusted_signing_keys]
	assert ids == ["kms:system-key"]


def test_pyproject_table_used_when_yaml_absent(tmp_path) -> None:  # type: ignore[no-untyped-def]
	pyproject = tmp_path / "pyproject.toml"
	pyproject.write_text(
		(
			"[tool.flowforge.trust]\n"
			'trust_verified_badge = true\n'
			"[[tool.flowforge.trust.trusted_signing_keys]]\n"
			'id = "kms:pyproject-key"\n'
		),
		"utf-8",
	)
	resolution = resolve_trust_config(
		env={},
		user_path=tmp_path / "no-user.yaml",
		system_path=tmp_path / "no-sys.yaml",
		pyproject_path=pyproject,
	)
	assert resolution.source == str(pyproject)
	assert resolution.config.trust_verified_badge is True
	assert (
		resolution.config.trusted_signing_keys[0].id == "kms:pyproject-key"
	)


def test_pyproject_absent_or_without_trust_falls_back_to_default(tmp_path) -> None:  # type: ignore[no-untyped-def]
	missing_pyproject = tmp_path / "missing-pyproject.toml"
	missing = resolve_trust_config(
		env={},
		user_path=tmp_path / "missing-user.yaml",
		system_path=tmp_path / "missing-system.yaml",
		pyproject_path=missing_pyproject,
	)
	assert missing.source == "default"
	assert str(missing_pyproject) in missing.probed

	pyproject = tmp_path / "pyproject.toml"
	pyproject.write_text("[tool.flowforge]\n", "utf-8")
	no_trust = resolve_trust_config(
		env={},
		user_path=tmp_path / "missing-user.yaml",
		system_path=tmp_path / "missing-system.yaml",
		pyproject_path=pyproject,
	)
	assert no_trust.source == "default"


def test_invalid_yaml_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
	bad = tmp_path / "bad.yaml"
	bad.write_text(": :: not yaml :: :\n", "utf-8")
	with pytest.raises(TrustConfigError):
		resolve_trust_config(flag_path=bad)


def test_unknown_keys_in_yaml_raise(tmp_path) -> None:  # type: ignore[no-untyped-def]
	bad = tmp_path / "bad.yaml"
	bad.write_text(
		"trusted_signing_keys:\n  - id: x\n    extra: nope\n", "utf-8"
	)
	with pytest.raises(TrustConfigError):
		resolve_trust_config(flag_path=bad)


def test_non_mapping_yaml_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
	bad = tmp_path / "list.yaml"
	bad.write_text("- not\n- a\n- mapping\n", "utf-8")
	with pytest.raises(TrustConfigError, match="must be a mapping"):
		resolve_trust_config(flag_path=bad)


def test_flag_path_pointing_at_missing_file_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
	with pytest.raises(TrustConfigError):
		resolve_trust_config(flag_path=tmp_path / "ghost.yaml")


def test_is_key_trusted_includes_verified_when_badge_trusted() -> None:
	cfg = TrustConfig(
		trusted_signing_keys=[TrustedKey(id="kms:user")],
		verified_signing_keys=[TrustedKey(id="kms:hub-verified")],
		trust_verified_badge=True,
	)
	assert cfg.is_key_trusted("kms:user")
	assert cfg.is_key_trusted("kms:hub-verified")
	assert not cfg.is_key_trusted("kms:rando")
	assert not cfg.is_key_trusted(None)


def test_is_key_trusted_excludes_verified_without_badge_opt_in() -> None:
	cfg = TrustConfig(
		verified_signing_keys=[TrustedKey(id="kms:hub-verified")],
		trust_verified_badge=False,
	)
	assert not cfg.is_key_trusted("kms:hub-verified")


def test_merge_trusted_keys_unions_sets() -> None:
	a = TrustConfig(trusted_signing_keys=[TrustedKey(id="kms:a")])
	b = TrustConfig(
		trusted_signing_keys=[TrustedKey(id="kms:b")],
		verified_signing_keys=[TrustedKey(id="kms:verified")],
		verified_publishers_only=True,
		trust_verified_badge=True,
	)
	merged = merge_trusted_keys(a, b)
	ids = sorted(k.id for k in merged.trusted_signing_keys)
	assert ids == ["kms:a", "kms:b"]
	assert [k.id for k in merged.verified_signing_keys] == ["kms:verified"]
	assert merged.verified_publishers_only is True
	assert merged.trust_verified_badge is True


def test_pyproject_trust_table_must_be_mapping(tmp_path) -> None:  # type: ignore[no-untyped-def]
	pyproject = tmp_path / "pyproject.toml"
	pyproject.write_text('[tool.flowforge]\ntrust = "bad"\n', "utf-8")
	with pytest.raises(TrustConfigError, match="must be a table"):
		resolve_trust_config(
			env={},
			user_path=tmp_path / "missing-user.yaml",
			system_path=tmp_path / "missing-system.yaml",
			pyproject_path=pyproject,
		)


def test_invalid_pyproject_trust_config_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
	pyproject = tmp_path / "pyproject.toml"
	pyproject.write_text(
		"[tool.flowforge.trust]\n"
		"[[tool.flowforge.trust.trusted_signing_keys]]\n"
		'id = "kms:pyproject-key"\n'
		'extra = "nope"\n',
		"utf-8",
	)
	with pytest.raises(TrustConfigError, match=r"\[tool\.flowforge\.trust\]"):
		resolve_trust_config(
			env={},
			user_path=tmp_path / "missing-user.yaml",
			system_path=tmp_path / "missing-system.yaml",
			pyproject_path=pyproject,
		)


def test_trust_set_from_keys_helper() -> None:
	cfg = trust_set_from_keys(["kms:k1", "kms:k2"])
	ids = [k.id for k in cfg.trusted_signing_keys]
	assert ids == ["kms:k1", "kms:k2"]
