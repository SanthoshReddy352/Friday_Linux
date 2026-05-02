"""Tests for RuntimeKernel + ServiceContainer — Phase 6 (v2)."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from core.bootstrap.lifecycle import LifecycleManager  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from core.kernel.runtime import RuntimeKernel, ServiceContainer  # noqa: E402
from core.planning.turn_orchestrator import TurnRequest, TurnResponse  # noqa: E402


# ---------------------------------------------------------------------------
# ServiceContainer
# ---------------------------------------------------------------------------

class _Foo:
    pass


def test_container_register_and_get_by_type():
    c = ServiceContainer()
    c.register(_Foo, lambda _c: _Foo())
    instance = c.get(_Foo)
    assert isinstance(instance, _Foo)
    # Singleton — second resolve returns the same object.
    assert c.get(_Foo) is instance


def test_container_register_instance_short_circuits_factory():
    c = ServiceContainer()
    pre_built = _Foo()
    c.register_instance(_Foo, pre_built)
    assert c.get(_Foo) is pre_built


def test_container_get_or_none_returns_none_when_unregistered():
    c = ServiceContainer()
    assert c.get_or_none(_Foo) is None


def test_container_get_raises_when_unregistered():
    c = ServiceContainer()
    with pytest.raises(KeyError):
        c.get(_Foo)


def test_container_accepts_string_keys():
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus())
    assert isinstance(c.get("event_bus"), EventBus)


def test_container_is_registered():
    c = ServiceContainer()
    assert not c.is_registered(_Foo)
    c.register(_Foo, lambda _c: _Foo())
    assert c.is_registered(_Foo)


# ---------------------------------------------------------------------------
# RuntimeKernel — populates container from a partial app stub
# ---------------------------------------------------------------------------

def _build_stub_app():
    """A minimal app stub satisfying the kernel's whitelist scan."""
    app = SimpleNamespace()
    app.event_bus = EventBus()
    app.lifecycle = LifecycleManager()
    app.config = MagicMock()
    app.turn_orchestrator = MagicMock()
    app.turn_orchestrator.handle.return_value = TurnResponse(
        response="hello-from-orchestrator",
        spoken_ack=None,
        source="planner",
        trace_id="tr-1",
        duration_ms=2.0,
        plan_mode="reply",
    )
    app.turn_manager = MagicMock()
    app.turn_manager.handle_turn.return_value = "fallback-from-turn-manager"
    return app


def test_kernel_populates_container_from_app_attributes():
    app = _build_stub_app()
    kernel = RuntimeKernel(app)
    kernel._populate_container_from_app()

    # Resolvable by attribute name
    assert kernel.get("event_bus") is app.event_bus
    assert kernel.get("lifecycle") is app.lifecycle
    # Resolvable by concrete type
    assert kernel.get(EventBus) is app.event_bus
    # The kernel and the underlying app are always resolvable
    assert kernel.get("RuntimeKernel") is kernel
    assert kernel.get("app") is app


def test_kernel_handle_request_uses_orchestrator_when_available():
    app = _build_stub_app()
    kernel = RuntimeKernel(app)

    request = TurnRequest(text="hi", source="text", session_id="s1")
    response = kernel.handle_request(request)

    assert isinstance(response, TurnResponse)
    assert response.response == "hello-from-orchestrator"
    app.turn_orchestrator.handle.assert_called_once_with(request)


def test_kernel_handle_request_falls_back_to_turn_manager_when_no_orchestrator():
    app = _build_stub_app()
    app.turn_orchestrator = None      # force the fallback branch
    kernel = RuntimeKernel(app)

    response = kernel.handle_request(TurnRequest(text="hi", source="cli", session_id="s1"))
    assert response == "fallback-from-turn-manager"
    app.turn_manager.handle_turn.assert_called_once_with("hi", source="cli")


def test_kernel_shutdown_calls_app_shutdown():
    app = _build_stub_app()
    app.shutdown = MagicMock()
    kernel = RuntimeKernel(app)
    kernel.shutdown()
    app.shutdown.assert_called_once()


def test_kernel_shutdown_falls_back_to_lifecycle_when_app_shutdown_raises():
    app = _build_stub_app()
    stop_all = MagicMock()
    app.lifecycle = SimpleNamespace(stop_all=stop_all)
    app.shutdown = MagicMock(side_effect=RuntimeError("boom"))
    kernel = RuntimeKernel(app)

    with pytest.raises(SystemExit):
        kernel.shutdown()
    stop_all.assert_called_once()


def test_kernel_initialize_calls_app_initialize_and_repopulates_container():
    app = _build_stub_app()
    init_called = []

    def _fake_init():
        init_called.append(True)
        # Simulate a service attached during initialize() — extensions do this.
        app.late_service = SimpleNamespace(name="late")

    app.initialize = _fake_init
    kernel = RuntimeKernel(app)
    kernel.initialize()

    assert init_called == [True]
    # The container learned about the late-attached service after re-population.
    # (it isn't on the whitelist by name, so this asserts the re-populate ran
    # without crashing on the new attribute, not that it was registered.)
    assert kernel.get("app").late_service.name == "late"


def test_kernel_get_or_none_when_service_missing():
    app = _build_stub_app()
    kernel = RuntimeKernel(app)
    kernel._populate_container_from_app()
    # Something that was never wired
    assert kernel.get_or_none("nonexistent_service") is None
