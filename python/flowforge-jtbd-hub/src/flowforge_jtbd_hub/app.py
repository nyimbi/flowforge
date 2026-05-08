"""FastAPI application for jtbd-hub.

Endpoints (canonical wire shape — multipart variants are layered on
top in deployments that need them):

* ``GET  /api/jtbd-hub/packages`` — search.
* ``GET  /api/jtbd-hub/packages/{name}/{version}`` — package detail.
* ``GET  /api/jtbd-hub/packages/{name}/{version}/payload`` — download
  the bundle bytes (base64 in the JSON body; tarballs in production
  would stream binary, but JSON keeps tests trivial).
* ``POST /api/jtbd-hub/packages`` — publish.
* ``POST /api/jtbd-hub/packages/{name}/{version}/ratings`` — rate.
* ``POST /api/jtbd-hub/packages/{name}/{version}/demote`` — admin
  demote (admin_token-gated).
* ``POST /api/jtbd-hub/packages/{name}/{version}/verified`` — admin
  flip the verified badge.

The trust set used at install time is read from the request body so
the same hub instance can serve clients with different trust policies.
``allow_untrusted`` query param opts out of the signature gate; the
client only uses it for explicit ``flowforge jtbd install --allow-
untrusted`` invocations.
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from flowforge_jtbd.registry.manifest import JtbdManifest
from pydantic import BaseModel, ConfigDict, Field

from .rbac import (
	LEGACY_ADMIN_PRINCIPAL,
	Permission,
	Principal,
	PrincipalExtractor,
	Role,
	role_permissions,
)
from .registry import (
	HubError,
	PackageAlreadyExistsError,
	PackageNotFoundError,
	PackageRegistry,
	TamperedPayloadError,
	UnsignedManifestError,
	UntrustedSignatureError,
)
from .trust import TrustConfig


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class PublishRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	manifest: JtbdManifest
	bundle_b64: str
	allow_unsigned: bool = False


class PackageSummary(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: str
	version: str
	description: str | None = None
	author: str | None = None
	tags: list[str] = Field(default_factory=list)
	published_at: str
	demoted: bool
	verified: bool
	downloads: int
	average_stars: float
	rating_count: int
	reputation: float


class PackageDetail(PackageSummary):
	manifest: JtbdManifest
	demote_reason: str | None = None


class InstallResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	manifest: JtbdManifest
	bundle_b64: str
	verified_signature: bool
	demoted: bool


class RateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	user_id: str
	stars: int


class DemoteRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	reason: str


class VerifiedRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	verified: bool = True


# ---------------------------------------------------------------------------
# Auth shim
# ---------------------------------------------------------------------------


class _AuthHeaderRequest:
	"""Thin shim passed to ``PrincipalExtractor`` callables.

	Surfaces the ``Authorization`` header on a `headers`-like attribute
	without requiring an actual FastAPI ``Request`` object. Extractors
	that need the full request can ignore this and accept ``Request``
	directly via FastAPI's dependency injection (the route then routes
	the real request through ``_resolve_principal``).
	"""

	__slots__ = ("authorization",)

	def __init__(self, authorization: str | None) -> None:
		self.authorization = authorization

	@property
	def headers(self) -> dict[str, str]:
		if self.authorization is None:
			return {}
		return {"Authorization": self.authorization, "authorization": self.authorization}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
	registry: PackageRegistry,
	*,
	admin_token: str | None = None,
	principal_extractor: PrincipalExtractor | None = None,
) -> FastAPI:
	"""Build a FastAPI instance bound to *registry*.

	Authentication and authorisation:

	* ``principal_extractor`` (E-73) — Pluggable callable that resolves
	  ``Authorization`` headers into a :class:`flowforge_jtbd_hub.rbac.Principal`.
	  When set, every admin route enforces a per-permission gate
	  (`require_permission(Permission.ADMIN_WRITE)`) and audit events
	  carry the principal's user_id. Returns ``None`` for unauthenticated
	  requests; the gate maps that to a 401.

	* ``admin_token`` (E-58 legacy bridge) — Backward-compatible
	  shared-token mode. Single token OR a comma-separated list (rotation
	  support: deploy with ``"old,new"``, drop ``old`` after clients flip).
	  Whitespace stripped per token. Any valid token grants the
	  synthetic :data:`LEGACY_ADMIN_PRINCIPAL` (`hub_admin` role,
	  ``principal_kind="legacy_admin"``); audit events record that kind so
	  ops can monitor migration to per-user RBAC.

	  ``principal_extractor`` and ``admin_token`` MAY be set together —
	  both are tried in order (extractor first, legacy bridge second).
	  This supports staged rollout: turn on the extractor while keeping
	  legacy admins working.

	* When neither is set, admin endpoints are open (dev mode only).
	"""
	# E-58 / JH-04: parse the rotation list once at app build time.
	allowed_tokens: tuple[str, ...] = ()
	if admin_token is not None:
		allowed_tokens = tuple(
			t.strip() for t in admin_token.split(",") if t.strip()
		)
		assert allowed_tokens, "admin_token must contain at least one non-empty value"

	app = FastAPI(title="flowforge-jtbd-hub")

	def _legacy_token_principal(authorization: str | None) -> Principal | None:
		"""Map ``Authorization: Bearer <legacy-token>`` to the synthetic
		legacy-admin Principal if the offered token is in the rotation
		list. Returns None if the legacy bridge is disabled or the
		header doesn't match. Constant-time comparison via
		``hmac.compare_digest``.
		"""
		if not allowed_tokens:
			return None
		if not authorization or not authorization.startswith("Bearer "):
			return None
		offered = authorization[len("Bearer ") :]
		import hmac as _hmac

		for valid in allowed_tokens:
			if _hmac.compare_digest(offered, valid):
				return LEGACY_ADMIN_PRINCIPAL
		return None

	def _resolve_principal(
		authorization: str | None,
		request: Any | None = None,
	) -> Principal | None:
		"""E-73: resolve a Principal from the request.

		Order: ``principal_extractor`` first (per-user RBAC), then the
		legacy admin-token bridge. Returns None if neither matched.
		"""
		# Prefer the per-user extractor when configured. If it raises
		# (bad token format, KMS error), surface as 401.
		if principal_extractor is not None:
			# Some extractors only need the Authorization header; pass
			# the full request via attribute injection on a thin shim
			# so legacy callers don't need to migrate at once.
			extractor_arg = request if request is not None else _AuthHeaderRequest(authorization)
			try:
				principal = principal_extractor(extractor_arg)
			except Exception:
				principal = None
			if principal is not None:
				return principal
		# Fall through to the legacy bridge.
		return _legacy_token_principal(authorization)

	def _require_admin(
		authorization: str | None = Header(default=None),
	) -> Principal:
		"""E-73 / E-58 backward-compat: authenticate any admin route.

		Returns a :class:`Principal`. Routes that need finer permission
		distinctions use :func:`_require_permission` instead. When
		neither principal_extractor nor admin_token is configured, this
		dependency returns the legacy admin Principal as a permissive
		default (dev mode); enabling either tightens the gate.
		"""
		if principal_extractor is None and not allowed_tokens:
			# Dev mode (no auth configured) — match historical open behaviour
			# but emit a synthetic principal so audit hooks have something
			# to record.
			return LEGACY_ADMIN_PRINCIPAL
		principal = _resolve_principal(authorization)
		if principal is None:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="missing or invalid admin token",
			)
		return principal

	def _require_permission(perm: Permission):
		"""E-73 dependency factory. Returns a FastAPI dependency that
		checks the resolved Principal carries ``perm``. 401 if no
		principal; 403 if authenticated but unauthorised.
		"""

		def _checker(
			authorization: str | None = Header(default=None),
		) -> Principal:
			# Dev mode: same permissive fallback as _require_admin.
			if principal_extractor is None and not allowed_tokens:
				return LEGACY_ADMIN_PRINCIPAL
			principal = _resolve_principal(authorization)
			if principal is None:
				raise HTTPException(
					status_code=status.HTTP_401_UNAUTHORIZED,
					detail="authentication required",
				)
			if not principal.has(perm):
				raise HTTPException(
					status_code=status.HTTP_403_FORBIDDEN,
					detail=f"principal lacks {perm.value!r}",
				)
			return principal

		return _checker

	# ------------------------------------------------------------------
	# search
	# ------------------------------------------------------------------

	@app.get(
		"/api/jtbd-hub/packages",
		response_model=list[PackageSummary],
	)
	def search_packages(
		q: str | None = Query(default=None),
		domain: str | None = Query(default=None),
		include_demoted: bool = Query(default=False),
	) -> list[PackageSummary]:
		results = registry.search(
			query=q,
			domain=domain,
			include_demoted=include_demoted,
		)
		return [_to_summary(registry, pkg) for pkg in results]

	# ------------------------------------------------------------------
	# detail
	# ------------------------------------------------------------------

	@app.get(
		"/api/jtbd-hub/packages/{name}/{version}",
		response_model=PackageDetail,
	)
	def get_package(name: str, version: str) -> PackageDetail:
		try:
			pkg = registry.get(name, version)
		except PackageNotFoundError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=str(exc),
			)
		summary = _to_summary(registry, pkg)
		return PackageDetail(
			**summary.model_dump(),
			manifest=pkg.manifest,
			demote_reason=pkg.demote_reason,
		)

	# ------------------------------------------------------------------
	# install
	# ------------------------------------------------------------------

	@app.post(
		"/api/jtbd-hub/packages/{name}/{version}/install",
		response_model=InstallResponse,
	)
	async def install_package(
		name: str,
		version: str,
		trust: TrustConfig = Body(default_factory=TrustConfig),
		allow_untrusted: bool = Query(default=False),
	) -> InstallResponse:
		try:
			result = await registry.install(
				name,
				version,
				trust=trust,
				allow_untrusted=allow_untrusted,
			)
		except PackageNotFoundError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
			)
		except UntrustedSignatureError as exc:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
			)
		except TamperedPayloadError as exc:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT, detail=str(exc)
			)
		except HubError as exc:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
			)
		# Re-load to surface the demoted flag in the response.
		pkg = registry.get(name, version)
		return InstallResponse(
			manifest=result.manifest,
			bundle_b64=base64.b64encode(result.bundle).decode("ascii"),
			verified_signature=result.verified_signature,
			demoted=pkg.demoted,
		)

	# ------------------------------------------------------------------
	# publish
	# ------------------------------------------------------------------

	@app.post(
		"/api/jtbd-hub/packages",
		response_model=PackageDetail,
		status_code=status.HTTP_201_CREATED,
	)
	async def publish_package(payload: PublishRequest) -> PackageDetail:
		try:
			bundle = base64.b64decode(payload.bundle_b64)
		except Exception as exc:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"bundle_b64 is not valid base64: {exc}",
			)
		try:
			result = await registry.publish(
				payload.manifest,
				bundle,
				allow_unsigned=payload.allow_unsigned,
			)
		except PackageAlreadyExistsError as exc:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT, detail=str(exc)
			)
		except UnsignedManifestError as exc:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
			)
		except TamperedPayloadError as exc:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
			)
		except HubError as exc:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
			)
		pkg = result.package
		summary = _to_summary(registry, pkg)
		return PackageDetail(
			**summary.model_dump(),
			manifest=pkg.manifest,
			demote_reason=pkg.demote_reason,
		)

	# ------------------------------------------------------------------
	# rate
	# ------------------------------------------------------------------

	@app.post(
		"/api/jtbd-hub/packages/{name}/{version}/ratings",
		status_code=status.HTTP_201_CREATED,
	)
	async def rate_package(
		name: str,
		version: str,
		payload: RateRequest,
	) -> dict[str, Any]:
		try:
			rating = await registry.rate(
				name, version, user_id=payload.user_id, stars=payload.stars
			)
		except ValueError as exc:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=str(exc),
			)
		except PackageNotFoundError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
			)
		pkg = registry.get(name, version)
		return {
			"user_id": rating.user_id,
			"stars": rating.stars,
			"created_at": rating.created_at.isoformat(),
			"average_stars": round(pkg.average_stars, 3),
			"rating_count": pkg.rating_count,
		}

	# ------------------------------------------------------------------
	# demote (admin)
	# ------------------------------------------------------------------

	@app.post(
		"/api/jtbd-hub/packages/{name}/{version}/demote",
		response_model=PackageDetail,
	)
	async def demote_package(
		name: str,
		version: str,
		payload: DemoteRequest,
		principal: Principal = Depends(_require_permission(Permission.ADMIN_WRITE)),
	) -> PackageDetail:
		try:
			pkg = await registry.demote(name, version, reason=payload.reason)
		except PackageNotFoundError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
			)
		summary = _to_summary(registry, pkg)
		return PackageDetail(
			**summary.model_dump(),
			manifest=pkg.manifest,
			demote_reason=pkg.demote_reason,
		)

	# ------------------------------------------------------------------
	# verified badge (admin)
	# ------------------------------------------------------------------

	@app.post(
		"/api/jtbd-hub/packages/{name}/{version}/verified",
		response_model=PackageDetail,
	)
	async def set_verified(
		name: str,
		version: str,
		payload: VerifiedRequest,
		principal: Principal = Depends(_require_permission(Permission.ADMIN_WRITE)),
	) -> PackageDetail:
		try:
			pkg = await registry.mark_verified(
				name, version, verified=payload.verified
			)
		except PackageNotFoundError as exc:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
			)
		summary = _to_summary(registry, pkg)
		return PackageDetail(
			**summary.model_dump(),
			manifest=pkg.manifest,
			demote_reason=pkg.demote_reason,
		)

	# ------------------------------------------------------------------
	# health
	# ------------------------------------------------------------------

	@app.get("/health")
	def health() -> JSONResponse:
		return JSONResponse({"status": "ok"})

	return app


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_summary(registry: PackageRegistry, pkg: Any) -> PackageSummary:
	return PackageSummary(
		name=pkg.name,
		version=pkg.version,
		description=pkg.manifest.description,
		author=pkg.manifest.author,
		tags=list(pkg.manifest.tags),
		published_at=pkg.published_at.isoformat(),
		demoted=pkg.demoted,
		verified=pkg.verified,
		downloads=pkg.downloads,
		average_stars=round(pkg.average_stars, 3),
		rating_count=pkg.rating_count,
		reputation=registry.reputation(pkg),
	)


__all__ = ["create_app"]
