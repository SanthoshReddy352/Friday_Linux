"""extensions — unified protocol for plugins and skills.

Phase 4 additions:
  Extension        — protocol every extension implements
  ExtensionContext — narrow API surface given to extensions (no FridayApp ref)
  ExtensionLoader  — discovers and loads extensions from modules/ and skills/
  LegacyExtensionAdapter — wraps existing FridayPlugin subclasses
  capability       — @capability(...) decorator for ergonomic tool declaration
"""
from core.extensions.protocol import Extension, ExtensionContext
from core.extensions.adapter import LegacyExtensionAdapter
from core.extensions.loader import ExtensionLoader
from core.extensions.decorators import capability

__all__ = [
    "Extension",
    "ExtensionContext",
    "LegacyExtensionAdapter",
    "ExtensionLoader",
    "capability",
]
