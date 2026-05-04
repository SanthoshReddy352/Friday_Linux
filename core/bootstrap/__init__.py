"""Bootstrap package — DI container, lifecycle management, and settings.

Phase 2 scope:
  * LifecycleManager — ordered start/stop with signal-handler integration
  * Container        — lazy DI container (factories registered, resolved on demand)
  * FridaySettings   — pydantic-free typed settings wrapper

FridayApp is NOT replaced in Phase 2; it delegates to Container internally
so the external API (main.py, tests, GUI) is unchanged.
"""
from core.bootstrap.lifecycle import LifecycleManager
from core.bootstrap.container import Container
from core.bootstrap.settings import FridaySettings

__all__ = ["LifecycleManager", "Container", "FridaySettings"]
