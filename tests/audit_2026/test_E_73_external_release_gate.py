"""Ratchets for fail-closed external release qualification targets."""

from __future__ import annotations

import importlib
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "audit_2026"))
package_sets = importlib.import_module("package_sets")
pypi_build_smoke = importlib.import_module("pypi_build_smoke")
PINNED_SECRET_WORKFLOW_ACTIONS = {
    "actions/checkout": "34e114876b0b11c390a56381ad16ebd13914f8d5",
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "astral-sh/setup-uv": "e4db8464a088ece1b920f60402e813ea4de65b8f",
    "pnpm/action-setup": "f40ffcd9367d9f12939873eb1018b921a783ffaa",
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _shipping_workspace_dirs() -> tuple[str, ...]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        root = tomllib.load(handle)
    shipping: list[str] = []
    for member in root["tool"]["uv"]["workspace"]["members"]:
        if not member.startswith("python/"):
            continue
        pyproject_path = ROOT / member / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            pyproject = tomllib.load(handle)
        if pyproject.get("tool", {}).get("uv", {}).get("package", True):
            shipping.append(member.removeprefix("python/"))
    return tuple(shipping)


def _python_pyprojects() -> tuple[Path, ...]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        root = tomllib.load(handle)
    return tuple(
        ROOT / member / "pyproject.toml"
        for member in root["tool"]["uv"]["workspace"]["members"]
        if member.startswith("python/")
    )


def test_audit_workflow_yaml_files_parse() -> None:
    for path in sorted((ROOT / ".github" / "workflows").glob("audit-2026*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict), f"{path} did not parse to a workflow mapping"


def test_external_release_gate_forbids_local_skip_escapes() -> None:
    makefile = _read("Makefile")

    assert ".PHONY: audit-2026-release-external" in makefile
    assert ".PHONY: audit-2026-release-external-preflight" in makefile
    assert "VISREG_ALLOW_SKIP=1 is forbidden for release qualification" in makefile
    assert "BROWSER_E2E_ALLOW_SKIP=1 is forbidden for release qualification" in makefile
    assert "$(MAKE) audit-2026-release-external-preflight" in makefile
    assert "$(MAKE) audit-2026-visual-regression-dom" in makefile
    assert "$(MAKE) audit-2026-browser-e2e" in makefile
    assert "$(MAKE) audit-2026-ums-parity" in makefile
    assert "FLOWFORGE_REQUIRE_UMS_PARITY" in makefile
    assert "skipping downstream UMS parity" in makefile
    assert "$(MAKE) audit-2026-live-postgres" in makefile


def test_external_release_gate_is_wired_as_manual_release_workflow() -> None:
    workflow = _read(".github/workflows/audit-2026-release-external.yml")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" in workflow
    assert "Optional downstream UMS parity is release-" in workflow
    assert "not a package dependency" in workflow
    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert "backend_repository:" in workflow
    assert "used only when run_ums_parity is true" in workflow
    assert 'default: "nyimbi/ums"' in workflow
    assert "backend_ref:" in workflow
    assert "run_ums_parity:" in workflow
    assert "default: false" in workflow
    assert "Detect UMS backend checkout token" in workflow
    assert "if: ${{ inputs.run_ums_parity }}" in workflow
    assert "BACKEND_REPOSITORY: ${{ inputs.backend_repository }}" in workflow
    assert "UMS_BACKEND_TOKEN: ${{ secrets.UMS_BACKEND_TOKEN }}" in workflow
    assert (
        "nyimbi/ums is private from GitHub Actions without UMS_BACKEND_TOKEN"
        in workflow
    )
    assert "attempting public UMS backend checkout without a token" in workflow
    assert "Checkout UMS backend with token" in workflow
    assert "Checkout UMS backend without token" in workflow
    assert (
        "inputs.run_ums_parity && steps.ums-backend-token.outputs.has_token == 'true'"
        in workflow
    )
    assert (
        "inputs.run_ums_parity && steps.ums-backend-token.outputs.has_token == 'false'"
        in workflow
    )
    assert "repository: ${{ inputs.backend_repository }}" in workflow
    assert "ref: ${{ inputs.backend_ref }}" in workflow
    assert workflow.count("persist-credentials: false") >= 3
    assert "token: ${{ secrets.UMS_BACKEND_TOKEN }}" in workflow
    assert "postgres:16" in workflow
    assert "pnpm exec playwright install --with-deps chromium" in workflow
    assert "uv sync --all-packages --all-extras" in workflow
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow
    assert "CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}" in workflow
    assert "BACKEND_ROOT: ${{ github.workspace }}/backend" in workflow
    assert "FLOWFORGE_REQUIRE_UMS_PARITY:" in workflow
    assert "FLOWFORGE_TEST_PG_URL:" in workflow
    assert "make audit-2026-release-external" in workflow
    assert "Write external release evidence summary" in workflow
    assert "external-release-evidence-current.md" in workflow
    assert "GITHUB_RUN_ID" in workflow
    assert (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4"
        in workflow
    )
    assert "audit-2026-release-external-evidence" in workflow
    assert "external-release-evidence*.md" in workflow
    assert "examples/**/screenshots/**/*.dom.html" in workflow
    assert "examples/insurance_claim/jtbd-bundle.json.overrides.json" in workflow
    assert "tests/visual_regression/playwright-report/**" in workflow
    assert "tests/visual_regression/test-results/**" in workflow
    assert "VISREG_ALLOW_SKIP" not in workflow
    assert "BROWSER_E2E_ALLOW_SKIP" not in workflow


def test_dom_baseline_generation_workflow_uploads_reviewable_artifact() -> None:
    workflow = _read(".github/workflows/audit-2026-dom-baselines.yml")

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "DOM_BASELINE_CADENCE:" in workflow
    assert (
        "github.event_name == 'workflow_dispatch' && inputs.cadence || 'smoke'"
        in workflow
    )
    assert "type: choice" in workflow
    assert "smoke" in workflow
    assert "full" in workflow
    assert "pnpm exec playwright install --with-deps chromium" in workflow
    assert 'UPDATE_BASELINES: "1"' in workflow
    assert "bash scripts/visual_regression/run_dom_snapshots.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "audit-2026-dom-baseline-candidates" in workflow
    assert "examples/**/screenshots/**/*.dom.html" in workflow
    assert "VISREG_ALLOW_SKIP" not in workflow


def test_flowforge_gate_pins_check_all_parallelism() -> None:
    workflow = _read(".github/workflows/flowforge-gate.yml")

    assert "bash scripts/check_all.sh" in workflow
    assert 'FLOWFORGE_CHECK_JOBS: "4"' in workflow
    assert "VISREG_ALLOW_SKIP" not in workflow


def test_ci_workflows_pin_pnpm_11_for_allow_builds() -> None:
    """pnpm 11 is required for allowBuilds and must run on Node 22+."""

    tag_pinned_workflows = [
        ".github/workflows/audit-2026.yml",
        ".github/workflows/audit-2026-dom-baselines.yml",
        ".github/workflows/flowforge-gate.yml",
    ]
    for path in tag_pinned_workflows:
        workflow = _read(path)
        assert "pnpm/action-setup@v4" in workflow
        assert 'version: "11.1.3"' in workflow
        assert "actions/setup-node@v4" in workflow
        assert 'node-version: "22"' in workflow

    release_workflow = _read(".github/workflows/audit-2026-release-external.yml")
    assert (
        "pnpm/action-setup@f40ffcd9367d9f12939873eb1018b921a783ffaa # v4"
        in release_workflow
    )
    assert 'version: "11.1.3"' in release_workflow
    assert (
        "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4"
        in release_workflow
    )
    assert 'node-version: "22"' in release_workflow


def test_secret_bearing_release_workflows_pin_actions_to_shas() -> None:
    """Workflows with API tokens must not depend on mutable action tags."""

    for path in [
        ".github/workflows/audit-2026-polish-copy-sidecar.yml",
        ".github/workflows/audit-2026-release-external.yml",
    ]:
        workflow = _read(path)
        for action, sha in PINNED_SECRET_WORKFLOW_ACTIONS.items():
            if action in workflow:
                assert f"{action}@{sha}" in workflow
        mutable = re.findall(r"uses:\s+([^\s#]+@v\d+)\b", workflow)
        assert mutable == [], f"{path} has mutable action refs: {mutable}"


def test_ci_uv_cache_uses_tracked_dependency_files() -> None:
    """uv.lock is intentionally ignored, so CI must not require it for setup-uv caching."""

    for path in [
        ".github/workflows/audit-2026.yml",
        ".github/workflows/audit-2026-polish-copy-sidecar.yml",
        ".github/workflows/audit-2026-release-external.yml",
        ".github/workflows/flowforge-gate.yml",
        ".github/workflows/jtbd-lint.yml",
    ]:
        workflow = _read(path)
        assert "uv.lock" not in workflow
        assert "pyproject.toml" in workflow


def test_jtbd_lint_workflow_uses_repo_relative_bundle_paths() -> None:
    workflow = _read(".github/workflows/jtbd-lint.yml")

    assert 'uv run flowforge jtbd lint --bundle "$bundle"' in workflow
    assert '--bundle "../$bundle"' not in workflow
    assert 'lint_flags="--warn-only"' in workflow
    assert 'lint_flags="--strict"' in workflow


def test_external_release_preflight_reports_all_hard_prerequisites() -> None:
    script = _read("scripts/audit_2026/check_external_release_preflight.py")
    sidecar = _read("scripts/audit_2026/check_polish_copy_sidecar.py")

    assert "VISREG_ALLOW_SKIP" in script
    assert "BROWSER_E2E_ALLOW_SKIP" in script
    assert "DOM baselines are not checked in" in script
    assert "check_sidecar()" in script
    assert "uv run flowforge polish-copy" in sidecar
    assert "--require-llm --commit" in sidecar
    assert "flowforge-cli[llm]" in sidecar
    assert "FLOWFORGE_POLISH_PROVIDER=claude-cli" in sidecar
    assert "BACKEND_ROOT not found" in script
    assert "FLOWFORGE_REQUIRE_UMS_PARITY" in script
    assert "unset FLOWFORGE_REQUIRE_UMS_PARITY" in script
    assert "FLOWFORGE_TEST_PG_URL" in script
    assert "browser execution is verified by make audit-2026-release-external" in script


def test_external_release_evidence_template_tracks_required_proofs() -> None:
    template = _read("docs/audit-2026/external-release-evidence-template.md")
    runbook = _read("docs/audit-2026/external-release-runbook.md")

    assert "external-release-evidence-template.md" in runbook
    assert "gh workflow run audit-2026-release-external.yml" in runbook
    assert "uv sync --all-packages --all-extras" in runbook
    assert 'uv run python -c "import anthropic"' in runbook
    assert "--require-llm" in runbook
    assert "`polish-copy`" in runbook
    assert "intentionally degrades to a no-op" in runbook
    assert "preflight does not prove browser execution" in runbook
    for required in [
        "Flowforge commit",
        "DOM baseline commit",
        "`VISREG_ALLOW_SKIP` unset",
        "`BROWSER_E2E_ALLOW_SKIP` unset",
        'uv run python -c "import anthropic"',
        "Preflight caveat acknowledged",
        "uv run flowforge polish-copy --require-llm --commit",
        "Workflow run URL",
        "Artifact URL",
        "Browser full-stack Playwright",
        "Real-key polish-copy sidecar gate",
        "UMS workflow-def parity",
        "Live Postgres tenant/ordinal index plan",
    ]:
        assert required in template


def test_internal_python_dependencies_are_compatibly_bounded() -> None:
    """PyPI wheels must not publish bare internal FlowForge dependencies."""

    pyprojects = _python_pyprojects()
    internal_names = {
        package_sets._distribution_key(
            tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"]
        )
        for pyproject in pyprojects
    }
    assert len(internal_names) == 46
    assert (
        package_sets._distribution_key("flowforge-notify-multichannel")
        in internal_names
    )
    assert package_sets._distribution_key("flowforge-jtbd-insurance") in internal_names
    failures: list[str] = []
    for pyproject in sorted(pyprojects):
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        for dep in data.get("project", {}).get("dependencies", []):
            name = (
                dep.split("[", 1)[0].split("<", 1)[0].split(">", 1)[0].split("=", 1)[0]
            )
            if package_sets._distribution_key(name) in internal_names and not (
                ">=0.1.0" in dep and "<0.2.0" in dep
            ):
                failures.append(f"{pyproject.relative_to(ROOT)}: {dep}")
    assert failures == []


def test_flowforge_cli_wheel_includes_runtime_package() -> None:
    """The console-script package must not whitelist only template assets."""

    data = tomllib.loads(
        (ROOT / "python" / "flowforge-cli" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    hatch = data.get("tool", {}).get("hatch", {})
    assert hatch.get("build", {}).get("targets", {}).get("wheel", {}).get(
        "packages"
    ) == ["src/flowforge_cli"]
    assert "include" not in hatch.get("build", {}), (
        "flowforge-cli wheel must include runtime modules, not only template assets"
    )


def test_shipping_packages_declared_typed_have_pep561_markers() -> None:
    failures: list[str] = []
    for package in package_sets.shipping_packages():
        package_root = ROOT / "python" / package.directory
        pyproject = tomllib.loads(
            (package_root / "pyproject.toml").read_text(encoding="utf-8")
        )
        classifiers = pyproject.get("project", {}).get("classifiers", [])
        if "Typing :: Typed" not in classifiers:
            continue
        marker_path = (
            package_root / "src" / package.import_package.replace(".", "/") / "py.typed"
        )
        if not marker_path.is_file():
            failures.append(f"{package.directory}: missing {marker_path}")

    assert failures == []


def test_shipping_packages_have_pypi_publication_metadata() -> None:
    required_project_fields = {
        "name",
        "version",
        "description",
        "readme",
        "requires-python",
        "license",
        "license-files",
        "authors",
        "maintainers",
        "keywords",
        "classifiers",
        "urls",
    }
    failures: list[str] = []
    for package in package_sets.shipping_packages():
        pyproject_path = ROOT / "python" / package.directory / "pyproject.toml"
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        project = pyproject.get("project", {})
        missing = sorted(
            field for field in required_project_fields if not project.get(field)
        )
        if missing:
            failures.append(f"{package.directory}: missing {', '.join(missing)}")

    assert failures == []


def test_metadata_stamper_uses_workspace_shipping_packages() -> None:
    script = _read("scripts/finalize_pypi_metadata.py")

    assert 'AUDIT_SCRIPTS / "package_sets.py"' in script
    assert "_load_shipping_packages()" in script
    assert "for package in _shipping_packages():" in script
    assert "STRATEGIC_PACKAGES" not in script
    assert "missing PyPI keyword metadata" in script
    assert 'license = "Apache-2.0"' in script
    assert 'license = { file = "LICENSE" }' not in script
    assert "make audit-2026-pypi-build" in script


def test_publishing_docs_require_cli_wheel_smoke() -> None:
    publishing = _read("docs/release/PUBLISHING.md")
    makefile = _read("Makefile")
    script = _read("scripts/audit_2026/pypi_build_smoke.py")

    assert ".PHONY: audit-2026-pypi-build" in makefile
    assert "scripts/audit_2026/pypi_build_smoke.py" in makefile
    assert "$(MAKE) audit-2026-pypi-build" in makefile
    shipping_packages = _shipping_workspace_dirs()
    assert len(shipping_packages) == 16
    assert "flowforge-core" in shipping_packages
    assert "flowforge-cli" in shipping_packages
    assert "flowforge-jtbd-hub" in shipping_packages
    assert "from package_sets import shipping_packages" in script
    assert "STRATEGIC_PACKAGES" not in script
    assert '"uv", "build"' in script
    assert '"twine"' in script
    assert '"check"' in script
    assert (
        "wheels_by_distribution[_distribution_key(package.distribution_name)]" in script
    )
    assert "flowforge-cli" in publishing
    assert '"--help"' in script
    assert "importlib.import_module(module)" in script
    assert "_assert_clean_venv_installs_shipping_packages(" in script
    assert "expected_artifacts = len(packages) * 2" in script
    assert "expected {len(packages)} wheels and {len(packages)} sdists" in script
    assert "_assert_artifact_metadata_names(" in script
    assert "wheel `METADATA`" in publishing
    assert "sdist `PKG-INFO` `Name` fields" in publishing
    assert "_assert_wheels_include_py_typed(wheels_by_distribution, packages)" in script
    assert "_assert_artifacts_include_license_files(" in script
    assert "_assert_artifact_internal_dependencies_bounded(" in script
    assert "Requires-Dist" in script
    assert "PKG-INFO" in script
    assert "_has_required_internal_dependency_bounds(" in script
    assert "exact `>=0.1.0,<0.2.0`" in publishing
    assert "wheel filename distribution" in script
    assert "wheel's own" in publishing
    assert "`.dist-info/METADATA`" in publishing
    assert "top-level sdist PKG-INFO" in script
    assert "top-level sdist `PKG-INFO`" in publishing
    assert "_shipping_distribution_keys(packages)" in script
    assert "unpublished internal Flowforge dependencies" in script
    assert "zipfile.ZipFile" in script
    assert "tarfile.open" in script
    assert "_assert_exact_artifacts_by_package(" in script
    assert "make audit-2026-pypi-build" in publishing
    assert "flowforge-cli-wheel-smoke" in publishing
    assert "--force-reinstall dist/*.whl" in publishing
    assert "flowforge --help" in publishing
    assert "ModuleNotFoundError" in publishing
    assert "exactly one wheel and one sdist per package" in publishing
    assert "py.typed" in publishing
    assert "declared `LICENSE` file" in publishing
    assert "`flowforge-jtbd-*` domain packages" in publishing
    assert "`flowforge-jtbd-*-starter`" not in publishing
    assert "scripts/audit_2026/package_sets.py" in publishing
    assert "for pkg in flowforge-core" not in publishing


def test_pypi_build_smoke_rejects_missing_or_duplicate_package_artifacts(
    tmp_path: Path,
) -> None:
    packages = (
        package_sets.ShippingPackage(
            directory="flowforge-core",
            distribution_name="flowforge-core",
            import_package="flowforge",
        ),
        package_sets.ShippingPackage(
            directory="flowforge-cli",
            distribution_name="flowforge-cli",
            import_package="flowforge_cli",
        ),
    )
    wheels = [
        tmp_path / "flowforge_core-0.1.0-py3-none-any.whl",
        tmp_path / "flowforge_core-0.1.1-py3-none-any.whl",
    ]
    sdists = [
        tmp_path / "flowforge-core-0.1.0.tar.gz",
        tmp_path / "flowforge-core-0.1.1.tar.gz",
    ]

    with pytest.raises(SystemExit, match="flowforge-cli"):
        pypi_build_smoke._assert_exact_artifacts_by_package(wheels, sdists, packages)


def test_pypi_build_smoke_rejects_artifact_metadata_name_mismatches(
    tmp_path: Path,
) -> None:
    package = package_sets.ShippingPackage(
        directory="flowforge-cli",
        distribution_name="flowforge-cli",
        import_package="flowforge_cli",
    )
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "flowforge_cli-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: other\nVersion: 0.1.0\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    package_dir.mkdir()
    pkg_info = package_dir / "PKG-INFO"
    pkg_info.write_text(
        "Metadata-Version: 2.4\nName: other\nVersion: 0.1.0\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname="flowforge_cli-0.1.0/PKG-INFO")

    with pytest.raises(SystemExit, match="metadata names"):
        pypi_build_smoke._assert_artifact_metadata_names(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            (package,),
        )


def test_pypi_build_smoke_rejects_non_temp_output_dirs_before_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    temp_root = tmp_path / "allowed-temp"
    monkeypatch.setattr(pypi_build_smoke.tempfile, "gettempdir", lambda: str(temp_root))
    outside = tmp_path / "outside-temp-root" / "dist"

    with pytest.raises(SystemExit, match="dist-dir must be under"):
        pypi_build_smoke._prepare_dir(outside, purpose="dist-dir")

    assert not outside.exists()


def test_pypi_build_smoke_rejects_artifacts_missing_license_files(
    tmp_path: Path,
) -> None:
    package = package_sets.ShippingPackage(
        directory="flowforge-core",
        distribution_name="flowforge",
        import_package="flowforge",
    )
    wheel = tmp_path / "flowforge-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("flowforge-0.1.0.dist-info/METADATA", "")
        archive.writestr("flowforge/__init__.py", "")
    sdist = tmp_path / "flowforge-0.1.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        package_dir = tmp_path / "flowforge-0.1.0"
        package_dir.mkdir()
        pyproject = package_dir / "pyproject.toml"
        pyproject.write_text('[project]\nname = "flowforge"\n', encoding="utf-8")
        archive.add(pyproject, arcname="flowforge-0.1.0/pyproject.toml")

    key = pypi_build_smoke._distribution_key(package.distribution_name)
    with pytest.raises(SystemExit, match="missing declared license files"):
        pypi_build_smoke._assert_artifacts_include_license_files(
            {key: wheel},
            {key: sdist},
            (package,),
        )


def test_pypi_build_smoke_requires_top_level_sdist_license(
    tmp_path: Path,
) -> None:
    package = package_sets.ShippingPackage(
        directory="flowforge-core",
        distribution_name="flowforge",
        import_package="flowforge",
    )
    wheel = tmp_path / "flowforge-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("flowforge-0.1.0.dist-info/METADATA", "")
        archive.writestr("flowforge-0.1.0.dist-info/licenses/LICENSE", "")
    sdist = tmp_path / "flowforge-0.1.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        package_dir = tmp_path / "flowforge-0.1.0"
        nested_license = package_dir / "src" / "flowforge" / "LICENSE"
        nested_license.parent.mkdir(parents=True)
        nested_license.write_text("nested only\n", encoding="utf-8")
        archive.add(nested_license, arcname="flowforge-0.1.0/src/flowforge/LICENSE")

    key = pypi_build_smoke._distribution_key(package.distribution_name)
    with pytest.raises(SystemExit, match="sdist LICENSE"):
        pypi_build_smoke._assert_artifacts_include_license_files(
            {key: wheel},
            {key: sdist},
            (package,),
        )


def test_pypi_build_smoke_requires_license_in_wheel_metadata_dist_info(
    tmp_path: Path,
) -> None:
    package = package_sets.ShippingPackage(
        directory="flowforge-core",
        distribution_name="flowforge",
        import_package="flowforge",
    )
    wheel = tmp_path / "flowforge-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("flowforge-0.1.0.dist-info/METADATA", "")
        archive.writestr("other-0.1.0.dist-info/licenses/LICENSE", "")
    sdist = tmp_path / "flowforge-0.1.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        package_dir = tmp_path / "flowforge-0.1.0"
        license_file = package_dir / "LICENSE"
        license_file.parent.mkdir()
        license_file.write_text("root license\n", encoding="utf-8")
        archive.add(license_file, arcname="flowforge-0.1.0/LICENSE")

    key = pypi_build_smoke._distribution_key(package.distribution_name)
    with pytest.raises(SystemExit, match="wheel LICENSE"):
        pypi_build_smoke._assert_artifacts_include_license_files(
            {key: wheel},
            {key: sdist},
            (package,),
        )


def test_pypi_build_smoke_installs_and_imports_all_shipping_wheels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packages = (
        package_sets.ShippingPackage(
            directory="flowforge-core",
            distribution_name="flowforge",
            import_package="flowforge",
        ),
        package_sets.ShippingPackage(
            directory="flowforge-fastapi",
            distribution_name="flowforge-fastapi",
            import_package="flowforge_fastapi",
        ),
    )
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, cwd: Path = pypi_build_smoke.ROOT) -> None:
        calls.append(argv)

    monkeypatch.setattr(pypi_build_smoke, "_run", fake_run)
    wheel_paths = {
        pypi_build_smoke._distribution_key("flowforge"): tmp_path
        / "dist"
        / "flowforge-0.1.0-py3-none-any.whl",
        pypi_build_smoke._distribution_key("flowforge-fastapi"): tmp_path
        / "dist"
        / "flowforge_fastapi-0.1.0-py3-none-any.whl",
    }

    pypi_build_smoke._assert_clean_venv_installs_shipping_packages(
        packages,
        venv_dir=tmp_path / "venv",
        wheels_by_distribution=wheel_paths,
    )

    pip_install = next(call for call in calls if call[:3] == ["uv", "pip", "install"])
    assert str(wheel_paths["flowforge"]) in pip_install
    assert str(wheel_paths["flowforge-fastapi"]) in pip_install
    assert "flowforge" not in pip_install
    assert "flowforge-fastapi" not in pip_install
    import_check = next(call for call in calls if call[1] == "-c")
    assert "importlib.import_module(module)" in import_check[2]
    assert "'flowforge'" in import_check[2]
    assert "'flowforge_fastapi'" in import_check[2]
    assert calls[-1][-1] == "--help"


def test_pypi_build_smoke_rejects_unbounded_internal_artifact_dependencies(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "flowforge_cli-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: flowforge-cli\n"
            "Version: 0.1.0\n"
            "Requires-Dist: flowforge_jtbd\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    package_dir.mkdir()
    pkg_info = package_dir / "PKG-INFO"
    pkg_info.write_text(
        "Metadata-Version: 2.4\n"
        "Name: flowforge-cli\n"
        "Version: 0.1.0\n"
        "Requires-Dist: flowforge_jtbd\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname="flowforge_cli-0.1.0/PKG-INFO")

    with pytest.raises(SystemExit, match="unbounded internal Flowforge"):
        pypi_build_smoke._assert_artifact_internal_dependencies_bounded(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            internal_distribution_keys=frozenset({"flowforge-jtbd"}),
            shipping_distribution_keys=frozenset({"flowforge-jtbd"}),
        )


def test_pypi_build_smoke_rejects_imprecise_internal_artifact_bounds(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "flowforge_cli-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: flowforge-cli\n"
            "Version: 0.1.0\n"
            "Requires-Dist: flowforge_jtbd>=0.1.0,<0.2.0.post1\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    package_dir.mkdir()
    pkg_info = package_dir / "PKG-INFO"
    pkg_info.write_text(
        "Metadata-Version: 2.4\n"
        "Name: flowforge-cli\n"
        "Version: 0.1.0\n"
        "Requires-Dist: flowforge_jtbd>=0.1.0,<0.2.0.post1\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname="flowforge_cli-0.1.0/PKG-INFO")

    with pytest.raises(SystemExit, match="unbounded internal Flowforge"):
        pypi_build_smoke._assert_artifact_internal_dependencies_bounded(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            internal_distribution_keys=frozenset({"flowforge-jtbd"}),
            shipping_distribution_keys=frozenset({"flowforge-jtbd"}),
        )


def test_pypi_build_smoke_rejects_extra_internal_artifact_specifiers(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "flowforge_cli-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: flowforge-cli\n"
            "Version: 0.1.0\n"
            "Requires-Dist: flowforge_jtbd>=0.1.0,<0.2.0,!=0.1.3\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    package_dir.mkdir()
    pkg_info = package_dir / "PKG-INFO"
    pkg_info.write_text(
        "Metadata-Version: 2.4\n"
        "Name: flowforge-cli\n"
        "Version: 0.1.0\n"
        "Requires-Dist: flowforge_jtbd>=0.1.0,<0.2.0,!=0.1.3\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname="flowforge_cli-0.1.0/PKG-INFO")

    with pytest.raises(SystemExit, match="unbounded internal Flowforge"):
        pypi_build_smoke._assert_artifact_internal_dependencies_bounded(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            internal_distribution_keys=frozenset({"flowforge-jtbd"}),
            shipping_distribution_keys=frozenset({"flowforge-jtbd"}),
        )


def test_pypi_build_smoke_rejects_unpublished_internal_artifact_dependencies(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "flowforge_cli-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: flowforge-cli\n"
            "Version: 0.1.0\n"
            "Requires-Dist: flowforge_jtbd_insurance>=0.1.0,<0.2.0\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    package_dir.mkdir()
    pkg_info = package_dir / "PKG-INFO"
    pkg_info.write_text(
        "Metadata-Version: 2.4\n"
        "Name: flowforge-cli\n"
        "Version: 0.1.0\n"
        "Requires-Dist: flowforge_jtbd_insurance>=0.1.0,<0.2.0\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname="flowforge_cli-0.1.0/PKG-INFO")

    with pytest.raises(SystemExit, match="unpublished internal Flowforge"):
        pypi_build_smoke._assert_artifact_internal_dependencies_bounded(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            internal_distribution_keys=frozenset({"flowforge-jtbd-insurance"}),
            shipping_distribution_keys=frozenset({"flowforge-jtbd"}),
        )


def test_pypi_build_smoke_requires_wheel_metadata_for_wheel_distribution(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "other-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: other\nVersion: 0.1.0\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    package_dir.mkdir()
    pkg_info = package_dir / "PKG-INFO"
    pkg_info.write_text(
        "Metadata-Version: 2.4\nName: flowforge-cli\nVersion: 0.1.0\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(pkg_info, arcname="flowforge_cli-0.1.0/PKG-INFO")

    with pytest.raises(SystemExit, match="wheel filename distribution"):
        pypi_build_smoke._assert_artifact_internal_dependencies_bounded(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            internal_distribution_keys=frozenset({"flowforge-jtbd"}),
            shipping_distribution_keys=frozenset({"flowforge-jtbd"}),
        )


def test_pypi_build_smoke_requires_top_level_sdist_pkg_info_for_dependencies(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "flowforge_cli-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "flowforge_cli-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: flowforge-cli\nVersion: 0.1.0\n",
        )
    sdist = tmp_path / "flowforge_cli-0.1.0.tar.gz"
    package_dir = tmp_path / "flowforge_cli-0.1.0"
    nested_dir = package_dir / "src" / "flowforge_cli.egg-info"
    nested_dir.mkdir(parents=True)
    nested_pkg_info = nested_dir / "PKG-INFO"
    nested_pkg_info.write_text(
        "Metadata-Version: 2.4\n"
        "Name: flowforge-cli\n"
        "Version: 0.1.0\n"
        "Requires-Dist: flowforge_jtbd>=0.1.0,<0.2.0\n",
        encoding="utf-8",
    )
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(
            nested_pkg_info,
            arcname="flowforge_cli-0.1.0/src/flowforge_cli.egg-info/PKG-INFO",
        )

    with pytest.raises(SystemExit, match="top-level sdist PKG-INFO"):
        pypi_build_smoke._assert_artifact_internal_dependencies_bounded(
            {"flowforge-cli": wheel},
            {"flowforge-cli": sdist},
            internal_distribution_keys=frozenset({"flowforge-jtbd"}),
            shipping_distribution_keys=frozenset({"flowforge-jtbd"}),
        )


def test_closed_package_coverage_ratchet_tracks_completed_packages() -> None:
    makefile = _read("Makefile")
    script = _read("scripts/audit_2026/closed_package_coverage.py")

    assert ".PHONY: audit-2026-closed-package-coverage" in makefile
    assert "scripts/audit_2026/closed_package_coverage.py" in makefile
    assert "audit-2026-closed-package-coverage \\" in makefile
    assert "--cov-branch" in script
    assert "--cov-fail-under=100" in script
    assert "from package_sets import shipping_packages" in script
    assert "CLOSED_PACKAGE_COVERAGE" not in script
    assert "package.import_package" in script
    assert 'ROOT / "python" / package_name' in script
    package_sets = _read("scripts/audit_2026/package_sets.py")
    assert 'root["tool"]["uv"]["workspace"]["members"]' in package_sets
    assert 'package", True' in package_sets
    assert "src/" in package_sets


def test_package_set_helper_rejects_ambiguous_wheel_packages() -> None:
    pyproject = {
        "tool": {
            "hatch": {
                "build": {
                    "targets": {
                        "wheel": {
                            "packages": [
                                "src/flowforge",
                                "src/flowforge_extra",
                            ]
                        }
                    }
                }
            }
        }
    }

    with pytest.raises(SystemExit, match="exactly one wheel package"):
        package_sets._import_package(pyproject, directory="flowforge-core")


def test_package_set_helper_rejects_duplicate_shipping_identities() -> None:
    packages = [
        package_sets.ShippingPackage(
            directory="flowforge-core",
            distribution_name="flowforge-core",
            import_package="flowforge",
        ),
        package_sets.ShippingPackage(
            directory="flowforge-core-alias",
            distribution_name="flowforge_core",
            import_package="flowforge_core",
        ),
    ]

    with pytest.raises(SystemExit, match="duplicate distribution name"):
        package_sets._assert_unique_packages(packages)


def test_dom_baselines_do_not_embed_ci_checkout_paths() -> None:
    normalizer = _read("tests/visual_regression/lib/dom_normalize.ts")
    assert "data-vite-dev-id" in normalizer
    assert "normaliseViteDevId" in normalizer

    for path in sorted((ROOT / "examples").glob("*/screenshots/**/*.dom.html")):
        body = path.read_text(encoding="utf-8")
        assert "/home/runner/work/" not in body, f"{path} embeds a CI checkout path"
        assert "/Users/" not in body, f"{path} embeds a local checkout path"


def test_ums_parity_has_fail_closed_release_target() -> None:
    makefile = _read("Makefile")
    check_all = _read("scripts/check_all.sh")

    assert ".PHONY: audit-2026-ums-parity" in makefile
    assert "BACKEND_ROOT not found" in makefile
    assert "tests/test_workflow_def_parity.py -v --tb=short" in makefile
    assert "audit-2026: \\" in makefile
    assert "audit-2026-ums-parity \\" in makefile
    assert "bash scripts/check_all.sh" in check_all
    assert "path to flowforge repo root" in check_all
    assert "SKIP UMS parity: BACKEND_ROOT not found" in check_all
    assert "audit-2026-ums-parity: BACKEND_ROOT not found" not in check_all
    assert "framework/scripts/check_all.sh" not in check_all
    assert "test_property_coverage_gate.py" in check_all
    assert "test_hypothesis_seed_uniqueness.py" in check_all
    assert "scripts/i18n/check_coverage.py" in check_all
    run_integration = _read("scripts/run_integration.sh")
    assert "bash scripts/run_integration.sh" in run_integration
    assert "path to flowforge repo root" in run_integration
    assert "framework/scripts/run_integration.sh" not in run_integration
