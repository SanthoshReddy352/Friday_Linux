"""ResearchWorkflow — multi-step research: search → gather → summarize → save.

Phase 9: Registered with WorkflowOrchestrator. Handles "research X" intents
by chaining: web/world_monitor search → LLM summarization → optional file save.
"""
from __future__ import annotations

import re


class ResearchWorkflow:
    """Multi-step research workflow.

    States: idle → searching → summarizing → [saving] → done
    """

    name = "research_mode"

    # Trigger phrases
    _START_PATTERNS = (
        re.compile(r"\b(?:research|look\s+(?:up|into)|find\s+out\s+about|investigate)\b", re.IGNORECASE),
        re.compile(r"\b(?:what\s+is|tell\s+me\s+about|explain)\b.{10,}", re.IGNORECASE),
    )

    def __init__(self, app):
        self._app = app

    def should_start(self, user_text: str, context=None) -> bool:
        return any(p.search(user_text) for p in self._START_PATTERNS)

    def can_continue(self, user_text: str, state: dict, context=None) -> bool:
        step = state.get("step", "")
        if step == "awaiting_save_confirm":
            lowered = user_text.lower().strip()
            return any(w in lowered for w in ("yes", "save", "sure", "yeah", "no", "skip", "done"))
        return False

    def run(self, user_text: str, session_id: str, context=None):
        from core.workflow_orchestrator import WorkflowResult  # noqa: PLC0415

        topic = self._extract_topic(user_text)
        if not topic:
            return WorkflowResult(
                workflow_name=self.name,
                handled=True,
                response="What would you like me to research, sir?",
                state={"step": "awaiting_topic"},
            )

        # Step 1: Gather information
        search_result = self._search(topic)

        # Step 2: Summarize with LLM (if available)
        summary = self._summarize(topic, search_result)

        return WorkflowResult(
            workflow_name=self.name,
            handled=True,
            response=f"Research on **{topic}**:\n\n{summary}\n\nWould you like me to save this summary to a file?",
            state={"step": "awaiting_save_confirm", "topic": topic, "summary": summary},
        )

    def _handle_continuation(self, user_text: str, state: dict, session_id: str):
        from core.workflow_orchestrator import WorkflowResult  # noqa: PLC0415

        lowered = user_text.lower().strip()
        topic = state.get("topic", "research")
        summary = state.get("summary", "")

        if any(w in lowered for w in ("yes", "save", "sure", "yeah")):
            filename = re.sub(r"[^\w\s-]", "", topic).strip().replace(" ", "_")[:40] + "_research.md"
            save_result = self._save_to_file(filename, topic, summary)
            return WorkflowResult(
                workflow_name=self.name,
                handled=True,
                response=save_result,
                state={"step": "done"},
            )
        else:
            return WorkflowResult(
                workflow_name=self.name,
                handled=True,
                response="Understood, sir. Research complete.",
                state={"step": "done"},
            )

    def _extract_topic(self, text: str) -> str:
        for prefix in ("research", "look up", "look into", "find out about", "investigate", "what is", "tell me about", "explain"):
            lower = text.lower()
            if prefix in lower:
                topic = lower.split(prefix, 1)[-1].strip().strip(".,?!")
                return topic[:80] if topic else ""
        return ""

    def _search(self, topic: str) -> str:
        registry = getattr(self._app, "capability_registry", None)
        if registry and registry.has_capability("get_news"):
            result = registry._get_handler("get_news")
            if result:
                try:
                    return str(result(topic, {}))
                except Exception:
                    pass
        return f"Searching for information on: {topic}"

    def _summarize(self, topic: str, search_result: str) -> str:
        registry = getattr(self._app, "capability_registry", None)
        if registry and registry.has_capability("llm_chat"):
            handler = registry._get_handler("llm_chat")
            if handler:
                try:
                    prompt = f"Summarize the following information about '{topic}' in 3-5 clear sentences:\n\n{search_result}"
                    result = handler(prompt, {"query": prompt})
                    if result and len(str(result)) > 20:
                        return str(result)
                except Exception:
                    pass
        return search_result[:500] if search_result else f"No results found for '{topic}'."

    def _save_to_file(self, filename: str, topic: str, content: str) -> str:
        import os  # noqa: PLC0415

        try:
            save_dir = os.path.expanduser("~/Documents/friday_research")
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Research: {topic}\n\n{content}\n")
            return f"Saved to {filepath}, sir."
        except Exception as exc:
            return f"Couldn't save the file: {exc}"
