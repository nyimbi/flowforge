"""Tests for flowforge_outbox_pg.registry.HandlerRegistry."""

from __future__ import annotations

import pytest

from flowforge.ports.types import OutboxEnvelope
from flowforge_outbox_pg.registry import DispatchError, HandlerRegistry


def _env(kind: str = "test.event", tenant: str = "t1") -> OutboxEnvelope:
    return OutboxEnvelope(kind=kind, tenant_id=tenant, body={"x": 1})


# ---------------------------------------------------------------------------
# register + dispatch (happy path)
# ---------------------------------------------------------------------------


async def test_register_and_dispatch_calls_handler() -> None:
    reg = HandlerRegistry()
    calls: list[OutboxEnvelope] = []

    async def handler(env: OutboxEnvelope) -> None:
        calls.append(env)

    reg.register("test.event", handler)
    env = _env()
    await reg.dispatch(env)

    assert calls == [env]


async def test_dispatch_default_backend() -> None:
    reg = HandlerRegistry()
    called: list[str] = []

    async def h(env: OutboxEnvelope) -> None:
        called.append(env.kind)

    reg.register("foo.bar", h)
    await reg.dispatch(_env("foo.bar"))
    assert called == ["foo.bar"]


# ---------------------------------------------------------------------------
# multi-backend
# ---------------------------------------------------------------------------


async def test_multi_backend_registration() -> None:
    reg = HandlerRegistry()
    log: list[tuple[str, str]] = []

    async def email_handler(env: OutboxEnvelope) -> None:
        log.append(("email", env.kind))

    async def sms_handler(env: OutboxEnvelope) -> None:
        log.append(("sms", env.kind))

    reg.register("msg.send", email_handler, backend="email")
    reg.register("msg.send", sms_handler, backend="sms")

    await reg.dispatch(_env("msg.send"), backend="email")
    await reg.dispatch(_env("msg.send"), backend="sms")

    assert log == [("email", "msg.send"), ("sms", "msg.send")]


async def test_backends_are_independent() -> None:
    """A handler registered on backend A must not fire on backend B."""
    reg = HandlerRegistry()
    fired: list[str] = []

    async def h(env: OutboxEnvelope) -> None:
        fired.append("wrong")

    reg.register("ev", h, backend="a")

    with pytest.raises(DispatchError):
        await reg.dispatch(_env("ev"), backend="b")

    assert fired == []


# ---------------------------------------------------------------------------
# dispatch errors
# ---------------------------------------------------------------------------


async def test_dispatch_unregistered_kind_raises() -> None:
    reg = HandlerRegistry()
    with pytest.raises(DispatchError, match="[Nn]o handler"):
        await reg.dispatch(_env("unknown.kind"))


async def test_dispatch_wrong_backend_raises() -> None:
    reg = HandlerRegistry()

    async def h(env: OutboxEnvelope) -> None:
        pass

    reg.register("ev", h, backend="x")
    with pytest.raises(DispatchError):
        await reg.dispatch(_env("ev"), backend="y")


# ---------------------------------------------------------------------------
# overwrite
# ---------------------------------------------------------------------------


async def test_register_overwrites_existing_handler() -> None:
    reg = HandlerRegistry()
    results: list[str] = []

    async def h1(env: OutboxEnvelope) -> None:
        results.append("h1")

    async def h2(env: OutboxEnvelope) -> None:
        results.append("h2")

    reg.register("ev", h1)
    reg.register("ev", h2)  # overwrite
    await reg.dispatch(_env("ev"))

    assert results == ["h2"]


# ---------------------------------------------------------------------------
# decorator API
# ---------------------------------------------------------------------------


async def test_handler_decorator() -> None:
    reg = HandlerRegistry()
    seen: list[OutboxEnvelope] = []

    @reg.handler("decorated.event")
    async def h(env: OutboxEnvelope) -> None:
        seen.append(env)

    env = _env("decorated.event")
    await reg.dispatch(env)
    assert seen == [env]


# ---------------------------------------------------------------------------
# introspection
# ---------------------------------------------------------------------------


def test_list_kinds_empty() -> None:
    reg = HandlerRegistry()
    assert reg.list_kinds() == []


def test_list_kinds_returns_registered() -> None:
    reg = HandlerRegistry()

    async def noop(env: OutboxEnvelope) -> None:
        pass

    reg.register("a", noop)
    reg.register("b", noop)
    reg.register("c", noop, backend="other")

    kinds = reg.list_kinds()
    assert sorted(kinds) == ["a", "b"]
    assert reg.list_kinds("other") == ["c"]


def test_list_backends() -> None:
    reg = HandlerRegistry()

    async def noop(env: OutboxEnvelope) -> None:
        pass

    reg.register("x", noop, backend="alpha")
    reg.register("y", noop, backend="beta")

    backends = reg.list_backends()
    assert set(backends) == {"alpha", "beta"}


def test_has_handler_true_and_false() -> None:
    reg = HandlerRegistry()

    async def noop(env: OutboxEnvelope) -> None:
        pass

    reg.register("ev", noop)
    assert reg.has_handler("ev") is True
    assert reg.has_handler("ev", backend="other") is False
    assert reg.has_handler("missing") is False
