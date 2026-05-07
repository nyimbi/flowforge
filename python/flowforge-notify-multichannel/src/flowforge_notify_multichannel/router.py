"""MultiChannelNotifier — implements NotificationPort.

Features:
- Template registry backed by Jinja2 with locale + timezone support
- Per-channel adapter dispatch (in_app, email, sms, push, webhook, slack)
- Recipient preference routing
- Per-(recipient, template_id) throttle window
- Deduplication via dedupe_key set
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, Undefined, sandbox

from flowforge.ports.types import NotificationSpec


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


@dataclass
class RecipientPreferences:
	"""Which channels a recipient accepts, and optional metadata per channel."""

	channels: list[str]
	timezone: str = "UTC"
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _ThrottleKey:
	recipient: str
	template_id: str


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------


def _make_jinja_env() -> Environment:
	"""Return a sandboxed Jinja2 environment.

	The sandbox disallows attribute traversal that could reach Python
	internals, keeping template rendering safe for user-supplied content.
	"""
	env: Environment = sandbox.SandboxedEnvironment(
		undefined=Undefined,
		autoescape=False,
	)
	return env


# ---------------------------------------------------------------------------
# MultiChannelNotifier
# ---------------------------------------------------------------------------


class MultiChannelNotifier:
	"""Multichannel NotificationPort implementation.

	Usage::

	    from flowforge_notify_multichannel import MultiChannelNotifier, FakeInAppAdapter, EmailAdapter

	    notifier = MultiChannelNotifier(
	        adapters=[FakeInAppAdapter(), EmailAdapter()],
	        throttle_seconds=60,
	    )
	    await notifier.register_template(spec)
	    subject, body = await notifier.render("welcome", "en", {"name": "Alice"})
	    await notifier.send("email", "alice@example.com", (subject, body))
	"""

	def __init__(
		self,
		adapters: list[Any] | None = None,
		throttle_seconds: int = 0,
		recipient_prefs: dict[str, RecipientPreferences] | None = None,
	) -> None:
		self._adapters: dict[str, Any] = {}
		for adapter in adapters or []:
			self._adapters[adapter.channel] = adapter

		self._templates: dict[str, dict[str, NotificationSpec]] = {}
		# throttle_seconds=0 disables throttling
		self._throttle_seconds = throttle_seconds
		# _throttle[key] = last_sent_ts
		self._throttle: dict[_ThrottleKey, float] = {}
		# dedupe set: (recipient, dedupe_key)
		self._dedupe: set[tuple[str, str]] = set()
		# recipient -> channel prefs
		self._prefs: dict[str, RecipientPreferences] = recipient_prefs or {}
		self._jinja = _make_jinja_env()
		# E-54 / NM-03: last timezone fallback breadcrumb for observability.
		# When a render() call falls back to UTC because the requested zone
		# is unknown, the originating exception is preserved here so a
		# tracing consumer can dump it into a structured log line.
		self.last_tz_fallback: dict[str, Any] | None = None

	# ------------------------------------------------------------------
	# NotificationPort
	# ------------------------------------------------------------------

	async def register_template(self, spec: NotificationSpec) -> None:
		"""Idempotent registration; locale-keyed within template_id."""
		by_locale = self._templates.setdefault(spec.template_id, {})
		by_locale[spec.locale] = spec

	async def render(
		self,
		template_id: str,
		locale: str,
		ctx: dict[str, Any],
	) -> tuple[str, str]:
		"""Render (subject, body) for *template_id* in *locale*.

		Falls back to "en" if the requested locale is not registered.
		Raises KeyError if no template exists at all.
		"""
		by_locale = self._templates.get(template_id)
		if by_locale is None:
			raise KeyError(f"Template not registered: {template_id!r}")

		spec = by_locale.get(locale) or by_locale.get("en") or next(iter(by_locale.values()))

		# Inject timezone-aware helpers into ctx if timezone metadata present
		tz_name = ctx.get("_timezone", "UTC")
		try:
			tz = ZoneInfo(tz_name)
		except (KeyError, ValueError, OSError) as exc:
			# E-54 / NM-03: a misconfigured timezone falls back to UTC
			# but the original exception is captured via __cause__ on
			# ``last_tz_fallback`` so tracing consumers can surface it.
			# ZoneInfoNotFoundError is a KeyError subclass; bad strings
			# raise ValueError; OS-level read failures raise OSError.
			tz = ZoneInfo("UTC")
			self.last_tz_fallback = {
				"requested": tz_name,
				"fallback": "UTC",
				"cause": exc,
				"message": f"unknown timezone {tz_name!r}; rendering with UTC",
			}
		render_ctx = {"_tz": tz, **ctx}

		subject = self._jinja.from_string(spec.subject_template).render(render_ctx)
		body = self._jinja.from_string(spec.body_template).render(render_ctx)
		return subject, body

	async def send(
		self,
		channel: str,
		recipient: str,
		rendered: tuple[str, str],
		*,
		metadata: dict[str, Any] | None = None,
		dedupe_key: str | None = None,
		template_id: str | None = None,
	) -> bool:
		"""Deliver *rendered* over *channel* to *recipient*.

		Returns True if delivery was attempted, False if skipped (throttle / dedup).
		Raises ValueError if no adapter for *channel* is registered.
		"""
		meta = metadata or {}

		# Deduplication
		if dedupe_key:
			dk = (recipient, dedupe_key)
			if dk in self._dedupe:
				return False
			self._dedupe.add(dk)

		# Throttle
		if self._throttle_seconds > 0 and template_id:
			tk = _ThrottleKey(recipient=recipient, template_id=template_id)
			last = self._throttle.get(tk)
			now = time.monotonic()
			if last is not None and (now - last) < self._throttle_seconds:
				return False
			self._throttle[tk] = now

		adapter = self._adapters.get(channel)
		if adapter is None:
			raise ValueError(f"No adapter registered for channel: {channel!r}")

		subject, body = rendered
		await adapter.deliver(recipient, subject, body, meta)
		return True

	# ------------------------------------------------------------------
	# Preference-based fanout
	# ------------------------------------------------------------------

	async def fanout(
		self,
		recipient: str,
		template_id: str,
		locale: str,
		ctx: dict[str, Any],
		*,
		metadata: dict[str, Any] | None = None,
		dedupe_key: str | None = None,
	) -> dict[str, bool]:
		"""Render and deliver across all channels in recipient's preferences.

		Returns a dict of channel -> sent (True/False/skipped).
		If no preferences registered for recipient, sends to all configured channels.
		"""
		prefs = self._prefs.get(recipient)
		channels: list[str]
		if prefs is not None:
			channels = prefs.channels
			tz_ctx = {"_timezone": prefs.timezone, **ctx}
		else:
			channels = list(self._adapters.keys())
			tz_ctx = ctx

		rendered = await self.render(template_id, locale, tz_ctx)
		results: dict[str, bool] = {}
		for ch in channels:
			if ch not in self._adapters:
				continue
			sent = await self.send(
				ch,
				recipient,
				rendered,
				metadata=metadata,
				dedupe_key=dedupe_key,
				template_id=template_id,
			)
			results[ch] = sent
		return results

	# ------------------------------------------------------------------
	# Adapter management
	# ------------------------------------------------------------------

	def register_adapter(self, adapter: Any) -> None:
		"""Register or replace an adapter for its channel."""
		self._adapters[adapter.channel] = adapter

	def register_preferences(self, recipient: str, prefs: RecipientPreferences) -> None:
		"""Register delivery preferences for a recipient."""
		self._prefs[recipient] = prefs

	def clear_dedupe(self) -> None:
		"""Clear the deduplication set (e.g. after a test)."""
		self._dedupe.clear()

	def clear_throttle(self) -> None:
		"""Clear the throttle state (e.g. after a test)."""
		self._throttle.clear()

	def dedupe_fingerprint(self, template_id: str, ctx: dict[str, Any]) -> str:
		"""Compute a stable dedup key from template_id + ctx values."""
		raw = template_id + "|" + "|".join(f"{k}={v}" for k, v in sorted(ctx.items()))
		return hashlib.sha256(raw.encode()).hexdigest()[:16]
