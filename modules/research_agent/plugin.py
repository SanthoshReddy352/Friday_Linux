import os
import re

from core.logger import logger
from core.plugin_manager import FridayPlugin

from .service import DEFAULT_MODE, MODES, ResearchAgentService, ResearchReport


class ResearchAgentPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "ResearchAgent"
        self.service = ResearchAgentService(app)
        self.app.research_agent = self.service
        self._active_threads = []
        self.on_load()

    def on_load(self):
        mode_list = "/".join(MODES.keys())
        self.app.router.register_tool({
            "name": "research_topic",
            "description": (
                "Run an agentic internet research session on a topic. Uses a "
                "classifier → researcher loop → writer pipeline (inspired by Vane). "
                "Searches a public SearxNG pool across web/academic/social categories "
                "with per-instance circuit-breakers and DuckDuckGo HTML as a last-"
                "resort fallback. Scrapes top sources and synthesizes a briefing "
                "with numbered [N] citations to ~/Documents/friday-research/<topic>/. "
                f"Modes: {mode_list} (default: {DEFAULT_MODE}). "
                "Use for 'research X', 'find research papers about X', "
                "'do a deep dive on X', or 'put together a briefing on X'."
            ),
            "parameters": {
                "topic": "string – the subject to research",
                "max_sources": "integer – how many sources to gather (1–12, default 5)",
                "mode": f"string – research depth: {mode_list} (default: {DEFAULT_MODE})",
            },
            "context_terms": [
                "research", "deep dive", "research papers", "find articles",
                "briefing", "literature review", "investigate", "study",
            ],
        }, self.handle_research, capability_meta={
            "connectivity": "online",
            "latency_class": "background",
            "permission_mode": "ask_first",
            "side_effect_level": "write",
        })
        logger.info("ResearchAgentPlugin loaded (Vane-style agentic pipeline).")

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------

    def handle_research(self, text, args):
        topic = (args.get("topic") or "").strip()
        if not topic:
            topic = self._extract_topic(text)

        # Delegate to the conversational planner workflow when one is wired
        # up — it will gather mode/sources/focus/confirmation step by step
        # before kicking off the actual research, then ask whether to read
        # the summary aloud when it's ready.
        planner = self._get_planner()
        if planner is not None and getattr(self.app.router, "session_id", None):
            return planner.begin(topic, self.app.router.session_id)

        # Direct-call fallback (no session / no orchestrator) — keep the old
        # one-shot behavior so non-interactive callers still work.
        if not topic:
            return "What should I research? Try 'research the latest on quantum dot displays'."

        try:
            max_sources = int(args.get("max_sources") or 5)
        except (TypeError, ValueError):
            max_sources = 5

        mode = (args.get("mode") or self._extract_mode(text) or DEFAULT_MODE).lower()
        if mode not in MODES:
            mode = DEFAULT_MODE

        cfg = MODES[mode]
        max_sources = max(1, min(max_sources, cfg["max_sources"]))

        thread = self.service.start_research(
            topic,
            max_sources=max_sources,
            on_complete=self._announce_completion,
            mode=mode,
        )
        self._active_threads = [t for t in self._active_threads if t.is_alive()]
        self._active_threads.append(thread)

        max_iter = cfg["max_iter"]
        return (
            f"Researching '{topic}' in {mode} mode ({max_iter} research iterations, "
            f"up to {max_sources} sources), sir. "
            "I'll let you know when the briefing is ready in your friday-research folder."
        )

    def _get_planner(self):
        """Return the ResearchPlannerWorkflow instance, or None if absent."""
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        if orchestrator is None:
            return None
        return orchestrator.workflows.get("research_planner")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _extract_topic(self, text: str) -> str:
        text_clean = (text or "").strip().rstrip(" .!?")
        if not text_clean:
            return ""
        for pattern in (
            r"^(?:please\s+)?(?:research|do\s+(?:a\s+)?(?:deep\s+dive|literature\s+review)|find\s+(?:me\s+)?(?:research\s+(?:papers|articles)|articles|papers)|put\s+together\s+(?:a\s+)?briefing|brief\s+me)\s+(?:about\s+|on\s+|for\s+)?(.+)$",
            r"^(?:please\s+)?(?:look\s+up|investigate|study)\s+(?:the\s+)?(.+)$",
        ):
            match = re.match(pattern, text_clean, re.IGNORECASE)
            if match:
                return match.group(1).strip(" .!?:'\"")
        return ""

    def _extract_mode(self, text: str) -> str:
        text_lower = (text or "").lower()
        for mode in MODES:
            if mode in text_lower:
                return mode
        # Common synonyms
        if any(w in text_lower for w in ("quick", "fast", "brief", "rapid")):
            return "speed"
        if any(w in text_lower for w in ("thorough", "deep", "exhaustive", "comprehensive")):
            return "quality"
        return ""

    def _announce_completion(self, report: ResearchReport):
        bus = getattr(self.app, "event_bus", None)
        emit = getattr(self.app, "emit_assistant_message", None)
        if report.error:
            message = f"Research on '{report.topic}' hit a snag, sir: {report.error}"
        else:
            usable = sum(1 for s in report.sources if s.summary and not s.error)
            folder_name = os.path.basename(report.folder.rstrip(os.sep))
            message = (
                f"Research briefing on '{report.topic}' is ready. "
                f"{usable} of {len(report.sources)} sources made it in. "
                f"You'll find it in friday-research/{folder_name}."
            )
        if callable(emit):
            try:
                emit(message, source="research")
                return
            except Exception:
                logger.exception("[research] emit_assistant_message failed; falling back")
        if bus is not None:
            bus.publish("voice_response", message)


def setup(app):
    return ResearchAgentPlugin(app)
