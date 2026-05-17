"""First-run user-profile onboarding.

Owns the `update_user_profile` capability and exposes profile-read helpers
that the Greeter calls on startup. The actual multi-turn dialog lives in
`OnboardingWorkflow` (workflow.py), registered by `WorkflowOrchestrator`.

Profile facts are stored in `ContextStore.facts` under
``namespace="user_profile"`` — no new table required.
"""
from __future__ import annotations

from core.extensions.protocol import Extension, ExtensionContext
from core.logger import logger


PROFILE_NAMESPACE = "user_profile"
PROFILE_FIELDS = ("name", "role", "location", "preferences", "comm_style")


def read_profile(context_store) -> dict:
    """Return the stored profile as a `{field: value}` dict.

    Missing fields are omitted from the dict so callers can use truthiness
    checks (`if profile.get("name")`). Returns an empty dict on any error.
    """
    if context_store is None:
        return {}
    try:
        rows = context_store.get_facts_by_namespace(PROFILE_NAMESPACE)
    except Exception as exc:
        logger.debug("[onboarding] read_profile failed: %s", exc)
        return {}
    profile = {}
    for row in rows or []:
        key = (row.get("key") or "").strip()
        value = (row.get("value") or "").strip()
        if key and value:
            profile[key] = value
    return profile


def write_profile_field(context_store, field: str, value: str) -> None:
    """Persist a single field. Empty values are stored as empty strings so
    `read_profile` can distinguish "asked and skipped" from "never asked"."""
    if context_store is None or field not in PROFILE_FIELDS:
        return
    try:
        context_store.store_fact(field, value or "", namespace=PROFILE_NAMESPACE)
    except Exception as exc:
        logger.warning("[onboarding] write_profile_field(%s) failed: %s", field, exc)


def mark_completed(context_store) -> None:
    """Set the system-namespace flag that suppresses re-prompting."""
    if context_store is None:
        return
    try:
        context_store.store_fact("onboarding_completed", "true", namespace="system")
    except Exception as exc:
        logger.warning("[onboarding] mark_completed failed: %s", exc)


def is_completed(context_store) -> bool:
    if context_store is None:
        return False
    try:
        facts = {f["key"]: f["value"]
                 for f in context_store.get_facts_by_namespace("system")}
    except Exception:
        return False
    return facts.get("onboarding_completed", "") == "true"


class OnboardingExtension(Extension):
    name = "Onboarding"

    def load(self, ctx: ExtensionContext) -> None:
        self.ctx = ctx
        ctx.register_capability(
            spec={
                "name": "update_user_profile",
                "description": (
                    "Update what FRIDAY remembers about the user. Use when the "
                    "user says things like 'call me X', 'my name is X', "
                    "'I'm a Y', 'I live in Z', 'remember I prefer concise answers'. "
                    "Field must be one of: name, role, location, preferences, comm_style."
                ),
                "parameters": {
                    "field": "string - one of: name, role, location, preferences, comm_style",
                    "value": "string - the new value",
                },
                "aliases": [
                    "call me",
                    "my name is",
                    "remember my name",
                    "i live in",
                    "i'm based in",
                    "remember about me",
                ],
            },
            handler=self._handle_update_profile,
            metadata={
                "side_effect_level": "write",
                "permission_mode": "always_ok",
                "connectivity": "local",
                "latency_class": "interactive",
            },
        )
        logger.info("OnboardingExtension loaded.")

    def unload(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Capability handler
    # ------------------------------------------------------------------

    def _handle_update_profile(self, raw_text: str, args: dict) -> str:
        field = (args.get("field") or "").strip().lower()
        value = (args.get("value") or "").strip()
        if field not in PROFILE_FIELDS:
            return (
                "I can only remember name, role, location, preferences, or "
                "communication style — which one?"
            )
        if not value:
            return f"What's the new {field.replace('_', ' ')}?"

        context_store = self._context_store()
        write_profile_field(context_store, field, value)

        ack = {
            "name": f"Got it — I'll call you {value}.",
            "role": f"Noted, you work as {value}.",
            "location": f"Noted, you're based in {value}.",
            "preferences": f"Got it, I'll keep that in mind: {value}.",
            "comm_style": f"Understood — I'll keep things {value}.",
        }
        return ack.get(field, f"Noted: {field} is now {value}.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _context_store(self):
        return self.ctx.get_service("context_store")
