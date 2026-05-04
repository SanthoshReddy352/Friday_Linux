"""Kernel — low-level services shared across the conversation pipeline.

Phase 3 contents:
  ConsentService    — single source for online-consent and confirmation patterns
  PermissionService — capability tier enforcement (read / write / critical)

Phase 6 (v2) addition:
  RuntimeKernel     — bootstrap shell that owns the ServiceContainer and the
                      underlying FridayApp. Source: core/kernel/runtime.py.
  ServiceContainer  — type-keyed DI container wrapping bootstrap.Container.
"""
from core.kernel.consent import ConsentService
from core.kernel.permissions import PermissionService, PermissionTier
from core.kernel.runtime import RuntimeKernel, ServiceContainer

__all__ = [
    "ConsentService",
    "PermissionService",
    "PermissionTier",
    "RuntimeKernel",
    "ServiceContainer",
]
