"""RuntimeKernel — Phase 6 (v2) bootstrap shell.

Phase 6 of the v2 architecture (docs/friday_architecture.md §7).

The doc proposes replacing `FridayApp`'s 24-step manual `__init__` with a
`ServiceContainer`-driven `RuntimeKernel` that lazily resolves services
from registered factories. The doc itself flags this phase as
*"highest effort, cosmetic once phases 1–5 are done"*.

Approach for "ship without breaking":

* `ServiceContainer` extends the existing `core.bootstrap.Container` with
  type-keyed `register(T, factory)` / `get(T) → T` so the doc's API
  surface (`kernel.get(EventBus)`) works without changing every legacy
  caller that still uses `app.event_bus`.
* `RuntimeKernel.boot()` builds a `FridayApp`, populates the container
  with every wired service, and exposes the v2 facade — `boot()`,
  `handle_request(TurnRequest) → TurnResponse`, `shutdown()`, and
  `get(T)`. The kernel does NOT re-implement service wiring; it borrows
  the already-correct construction order from `FridayApp.__init__` and
  uses that as the source of truth.
* `kernel.app` exposes the underlying `FridayApp` so legacy interfaces
  (CLI, GUI, extensions) keep working unchanged. Tests and new code can
  use `kernel.get(...)` and `kernel.handle_request(...)` directly.

Cutover path (deferred): once every consumer reads through `kernel.get`
and `kernel.handle_request`, the FridayApp class can be deleted and its
service construction inlined into the container's factories.
"""
from __future__ import annotations

import sys
from typing import Any, Type, TypeVar

from core.bootstrap.container import Container
from core.bootstrap.lifecycle import LifecycleManager
from core.logger import logger


T = TypeVar("T")


class ServiceContainer:
    """Type-keyed wrapper over `bootstrap.Container`.

    The doc's interface uses generics — `c.register(T, factory)` /
    `c.get(T) -> T` — and resolves services by their concrete type. The
    bootstrap Container is keyed by string; this wrapper translates one
    to the other so both are usable side by side.
    """

    def __init__(self, inner: Container | None = None):
        self._inner = inner or Container()

    # ------------------------------------------------------------------
    # Doc-facing API
    # ------------------------------------------------------------------

    def register(self, key: Type[T] | str, factory, *, lifecycle: bool = False) -> None:
        self._inner.register(_key_for(key), lambda _c: factory(self), lifecycle=lifecycle)

    def register_instance(self, key: Type[T] | str, instance: T) -> None:
        self._inner.register_instance(_key_for(key), instance)

    def get(self, key: Type[T] | str) -> T:
        return self._inner.resolve(_key_for(key))

    def get_or_none(self, key: Type[T] | str) -> T | None:
        try:
            return self.get(key)
        except KeyError:
            return None

    def is_registered(self, key: Type[T] | str) -> bool:
        return self._inner.is_registered(_key_for(key))

    @property
    def inner(self) -> Container:
        return self._inner


def _key_for(key) -> str:
    """Map a class (or string) to the container's string key."""
    if isinstance(key, type):
        return key.__name__
    return str(key)


# ---------------------------------------------------------------------------
# RuntimeKernel
# ---------------------------------------------------------------------------


class RuntimeKernel:
    """Phase 6 (v2) bootstrap shell.

    Owns the `ServiceContainer` and the underlying `FridayApp`. Exposes
    the v2 facade documented in §7 (`boot`, `handle_request`,
    `shutdown`, `get`). The legacy `FridayApp` interface stays reachable
    via `kernel.app` so CLI/GUI/extensions need no migration.
    """

    def __init__(self, app, container: ServiceContainer | None = None):
        self.app = app
        self.container = container or ServiceContainer()
        # Inherit the lifecycle manager FridayApp already owns so
        # `kernel.shutdown()` and `app.shutdown()` are interchangeable.
        self.lifecycle: LifecycleManager = getattr(app, "lifecycle", LifecycleManager())

    # ------------------------------------------------------------------
    # Boot / shutdown
    # ------------------------------------------------------------------

    @classmethod
    def boot(cls, app=None) -> "RuntimeKernel":
        """Construct the kernel.

        If *app* is None a fresh `FridayApp` is built — this is the path
        production code (main.py) takes. Tests can pass a partial stub
        instead so they don't need to mount the full service graph.
        """
        if app is None:
            from core.app import FridayApp  # local import: avoids module cycle
            app = FridayApp()
        kernel = cls(app)
        kernel._populate_container_from_app()
        return kernel

    def initialize(self) -> "RuntimeKernel":
        """Run app.initialize() (model preload, extension load, trace export).

        Kept as a separate step so callers can register additional
        services on the container between boot() and initialize() — same
        contract as `FridayApp()` followed by `FridayApp.initialize()`.
        """
        if hasattr(self.app, "initialize"):
            self.app.initialize()
        # Re-populate so any services constructed during initialize()
        # (e.g. extensions that attach themselves to the app) are
        # resolvable through the container.
        self._populate_container_from_app()
        return self

    def shutdown(self) -> None:
        if hasattr(self.app, "shutdown"):
            try:
                self.app.shutdown()
                return        # FridayApp.shutdown calls sys.exit; never returns
            except SystemExit:
                raise
            except Exception:
                logger.exception("[kernel] app.shutdown() failed; falling back to lifecycle.stop_all()")
        self.lifecycle.stop_all()
        sys.exit(0)

    # ------------------------------------------------------------------
    # v2 turn entry point — mirrors FridayApp's TurnManager but speaks
    # the doc's TurnRequest / TurnResponse contract directly.
    # ------------------------------------------------------------------

    def handle_request(self, request) -> Any:
        """Run a TurnRequest through the v2 TurnOrchestrator.

        Falls back to TurnManager.handle_turn() (which itself dispatches
        to the orchestrator when `routing.orchestrator: "v2"`) when the
        orchestrator is not separately mounted, so the kernel stays
        useful in mixed v1/v2 deployments.
        """
        orchestrator = getattr(self.app, "turn_orchestrator", None)
        if orchestrator is not None:
            return orchestrator.handle(request)
        # Fallback: drive through TurnManager. Returns the raw response
        # string rather than a TurnResponse — caller is responsible for
        # wrapping it if needed.
        return self.app.turn_manager.handle_turn(request.text, source=request.source)

    # ------------------------------------------------------------------
    # Container access
    # ------------------------------------------------------------------

    def get(self, key: Type[T] | str) -> T:
        return self.container.get(key)

    def get_or_none(self, key: Type[T] | str) -> T | None:
        return self.container.get_or_none(key)

    # ------------------------------------------------------------------
    # Container population
    # ------------------------------------------------------------------

    def _populate_container_from_app(self) -> None:
        """Mirror every wired service on the underlying app into the container.

        Phase 6 doesn't move construction logic — `FridayApp.__init__` is
        still the source of truth for service ordering. The container
        learns about services by discovering them on the app instance.
        New code that wants `kernel.get(EventBus)` works; legacy code
        that uses `app.event_bus` is unchanged.
        """
        # Whitelist of attribute names known to be wired services. The
        # kernel only exposes things that make sense as injectable
        # dependencies — stateful per-turn fields and private slots are
        # deliberately excluded.
        candidates = (
            "config",
            "event_bus",
            "context_store",
            "memory_broker",
            "memory_service",
            "persona_manager",
            "consent_service",
            "permission_service",
            "routing_state",
            "response_finalizer",
            "router",
            "model_manager",
            "model_router",
            "intent_recognizer",
            "route_scorer",
            "capability_registry",
            "capability_executor",
            "capability_broker",
            "ordered_tool_executor",
            "task_graph_executor",
            "graph_compiler",
            "workflow_orchestrator",
            "workflow_coordinator",
            "intent_engine",
            "planner_engine",
            "turn_orchestrator",
            "conversation_agent",
            "turn_manager",
            "speech_coordinator",
            "task_runner",
            "delegation_manager",
            "extension_loader",
            "dialogue_manager",
            "result_cache",
            "lifecycle",
            "turn_feedback",
            "runtime_metrics",
            "tts",
            "stt",
        )
        for attr in candidates:
            instance = getattr(self.app, attr, None)
            if instance is None:
                continue
            type_key = _key_for(type(instance))
            string_key = _key_for(attr)
            # Register under both the concrete type name AND the legacy
            # attribute name so callers can resolve by either.
            if not self.container.is_registered(type_key):
                self.container.register_instance(type_key, instance)
            if not self.container.is_registered(string_key):
                self.container.register_instance(string_key, instance)
        # Always make the kernel itself and the app itself resolvable.
        if not self.container.is_registered("RuntimeKernel"):
            self.container.register_instance("RuntimeKernel", self)
        if not self.container.is_registered("app"):
            self.container.register_instance("app", self.app)
