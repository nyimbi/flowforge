# flowforge-jtbd-hub

E-24 deliverable — public registry service for signed JTBD packages.

A FastAPI service plus the supporting domain layer (`PackageManifest`,
`PackageRegistry`, trust-file resolution, reputation scorer). The CLI
publish/install/search commands talk to it; consumers verify package
signatures against their `~/.flowforge/trust.yaml` before installing.

## Surfaces

- `flowforge_jtbd_hub.manifest` — `PackageManifest`, `PackageFile`,
  `compute_manifest_signing_payload(manifest)` (canonical-JSON bytes
  hashed by the signing port).
- `flowforge_jtbd_hub.registry` — `PackageRegistry`,
  `Package`, `Rating` plus the publish / install / search / rate /
  demote operations.
- `flowforge_jtbd_hub.reputation` — `ReputationScorer` Protocol with
  a `DefaultReputationScorer` (downloads × average-stars × age-decay).
- `flowforge_jtbd_hub.trust` — `TrustConfig` plus
  `resolve_trust_config(...)` for the per-flag / env / user / system /
  pyproject lookup chain (per arch §11.16).
- `flowforge_jtbd_hub.app` — `create_app(registry, signing, *,
  admin_token=...)` returns a FastAPI instance with the documented
  endpoints.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/jtbd-hub/packages` | Search (q, domain, include_demoted) |
| GET | `/api/jtbd-hub/packages/{name}/{version}` | Package metadata |
| GET | `/api/jtbd-hub/packages/{name}/{version}/payload` | Tarball download (increments download counter) |
| POST | `/api/jtbd-hub/packages` | Publish (multipart-style JSON: manifest + tarball base64) |
| POST | `/api/jtbd-hub/packages/{name}/{version}/ratings` | Rate (1–5 stars per user) |
| POST | `/api/jtbd-hub/packages/{name}/{version}/demote` | Admin demote (admin_token-gated) |
| POST | `/api/jtbd-hub/packages/{name}/{version}/verified` | Admin verify badge |

Tarballs are exchanged as base64 JSON to keep the example wire-format
small + httpx-friendly. A multipart variant is straightforward; the
JSON shape is what tests pin.

## Trust file

Resolution order (per arch §11.16):

1. `--trust-file <path>` flag (CLI only).
2. `FLOWFORGE_TRUST_FILE` environment variable.
3. `~/.flowforge/trust.yaml` (per-user).
4. `/etc/flowforge/trust.yaml` (system).
5. `[tool.flowforge.trust]` in `pyproject.toml`.
6. Built-in default (empty trust set).

Schema:

```yaml
trusted_signing_keys:
  - id: "kms:alias/flowforge-publisher"
    name: "Flowforge core team"
verified_publishers_only: false
trust_verified_badge: true
```

## Tests

```
uv run --package flowforge-jtbd-hub --extra test pytest python/flowforge-jtbd-hub/tests
```

The FastAPI app is exercised through `httpx.AsyncClient` with
`httpx.ASGITransport(app=app)` so no port is bound during tests.
