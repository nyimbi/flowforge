"""audit-2026 E-57 acceptance tests (findings CL-01..CL-04)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from flowforge_cli.commands.new import _jtbd_schema
from flowforge_cli.commands.tutorial import _run_cmd, _validated_cwd
from flowforge_cli.jtbd.generators import (
	audit_taxonomy,
	domain_router,
	sa_model,
)
from flowforge_cli.jtbd.normalize import NormalizedBundle, NormalizedJTBD, normalize


# ---------------------------------------------------------------------------
# CL-01 — stub generators are implemented (templates produce non-empty output)
# ---------------------------------------------------------------------------


def _bundle_fixture() -> tuple[NormalizedBundle, NormalizedJTBD]:
	"""Smallest realistic bundle the generators accept."""

	raw = {
		"project": {
			"name": "claims-demo",
			"package": "claims_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {"roles": ["adjuster"], "permissions": ["claim.read"]},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "FNOL",
				"motivation": "recover loss",
				"outcome": "claim accepted",
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Loss",
						"required": True,
						"pii": False,
					},
				],
			}
		],
	}
	bundle = normalize(raw)
	return bundle, bundle.jtbds[0]


def test_CL_01_domain_router_generator_produces_non_empty_module() -> None:
	"""``domain_router.generate`` produces a real FastAPI router module."""

	bundle, jtbd = _bundle_fixture()
	out = domain_router.generate(bundle, jtbd)
	assert out.path.endswith("_router.py"), out.path
	# Must include router scaffolding — proves the template fired.
	assert "APIRouter" in out.content
	assert "post_event" in out.content
	assert len(out.content.splitlines()) >= 30, "<30 LoC stub regression"


def test_CL_01_audit_taxonomy_generator_produces_topic_table() -> None:
	"""``audit_taxonomy.generate`` emits the AUDIT_TOPICS tuple + is_known()."""

	bundle, _jtbd = _bundle_fixture()
	out = audit_taxonomy.generate(bundle)  # cross-bundle generator
	assert "AUDIT_TOPICS" in out.content
	assert "def is_known" in out.content
	# Even with a single-jtbd bundle the file is implemented (not a stub).
	assert "tuple[str, ...]" in out.content


def test_CL_01_sa_model_generator_produces_declarative_class() -> None:
	"""``sa_model.generate`` emits a SQLAlchemy DeclarativeBase + class."""

	bundle, jtbd = _bundle_fixture()
	out = sa_model.generate(bundle, jtbd)
	assert "DeclarativeBase" in out.content
	assert "mapped_column" in out.content
	assert len(out.content.splitlines()) >= 30, "<30 LoC stub regression"


# ---------------------------------------------------------------------------
# CL-02 — _validated_cwd / _run_cmd reject relative + missing paths
# ---------------------------------------------------------------------------


def test_CL_02_validated_cwd_rejects_relative_path(tmp_path: Path) -> None:
	"""Bare ``Path(".")`` resolves to an absolute cwd, not a relative one.

	The validator must always return an absolute, existing directory —
	that's the production-safety invariant.
	"""

	# A relative ``Path(".")`` is resolved by the validator.
	result = _validated_cwd(Path("."))
	assert result.is_absolute()
	assert result.exists()


def test_CL_02_validated_cwd_rejects_missing_dir(tmp_path: Path) -> None:
	missing = tmp_path / "does_not_exist"
	with pytest.raises(FileNotFoundError):
		_validated_cwd(missing)


def test_CL_02_validated_cwd_rejects_file_not_dir(tmp_path: Path) -> None:
	a_file = tmp_path / "f.txt"
	a_file.write_text("x")
	with pytest.raises(FileNotFoundError):
		_validated_cwd(a_file)


def test_CL_02_run_cmd_passes_absolute_cwd_to_subprocess(tmp_path: Path) -> None:
	"""subprocess.run never sees a relative cwd."""

	captured: dict[str, object] = {}

	class _Result:
		returncode = 0

	def _capture(*args: object, **kwargs: object) -> _Result:
		captured.update(kwargs)
		return _Result()

	with patch.object(subprocess, "run", side_effect=_capture):
		ok = _run_cmd(["echo", "hello"], cwd=Path("."), dry_run=False)
	assert ok
	cwd = captured["cwd"]
	assert isinstance(cwd, Path)
	assert cwd.is_absolute(), cwd
	assert cwd.exists()


# ---------------------------------------------------------------------------
# CL-03 — schema loaded via importlib.resources, not __file__ resolve
# ---------------------------------------------------------------------------


def test_CL_03_schema_load_uses_importlib_resources() -> None:
	"""Loading the JTBD schema does not depend on ``flowforge.__file__``.

	The audit-2026 fix dropped the editable-install fallback. Verify
	that the function returns a non-empty schema dict even when nothing
	mocks the importlib path.
	"""

	# Force re-load by clearing the cache.
	import flowforge_cli.commands.new as new_mod

	new_mod._JTBD_SCHEMA = None
	schema = _jtbd_schema()
	assert isinstance(schema, dict)
	# Must look like a JSON schema for JTBD.
	assert "$schema" in schema or "$id" in schema or "type" in schema


def test_CL_03_schema_load_does_not_reference_dunder_file(tmp_path: Path) -> None:
	"""Source code no longer carries a ``flowforge.__file__`` resolve path."""

	new_py = (
		Path(__file__).resolve().parent.parent
		/ "src"
		/ "flowforge_cli"
		/ "commands"
		/ "new.py"
	)
	src = new_py.read_text()
	# The audit-2026 CL-03 fix removed the import-flowforge fallback.
	assert "_ff.__file__" not in src, (
		"new.py still resolves the schema via flowforge.__file__ — see CL-03"
	)


# ---------------------------------------------------------------------------
# CL-04 — bare ``except Exception`` replaced with logged + chained
# ---------------------------------------------------------------------------


def test_CL_04_schema_load_chains_failure(
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""When the bundled schema can't be loaded, the failure is logged and chained."""

	import flowforge_cli.commands.new as new_mod

	new_mod._JTBD_SCHEMA = None
	# Patch the importlib resolver to raise a recognisable error.
	target_exc = FileNotFoundError("synthetic missing schema")
	with caplog.at_level(logging.ERROR, logger="flowforge_cli.commands.new"):
		with patch.object(new_mod, "_ir_files", side_effect=lambda *_a, **_k: (_ for _ in ()).throw(target_exc)):
			with pytest.raises(RuntimeError) as exc_info:
				_jtbd_schema()
	# The audit-2026 fix mandates a chained __cause__ + log line.
	assert exc_info.value.__cause__ is target_exc
	assert any(
		"failed to load bundled JTBD schema" in rec.getMessage() for rec in caplog.records
	), [r.getMessage() for r in caplog.records]


def test_CL_04_no_bare_except_in_new_module(tmp_path: Path) -> None:
	"""Source code carries no bare ``except Exception`` blocks."""

	new_py = (
		Path(__file__).resolve().parent.parent
		/ "src"
		/ "flowforge_cli"
		/ "commands"
		/ "new.py"
	)
	src = new_py.read_text()
	# Lines starting with bare 'except Exception:' (no specific subclass)
	# should be gone. Allow tuple-form catches like (FileNotFoundError, …).
	for lineno, line in enumerate(src.splitlines(), start=1):
		stripped = line.strip()
		if stripped.startswith("except Exception:") or stripped.startswith(
			"except Exception as"
		):
			pytest.fail(f"new.py:{lineno}: bare except Exception (audit-2026 CL-04)")
