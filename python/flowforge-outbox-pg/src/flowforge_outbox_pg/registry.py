"""Handler registry — register/dispatch outbox handlers across named backends.

Mirrors the ``OutboxRegistry`` port from ``flowforge.ports.outbox`` but is a
concrete class, not an ABC, so it can be used standalone without importing
flowforge-core in test environments that prefer a minimal dependency set.

Multi-backend example::

    reg = HandlerRegistry()
    reg.register("email.send", send_email, backend="email")
    reg.register("sms.send", send_sms, backend="sms")
    await reg.dispatch(envelope, backend="email")
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from flowforge.ports.types import OutboxEnvelope

OutboxHandler = Callable[[OutboxEnvelope], Awaitable[None]]


class DispatchError(Exception):
    """Raised when no handler is registered for a (backend, kind) pair."""


class HandlerRegistry:
    """Concrete, multi-backend handler registry.

    Handlers are keyed by ``(backend, kind)`` so multiple messaging backends
    (e.g., ``dramatiq``, ``temporal``, ``inline``) can coexist without
    namespace collisions.

    Usage::

        reg = HandlerRegistry()

        @reg.handler("my.kind", backend="default")
        async def my_handler(env: OutboxEnvelope) -> None:
            ...

        await reg.dispatch(envelope)
    """

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], OutboxHandler] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        kind: str,
        handler: OutboxHandler,
        backend: str = "default",
    ) -> None:
        """Register *handler* for *kind* under *backend*.

        Re-registering the same ``(backend, kind)`` key overwrites the previous
        handler — this is intentional so tests can swap in stubs.
        """
        self._handlers[(backend, kind)] = handler

    def handler(
        self,
        kind: str,
        backend: str = "default",
    ) -> Callable[[OutboxHandler], OutboxHandler]:
        """Decorator shorthand for ``register``."""

        def decorator(fn: OutboxHandler) -> OutboxHandler:
            self.register(kind, fn, backend=backend)
            return fn

        return decorator

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        envelope: OutboxEnvelope,
        backend: str = "default",
    ) -> None:
        """Dispatch *envelope* to the matching handler.

        Raises ``DispatchError`` if no handler is registered for
        ``(backend, envelope.kind)``.
        """
        key = (backend, envelope.kind)
        handler = self._handlers.get(key)
        if handler is None:
            raise DispatchError(
                f"No handler registered for kind={envelope.kind!r} backend={backend!r}. "
                f"Registered: {self.list_kinds(backend)}"
            )
        await handler(envelope)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_kinds(self, backend: str = "default") -> list[str]:
        """Return all registered kind strings for *backend*."""
        return [kind for (b, kind) in self._handlers if b == backend]

    def list_backends(self) -> list[str]:
        """Return all backend names that have at least one registered handler."""
        seen: list[str] = []
        for backend, _ in self._handlers:
            if backend not in seen:
                seen.append(backend)
        return seen

    def has_handler(self, kind: str, backend: str = "default") -> bool:
        """Return ``True`` if a handler exists for ``(backend, kind)``."""
        return (backend, kind) in self._handlers

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        backends = self.list_backends()
        total = len(self._handlers)
        return f"<HandlerRegistry backends={backends} total_handlers={total}>"


__all__ = ["DispatchError", "HandlerRegistry", "OutboxHandler"]
