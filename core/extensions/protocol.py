"""Extension protocol + ExtensionContext.

Extensions never receive a FridayApp reference. Everything they need is
surfaced through ExtensionContext, which is the narrow contract between
the application core and the extension boundary.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from core.capability_registry import CapabilityRegistry
from core.event_bus import EventBus
from core.kernel.consent import ConsentService
from core.logger import logger


# ---------------------------------------------------------------------------
# Narrow API surface — no FridayApp, no CommandRouter
# ---------------------------------------------------------------------------

class ExtensionContext:
    """Injected into every Extension.load() call.

    This is the ONLY object extensions should retain.  Its attributes expose
    the exact services extensions legitimately need; everything else stays
    internal to the application.
    """

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        events: EventBus,
        consent: ConsentService,
        config,
        app_ref=None,     # kept for LegacyExtensionAdapter only; native extensions must not use it
    ):
        self._registry = registry
        self._events = events
        self._consent = consent
        self._config = config
        self._app_ref = app_ref  # private; only adapter uses this

    # --- public accessors ---------------------------------------------------

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def events(self) -> EventBus:
        return self._events

    @property
    def consent(self) -> ConsentService:
        return self._consent

    # --- registration helpers -----------------------------------------------

    def register_capability(
        self,
        spec: dict,
        handler: Callable[[str, dict], Any],
        metadata: dict | None = None,
    ) -> None:
        """Register a capability.

        Delegates to CapabilityRegistry and, while CommandRouter is still
        alive (Phase 4), also to router.register_tool() for backward compat.
        Phase 5 removes the router path.
        """
        # Primary: register in the capability registry
        self._registry.register_tool(spec, handler, metadata)

        # Compat: also register in CommandRouter so routing still works
        router = getattr(self._app_ref, "router", None) if self._app_ref else None
        if router is not None and hasattr(router, "register_tool"):
            try:
                router.register_tool(spec, handler, **({"metadata": metadata} if metadata else {}))
            except Exception:
                pass  # already registered via registry path above

    def get_config(self, key: str, default=None):
        config = self._config
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default

    def get_service(self, name: str):
        """Escape hatch: retrieve a named attribute from the app.

        Intentionally ugly API — if an extension calls this for anything
        other than a transitional reason, it should add that service to
        ExtensionContext properly.
        """
        if self._app_ref is None:
            return None
        return getattr(self._app_ref, name, None)


# ---------------------------------------------------------------------------
# Extension protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Extension(Protocol):
    """Interface every extension must satisfy.

    A class implementing Extension may additionally define:
      handle_startup() -> str    — vocal greeting on app start
      handle_event(event, data)  — arbitrary event subscription
    but these are optional hooks, not protocol requirements.
    """

    name: str

    def load(self, ctx: ExtensionContext) -> None:
        """Register capabilities, subscribe to events."""
        ...

    def unload(self) -> None:
        """Release resources, cancel subscriptions."""
        ...
