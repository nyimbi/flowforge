"""Canonical pydantic models for ``JtbdSpec`` and ``JtbdBundle``.

These models pin the wire format that the generator, linter, lockfile,
and storage layer all read. They mirror the JSON-schema shipped in
``flowforge.dsl.schema.jtbd-1.0.schema.json`` but live as typed pydantic
classes so the rest of the framework can exchange real objects rather
than open dicts.

Design notes:

* ``model_config`` uses ``extra='forbid'`` to catch typos at validation
  time. The lint-facing models in :mod:`flowforge_jtbd.spec` keep
  ``extra='allow'`` because they consume forward-evolving payloads;
  the canonical contract must reject unknown keys so a typo never
  silently roundtrips through publish.
* ``Annotated[..., AfterValidator(...)]`` carries the ``pii``-on-
  sensitive-kinds gate; the JSON schema carries the same rule via
  ``allOf/if/then`` (see ``framework/docs/jtbd-editor-arch.md`` §23.5).
* ``spec_hash`` and ``parent_version_id`` are recorded on
  :class:`JtbdSpec`; the bundle wrapper :class:`JtbdBundle` does not
  carry a hash of its own — that is the lockfile's job.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
	AfterValidator,
	BaseModel,
	ConfigDict,
	Field,
	model_validator,
)

# Field kinds whose value is treated as personally-identifying or
# otherwise sensitive by default. Matches the JSON-schema enum in
# ``jtbd-1.0.schema.json``.
SENSITIVE_FIELD_KINDS: frozenset[str] = frozenset(
	{"email", "phone", "party_ref", "signature", "file", "address", "text", "textarea"}
)

FieldKind = Literal[
	"text",
	"number",
	"money",
	"date",
	"datetime",
	"enum",
	"boolean",
	"party_ref",
	"document_ref",
	"email",
	"phone",
	"address",
	"textarea",
	"signature",
	"file",
]

EdgeCaseHandle = Literal["branch", "reject", "escalate", "compensate", "loop"]
ApprovalPolicy = Literal["1_of_1", "2_of_2", "n_of_m", "authority_tier"]
NotificationTrigger = Literal[
	"state_enter",
	"state_exit",
	"sla_warn",
	"sla_breach",
	"approved",
	"rejected",
	"escalated",
]
NotificationChannel = Literal["email", "sms", "slack", "webhook", "in_app"]
TenancyMode = Literal["none", "single", "multi"]
DataSensitivity = Literal["PII", "PHI", "PCI", "secrets", "regulated"]
ComplianceRegime = Literal[
	"GDPR",
	"SOX",
	"HIPAA",
	"PCI-DSS",
	"ISO27001",
	"SOC2",
	"NIST-800-53",
	"CCPA",
]

JtbdSpecStatus = Literal[
	"draft",
	"in_review",
	"published",
	"deprecated",
	"archived",
]


def _semver(value: str) -> str:
	"""Strict semver guard backed by :mod:`packaging.version`.

	audit-2026 J-09: the previous implementation accepted ``"1.0.0-"``
	(empty pre-release suffix) because it only checked that the digit
	parts looked numeric. ``packaging.version.Version`` enforces the
	full PEP 440 / semver shape — empty suffixes, leading zeros in
	pre-release segments, and other malformed inputs all raise
	``InvalidVersion``.

	We additionally require the bare ``MAJOR.MINOR.PATCH`` triple to be
	present (``packaging.Version`` accepts ``"1.0"`` for example). This
	matches the JTBD spec's documented contract.
	"""

	from packaging.version import InvalidVersion, Version

	if not value:
		raise ValueError("version must be non-empty")
	core = value.split("-", 1)[0].split("+", 1)[0]
	parts = core.split(".")
	if len(parts) != 3 or not all(p.isdigit() and p == str(int(p)) for p in parts):
		raise ValueError(
			"version must look like 'MAJOR.MINOR.PATCH' with optional"
			f" pre-release/build suffix; got {value!r}"
		)
	# Reject empty suffix shapes ("1.0.0-", "1.0.0+") that the simple
	# split above would otherwise let through.
	if value.endswith("-") or value.endswith("+"):
		raise ValueError(
			f"version has empty pre-release/build suffix: {value!r}"
		)
	try:
		Version(value)
	except InvalidVersion as exc:
		raise ValueError(
			f"version is not a valid PEP 440 / semver: {value!r} ({exc})"
		) from exc
	return value


def _spec_hash_format(value: str) -> str:
	"""Validate the ``sha256:<64 hex>`` shape used for ``spec_hash``."""
	if not value.startswith("sha256:"):
		raise ValueError(
			"spec_hash must be prefixed with 'sha256:'; got " + repr(value)
		)
	digest = value.split(":", 1)[1]
	if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
		raise ValueError(
			"spec_hash digest must be 64 lowercase hex chars; got " + repr(digest)
		)
	return value


def _id_pattern(value: str) -> str:
	"""Snake-case identifier pattern shared by jtbd_id, package, etc.

	ASCII-only — ``str.islower()`` and ``str.isalpha()`` accept Unicode
	letters like ``é`` and ``α``, which would let cross-script identifiers
	(e.g. ``café_run``) slip past validation. Audit E-64 / IT-04 class 3
	requires the validator to reject every non-ASCII identifier.
	"""
	if (
		not value
		or not value[0].isascii()
		or not ("a" <= value[0] <= "z")
	):
		raise ValueError("id must start with an ASCII lowercase letter")
	for ch in value:
		if not (
			ch.isascii()
			and (("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "_")
		):
			raise ValueError(
				"id must contain only ASCII lowercase letters, digits, and underscores"
				f"; got {value!r}"
			)
	return value


SemverStr = Annotated[str, AfterValidator(_semver)]
SpecHashStr = Annotated[str, AfterValidator(_spec_hash_format)]
IdStr = Annotated[str, AfterValidator(_id_pattern)]


class JtbdActor(BaseModel):
	"""Who acts on the JTBD."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	role: str
	department: str | None = None
	external: bool = False


class JtbdField(BaseModel):
	"""One captured field on a JTBD.

	``pii`` is mandatory for kinds in :data:`SENSITIVE_FIELD_KINDS`.
	The validator runs after ``model_validate`` populates the field so
	it sees both the kind and the explicit ``pii`` value (or its
	default).
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	id: str
	kind: FieldKind
	label: str | None = None
	required: bool = False
	pii: bool | None = None
	validation: dict[str, Any] | None = None
	sensitivity: list[DataSensitivity] = Field(default_factory=list)

	@model_validator(mode="after")
	def _check_pii_required_on_sensitive_kinds(self) -> "JtbdField":
		if self.kind in SENSITIVE_FIELD_KINDS and self.pii is None:
			raise ValueError(
				f"field {self.id!r} of kind {self.kind!r} must declare pii"
				" explicitly (true or false)"
			)
		return self


class JtbdEdgeCase(BaseModel):
	"""One pre-identified deviation from the happy path."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	id: str
	condition: str
	handle: EdgeCaseHandle
	branch_to: str | None = None

	@model_validator(mode="after")
	def _branch_target_required_when_branching(self) -> "JtbdEdgeCase":
		if self.handle == "branch" and not self.branch_to:
			raise ValueError(
				f"edge_case {self.id!r}: handle='branch' requires branch_to"
			)
		return self


class JtbdDocReq(BaseModel):
	"""One document requirement on a JTBD."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	kind: str
	min: int = 1
	max: int | None = None
	freshness_days: int | None = None
	av_required: bool = True


class JtbdApproval(BaseModel):
	"""One approval lane on the JTBD."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	role: str
	policy: ApprovalPolicy
	n: int | None = None
	tier: int | None = None

	@model_validator(mode="after")
	def _policy_specific_fields(self) -> "JtbdApproval":
		if self.policy == "n_of_m" and self.n is None:
			raise ValueError("approval policy 'n_of_m' requires field 'n'")
		if self.policy == "authority_tier" and self.tier is None:
			raise ValueError("approval policy 'authority_tier' requires field 'tier'")
		return self


class JtbdSla(BaseModel):
	"""SLA configuration for a JTBD."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	warn_pct: int | None = Field(default=None, ge=1, le=99)
	breach_seconds: int | None = Field(default=None, ge=60)


class JtbdNotification(BaseModel):
	"""One notification rule on a JTBD."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	trigger: NotificationTrigger
	channel: NotificationChannel
	audience: str


class JtbdSpec(BaseModel):
	"""Canonical JTBD spec (one job).

	The hash + version metadata at the head of this model is what
	makes a JTBD content-addressable. ``spec_hash`` is computed via
	:func:`flowforge_jtbd.dsl.canonical.spec_hash` over the *body* of
	the spec — ``id`` plus everything after but excluding the hash
	itself, ``parent_version_id``, ``status``, and audit metadata.
	The :meth:`compute_hash` helper does the right thing.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	# --- identity ---
	id: IdStr
	title: str | None = None
	version: SemverStr = "1.0.0"
	spec_hash: SpecHashStr | None = None
	parent_version_id: str | None = None
	replaced_by: str | None = None
	status: JtbdSpecStatus = "draft"

	# --- jtbd body ---
	actor: JtbdActor
	situation: str
	motivation: str
	outcome: str
	success_criteria: list[str] = Field(default_factory=list, min_length=1)
	edge_cases: list[JtbdEdgeCase] = Field(default_factory=list)
	data_capture: list[JtbdField] = Field(default_factory=list)
	documents_required: list[JtbdDocReq] = Field(default_factory=list)
	approvals: list[JtbdApproval] = Field(default_factory=list)
	sla: JtbdSla | None = None
	notifications: list[JtbdNotification] = Field(default_factory=list)
	metrics: list[str] = Field(default_factory=list)

	# --- governance ---
	requires: list[str] = Field(default_factory=list)
	compliance: list[ComplianceRegime] = Field(default_factory=list)
	data_sensitivity: list[DataSensitivity] = Field(default_factory=list)

	# --- audit (set by storage layer; spec authors don't fill these) ---
	created_by: str | None = None
	published_by: str | None = None

	def hash_body(self) -> dict[str, Any]:
		"""Return the canonical-JSON body used for ``spec_hash``.

		The body intentionally excludes:

		* ``spec_hash`` (the hash of itself; would create a fixed-point
		  problem).
		* ``parent_version_id`` (assigned by the storage layer at
		  publish time; not part of the author's intent).
		* ``status`` (lifecycle state machine; orthogonal to content).
		* ``created_by`` / ``published_by`` (audit metadata).

		Everything else is included; the ``id`` and ``version`` are
		first-class identity inputs and must move the hash.
		"""
		dumped = self.model_dump(mode="json", exclude_none=False)
		for excluded in (
			"spec_hash",
			"parent_version_id",
			"status",
			"created_by",
			"published_by",
		):
			dumped.pop(excluded, None)
		return dumped

	def compute_hash(self) -> str:
		"""Return the freshly-computed ``sha256:...`` for this spec.

		Stateless — does not mutate ``self.spec_hash``. Use
		:meth:`with_hash` if you want a copy with the field populated.
		"""
		from .canonical import spec_hash as _spec_hash

		return _spec_hash(self.hash_body())

	def with_hash(self) -> "JtbdSpec":
		"""Return a copy with ``spec_hash`` populated."""
		return self.model_copy(update={"spec_hash": self.compute_hash()})


FormRendererMode = Literal["skeleton", "real"]


class JtbdFrontend(BaseModel):
	"""Bundle-level frontend authoring options.

	Additive in v0.3.0 W1 (item 13 of ``docs/improvements.md``). The
	``form_renderer`` knob picks the Step.tsx emission path:

	* ``"skeleton"`` (default): the legacy stub component that renders
	  field labels with ``<dd>—</dd>`` placeholders. All pre-W1 bundles
	  default here, preserving byte-identical regen for existing
	  examples.
	* ``"real"``: emit a working ``FormRenderer`` invocation against the
	  per-JTBD ``form_spec.json`` plus client-side validators derived
	  from ``data_capture[].validation``. ``show_if`` conditional
	  visibility, PII visual treatment, and inline ``aria-describedby``
	  error wiring activate on this path.

	The schema-side mirror lives in
	``flowforge.dsl.schema.jtbd-1.0.schema.json`` under
	``project.properties.frontend``.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	form_renderer: FormRendererMode = "skeleton"


class JtbdProject(BaseModel):
	"""Bundle-level project metadata."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	name: str
	package: IdStr
	domain: str
	tenancy: TenancyMode = "single"
	languages: list[str] = Field(default_factory=list)
	currencies: list[str] = Field(default_factory=list)
	frontend_framework: Literal["nextjs", "remix", "vite-react"] = "nextjs"
	frontend: JtbdFrontend | None = None
	compliance: list[ComplianceRegime] = Field(default_factory=list)
	data_sensitivity: list[DataSensitivity] = Field(default_factory=list)


class JtbdShared(BaseModel):
	"""Bundle-level shared metadata: roles, permissions, entities."""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	roles: list[str] = Field(default_factory=list)
	permissions: list[str] = Field(default_factory=list)
	entities: list[dict[str, Any]] = Field(default_factory=list)


class JtbdBundle(BaseModel):
	"""A project bundle wrapping ``project`` + ``shared`` + ``jtbds``.

	A bundle is the unit a tenant publishes (``flowforge jtbd publish``)
	or installs (``flowforge jtbd install``). The lockfile pins the
	resolved versions of every JTBD it composes.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	project: JtbdProject
	shared: JtbdShared = Field(default_factory=JtbdShared)
	jtbds: list[JtbdSpec] = Field(default_factory=list, min_length=1)

	@model_validator(mode="after")
	def _unique_jtbd_ids(self) -> "JtbdBundle":
		seen: set[str] = set()
		for spec in self.jtbds:
			if spec.id in seen:
				raise ValueError(
					f"duplicate jtbd id {spec.id!r} in bundle {self.project.package!r}"
				)
			seen.add(spec.id)
		return self

	def find(self, jtbd_id: str) -> JtbdSpec | None:
		"""Return the JTBD with this id, or ``None``."""
		for spec in self.jtbds:
			if spec.id == jtbd_id:
				return spec
		return None

	def by_id(self) -> dict[str, JtbdSpec]:
		"""Lookup table keyed by ``id``."""
		return {spec.id: spec for spec in self.jtbds}

	def with_hashes(self) -> "JtbdBundle":
		"""Return a copy where every JTBD has ``spec_hash`` populated."""
		new_jtbds = [spec.with_hash() for spec in self.jtbds]
		return self.model_copy(update={"jtbds": new_jtbds})


__all__ = [
	"ApprovalPolicy",
	"ComplianceRegime",
	"DataSensitivity",
	"EdgeCaseHandle",
	"FieldKind",
	"FormRendererMode",
	"JtbdActor",
	"JtbdApproval",
	"JtbdBundle",
	"JtbdDocReq",
	"JtbdEdgeCase",
	"JtbdField",
	"JtbdFrontend",
	"JtbdNotification",
	"JtbdProject",
	"JtbdShared",
	"JtbdSla",
	"JtbdSpec",
	"JtbdSpecStatus",
	"NotificationChannel",
	"NotificationTrigger",
	"SENSITIVE_FIELD_KINDS",
	"SemverStr",
	"SpecHashStr",
	"TenancyMode",
]
