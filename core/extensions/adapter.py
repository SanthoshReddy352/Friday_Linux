"""LegacyExtensionAdapter — wraps a FridayPlugin so it satisfies Extension.

During Phase 4, all non-migrated plugins are wrapped by this adapter.
The adapter calls plugin.on_load() during load() so the plugin self-registers
its tools exactly as it did before.  The original FridayPlugin instance is
exposed as `.plugin` so main.py and other callers can still find named plugins.
"""

from __future__ import annotations

from core.extensions.protocol import Extension, ExtensionContext
from core.logger import logger


class LegacyExtensionAdapter:
    """Wrap an existing FridayPlugin instance as an Extension."""

    def __init__(self, plugin):
        self._plugin = plugin
        # Expose the wrapped plugin's name at the adapter level
        self.name: str = getattr(plugin, "name", type(plugin).__name__)

    @property
    def plugin(self):
        return self._plugin

    # ------------------------------------------------------------------
    # Extension protocol
    # ------------------------------------------------------------------

    def load(self, ctx: ExtensionContext) -> None:
        # Legacy plugins self-register during __init__ via on_load(), so
        # there's nothing extra to do here.  The ctx is stored in case a
        # future partial migration of the plugin needs it.
        self._ctx = ctx

    def unload(self) -> None:
        if hasattr(self._plugin, "unload"):
            try:
                self._plugin.unload()
            except Exception:
                logger.exception(f"[adapter] unload error in {self.name}")

    # ------------------------------------------------------------------
    # Transparent delegation for attribute access (e.g. handle_startup)
    # ------------------------------------------------------------------

    def __getattr__(self, item: str):
        # Only reached when the attribute isn't on the adapter itself.
        return getattr(self._plugin, item)
