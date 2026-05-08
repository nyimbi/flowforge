# flowforge-jtbd-hub

Public registry service for signed JTBD packages: publish, install, search, rate, and demote with a trust-file verification gate.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-jtbd-hub
```

## What it does

`flowforge-jtbd-hub` is the E-24 registry service. It exposes a FastAPI application (via `create_app()`) that lets publishers push signed JTBD tarball packages and lets consumers search, install, rate, and demote them. The domain layer (`PackageRegistry`) is in-memory by default; production hosts subclass it and override the three storage accessors (`_store_package`, `_load_package`, `_iter_packages`) to back with PostgreSQL and S3.

At publish time the registry validates the bundle's SHA-256 hash against `manifest.bundle_hash`, verifies the manifest signature using the injected `SigningPort`, and records whether the package arrived signed (`signed_at_publish`). At install time it enforces the caller's `TrustConfig`: the signing key must appear in the trusted set, and if `verified_publishers_only=True` the hub-curated verified badge must be set. A 24-hour `verified_at_install` cache skips repeat signature verification for high-traffic packages.

The `ReputationScorer` ranks search results by `downloads × average_stars × age_decay`. The `TrustConfig` resolver follows the §11.16 lookup chain: `--trust-file` flag → `FLOWFORGE_TRUST_FILE` env → `~/.flowforge/trust.yaml` (via `platformdirs`) → `/etc/flowforge/trust.yaml` → `[tool.flowforge.trust]` in `pyproject.toml` → built-in empty default.

Admin routes (`demote`, `verified`) are gated by the `ADMIN_WRITE` permission. Two auth modes coexist: a `principal_extractor=` callable for per-user RBAC (E-73), and a legacy `admin_token=` shared-token bridge that accepts a comma-separated rotation list. Both can be active simultaneously for staged migration.

## Quick start

```python
import asyncio
from flowforge_signing_kms import HmacDevSigning
from flowforge_jtbd.registry.manifest import JtbdManifest
from flowforge_jtbd_hub import PackageRegistry, TrustConfig, create_app

signing = HmacDevSigning(secret="dev-secret-32-chars-minimum-ok!", key_id="key-v1")
registry = PackageRegistry(signing=signing)
app = create_app(registry, admin_token="my-admin-token")

# In tests — no port binding needed
import httpx
from httpx import ASGITransport

async def demo():
	async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		resp = await client.get("/api/jtbd-hub/packages")
		assert resp.status_code == 200
		print(resp.json())  # []

asyncio.run(demo())
```

## Public API

- `create_app(registry, *, admin_token=None, principal_extractor=None) -> FastAPI` — app factory.
- `PackageRegistry` — in-memory registry; subclass for persistent storage.
- `Package` — hub-stored package: manifest + tarball + lifecycle state.
- `PublishResult`, `InstallResult` — results from `registry.publish()` / `registry.install()`.
- `Rating` — one user rating (1–5 stars).
- `HubError` — base exception; subclasses: `PackageNotFoundError`, `PackageAlreadyExistsError`, `UnsignedManifestError`, `UntrustedSignatureError`, `TamperedPayloadError`.
- `TrustConfig`, `TrustedKey` — trust configuration models.
- `resolve_trust_config(**) -> TrustResolution` — §11.16 lookup chain.
- `ReputationScorer` — protocol; `DefaultReputationScorer` is the default.
- `Permission`, `Role`, `Principal`, `PrincipalExtractor` — E-73 RBAC types.
- `LEGACY_ADMIN_PRINCIPAL` — synthetic principal for the admin-token bridge.
- `role_permissions(role) -> frozenset[Permission]` — static role→permission map.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/jtbd-hub/packages` | open | Search (`q`, `domain`, `include_demoted`). |
| `GET` | `/api/jtbd-hub/packages/{name}/{version}` | open | Package metadata. |
| `POST` | `/api/jtbd-hub/packages/{name}/{version}/install` | open | Download + verify bundle. |
| `POST` | `/api/jtbd-hub/packages` | open | Publish (manifest + `bundle_b64`). |
| `POST` | `/api/jtbd-hub/packages/{name}/{version}/ratings` | open | Rate (1–5 stars per user). |
| `POST` | `/api/jtbd-hub/packages/{name}/{version}/demote` | `ADMIN_WRITE` | Demote with reason. |
| `POST` | `/api/jtbd-hub/packages/{name}/{version}/verified` | `ADMIN_WRITE` | Set/clear verified badge. |
| `GET` | `/health` | open | Liveness probe. |

## Trust file

Resolution order (§11.16):

1. `--trust-file <path>` flag.
2. `FLOWFORGE_TRUST_FILE` env var.
3. Platform-specific user config dir (via `platformdirs`) — e.g. `~/.config/flowforge/trust.yaml` on Linux, `~/Library/Application Support/flowforge/trust.yaml` on macOS.
4. Platform-specific system config dir.
5. `[tool.flowforge.trust]` in `pyproject.toml`.
6. Built-in default (empty trust set).

```yaml
trusted_signing_keys:
  - id: "kms:alias/flowforge-publisher"
    name: "Flowforge core team"
verified_publishers_only: false
trust_verified_badge: true
```

## Audit-2026 hardening

- **JH-01** (E-37b): `signed_at_publish` flag is stored at publish time. Install rejects unsigned packages by default; callers must pass `accept_unsigned=True` which emits a `PACKAGE_INSTALL_UNSIGNED` audit event. Error messages do not leak the signing `key_id` — pre-fix, cleartext error messages gave an attacker partial enumeration of the hub's trust set.
- **JH-02** (E-58): Download counter increments through the hookable `_increment_downloads()` method so production subclasses can issue an atomic SQL `UPDATE` and converge correctly across multiple replicas.
- **JH-03** (E-58): `verified_at_install` caches the timestamp of the most recent successful manifest re-verify. Repeat installs within the 24-hour window skip the verify call; a daily background job clears stale entries.
- **JH-04** (E-58): `admin_token` accepts a comma-separated rotation list; tokens are compared with `hmac.compare_digest`. Deploy with `"old,new"`, drop `old` after clients rotate. Audit events record `principal_kind="legacy_admin"` so migration to per-user RBAC can be tracked.
- **JH-05** (E-58): Trust file paths resolved via `platformdirs` instead of hard-coded `~/.flowforge` so they are correct on macOS and Windows as well as Linux.
- **JH-06** (E-58): YAML and TOML trust-config parsing catches only `yaml.YAMLError` / `pydantic.ValidationError` rather than bare `Exception`, so `KeyboardInterrupt` and unrelated bugs propagate rather than being re-wrapped as `TrustConfigError`.
- **E-73 phase 1–3**: `Permission`, `Role`, `Principal`, `PrincipalExtractor` types in `flowforge_jtbd_hub.rbac`; per-route permission gate via `_require_permission(Permission.ADMIN_WRITE)` dependency; backward-compatible `admin_token=` bridge coexists with `principal_extractor=` for staged rollout.

## Compatibility

- Python 3.11+
- `fastapi`
- `pydantic>=2`
- `pyyaml`
- `platformdirs`
- `flowforge-jtbd` (for `JtbdManifest` and manifest signing helpers)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-jtbd`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-jtbd) — provides `JtbdManifest` and manifest signing primitives
- [`flowforge-signing-kms`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-signing-kms) — `SigningPort` implementations used by `PackageRegistry`
- [`flowforge-cli`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-cli) — `flowforge jtbd fork` and publish/install CLI commands talk to this service
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
