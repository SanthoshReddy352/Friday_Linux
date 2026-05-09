"""MemoryManagerPlugin — show_memories and delete_memory capabilities.

Requires Phase 6 (Mem0 integration) to be active. When Mem0 is disabled
or unavailable, both tools return graceful informational messages.
"""
from __future__ import annotations

from core.logger import logger
from core.plugin_manager import FridayPlugin


class MemoryManagerPlugin(FridayPlugin):
    name = "memory_manager"

    def __init__(self, app):
        super().__init__(app)
        self.name = "memory_manager"
        self.on_load()

    def on_load(self) -> None:
        self.app.router.register_tool(
            {
                "name": "show_memories",
                "description": (
                    "Show what FRIDAY remembers about the user — preferences, facts, and context "
                    "learned from past conversations."
                ),
                "parameters": {
                    "limit": "integer — max number of memories to show (default: 20)",
                },
                "context_terms": [
                    "what do you remember", "show my memories",
                    "what do you know about me", "list memories",
                    "what have you learned", "my preferences",
                ],
            },
            self._handle_show_memories,
        )

        self.app.router.register_tool(
            {
                "name": "delete_memory",
                "description": (
                    "Delete a specific memory by describing it. "
                    "Searches for the closest matching memory and removes it."
                ),
                "parameters": {
                    "target": "string — description or text of the memory to delete",
                },
                "context_terms": [
                    "forget that", "delete memory", "remove that memory",
                    "stop remembering", "forget what I said", "clear that memory",
                ],
            },
            self._handle_delete_memory,
        )

        logger.info("[memory_manager] Plugin loaded — show_memories + delete_memory registered.")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_show_memories(self, raw_text: str, args: dict):
        from core.capability_registry import CapabilityExecutionResult
        client = getattr(self.app, "_mem0_client", None)
        if not client:
            return CapabilityExecutionResult(
                ok=True, name="show_memories",
                output="Memory system is not active. Set memory.enabled: true in config.yaml to enable it.",
            )
        try:
            limit = int(args.get("limit", 20))
            all_memories = client.get_all(user_id="default")
            results = all_memories.get("results", [])
            if not results:
                return CapabilityExecutionResult(
                    ok=True, name="show_memories",
                    output="I don't have any stored memories yet.",
                )
            lines = [f"{i + 1}. {m['memory']}" for i, m in enumerate(results[:limit])]
            return CapabilityExecutionResult(
                ok=True, name="show_memories",
                output="Here is what I remember:\n" + "\n".join(lines),
                output_type="list",
            )
        except Exception as exc:
            logger.error("[memory_manager] show_memories failed: %s", exc)
            return CapabilityExecutionResult(ok=False, name="show_memories", error=str(exc))

    def _handle_delete_memory(self, raw_text: str, args: dict):
        from core.capability_registry import CapabilityExecutionResult
        client = getattr(self.app, "_mem0_client", None)
        if not client:
            return CapabilityExecutionResult(
                ok=False, name="delete_memory",
                error="Memory system not active.",
            )
        target = args.get("target") or raw_text
        try:
            results = client.search(target, user_id="default", limit=1)
            items = results.get("results", [])
            if not items:
                return CapabilityExecutionResult(
                    ok=True, name="delete_memory",
                    output=f"Could not find a memory matching: {target}",
                )
            memory_id = items[0]["id"]
            memory_text = items[0]["memory"]
            client.delete(memory_id)
            logger.info("[memory_manager] Deleted memory id=%s: %s", memory_id, memory_text)
            return CapabilityExecutionResult(
                ok=True, name="delete_memory",
                output=f"Deleted memory: {memory_text}",
            )
        except Exception as exc:
            logger.error("[memory_manager] delete_memory failed: %s", exc)
            return CapabilityExecutionResult(ok=False, name="delete_memory", error=str(exc))
