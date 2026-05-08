"""flowforge-jtbd-hub — public registry service for signed JTBD packages.

Composes on top of :mod:`flowforge_jtbd.registry` (E-24 manifest +
signing layer): the registry domain wraps :class:`JtbdManifest` plus
the tarball blob, the reputation scorer aggregates downloads + stars,
the FastAPI app exposes publish / install / search / rate / demote
endpoints, and the trust resolver implements the §11.16 lookup chain.

Hosts that prefer to embed the hub in an existing FastAPI service can
import :func:`create_app` directly; the standalone reference deploy
(see ``apps/jtbd-hub/``, future) imports it the same way.
"""

from __future__ import annotations

from .app import create_app
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
	InstallResult,
	Package,
	PackageRegistry,
	PublishResult,
	Rating,
	UntrustedSignatureError,
)
from .reputation import (
	DefaultReputationScorer,
	ReputationScorer,
)
from .trust import (
	TrustConfig,
	TrustedKey,
	resolve_trust_config,
)

__version__ = "0.1.0"

__all__ = [
	"DefaultReputationScorer",
	"HubError",
	"InstallResult",
	"LEGACY_ADMIN_PRINCIPAL",
	"Package",
	"PackageRegistry",
	"Permission",
	"Principal",
	"PrincipalExtractor",
	"PublishResult",
	"Rating",
	"ReputationScorer",
	"Role",
	"TrustConfig",
	"TrustedKey",
	"UntrustedSignatureError",
	"__version__",
	"create_app",
	"resolve_trust_config",
	"role_permissions",
]
