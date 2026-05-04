"""Lightweight DI container.

Factories are registered against a string key (typically the class name or an
interface name). On resolve(), the factory is called once and the result is
cached — subsequent resolves return the same instance (singleton scope only;
no per-request scopes are needed yet).

Usage:
    container = Container()
    container.register("EventBus",  lambda c: EventBus())
    container.register("TurnManager", lambda c: TurnManager(c.resolve("App")))

    bus = container.resolve("EventBus")

Services that declare a stop() method can optionally be registered with
lifecycle=True to have LifecycleManager manage their teardown.
"""

from __future__ import annotations

from typing import Any, Callable

from core.logger import logger


_Factory = Callable[["Container"], Any]


class Container:
    def __init__(self):
        self._factories: dict[str, tuple[_Factory, bool]] = {}
        self._instances: dict[str, Any] = {}

    def register(self, key: str, factory: _Factory, *, lifecycle: bool = False) -> None:
        """Register a factory for `key`.

        lifecycle=True marks the resolved instance for lifecycle management
        (the caller is responsible for wiring it into LifecycleManager — the
        container itself does not own a LifecycleManager to avoid circular
        coupling).
        """
        self._factories[key] = (factory, lifecycle)

    def register_instance(self, key: str, instance: Any) -> None:
        """Register a pre-built instance directly (e.g. already-constructed objects)."""
        self._instances[key] = instance

    def resolve(self, key: str) -> Any:
        if key in self._instances:
            return self._instances[key]
        if key not in self._factories:
            raise KeyError(f"[container] No factory registered for '{key}'.")
        factory, _ = self._factories[key]
        try:
            instance = factory(self)
        except Exception:
            logger.exception("[container] factory failed for '%s'", key)
            raise
        self._instances[key] = instance
        return instance

    def is_registered(self, key: str) -> bool:
        return key in self._factories or key in self._instances

    def __contains__(self, key: str) -> bool:
        return self.is_registered(key)
