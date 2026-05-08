"""ResearchPlannerWorkflow — pre-research conversational planner.

Sits in front of ResearchAgentService. Instead of starting research
immediately when the user says "research X", we walk through a small
state machine:

    awaiting_topic   → "What should I research?"
    awaiting_mode    → "speed / balanced / quality?"
    awaiting_sources → "How many sources? (1-N)"
    awaiting_focus   → "Any particular angle, or general?"
    awaiting_confirm → recap, "Shall I proceed?"
    researching      → research kicked off, async on_complete will message
    awaiting_readout → "Briefing ready — read it aloud?"
    done             → terminal

The workflow is started by the ResearchAgentPlugin (not by should_start
matching utterances). That keeps it from competing with the existing
`research_mode` workflow or with the deterministic router. Once active,
the WorkflowOrchestrator's continue_active path delivers subsequent user
turns to ``can_continue`` -> ``run`` -> ``_handle``.
"""
from __future__ import annotations

import re

from core.logger import logger
from core.workflow_orchestrator import BaseWorkflow, WorkflowResult


_NEGATIVE_TOKENS = ("no", "skip", "cancel", "stop", "nope", "nah", "forget", "abort", "don't", "do not")
_AFFIRMATIVE_TOKENS = ("yes", "yeah", "yep", "sure", "ok", "okay", "go", "do it", "proceed", "go ahead", "please do")

_MODE_CAPS = {"speed": 4, "balanced": 8, "quality": 12}

_AWAITING_STEPS = frozenset({
    "awaiting_topic",
    "awaiting_mode",
    "awaiting_sources",
    "awaiting_focus",
    "awaiting_confirm",
    "awaiting_readout",
})


class ResearchPlannerWorkflow(BaseWorkflow):
    name = "research_planner"

    # Never auto-start. The plugin is responsible for entering this workflow
    # so we don't compete with the existing `research_mode` quick-summary
    # workflow or with deterministic routing.
    def should_start(self, user_text, context=None):
        return False

    def can_continue(self, user_text, state, context=None):
        return state.get("step") in _AWAITING_STEPS

    # ------------------------------------------------------------------
    # External entry point: called by the plugin to enter the workflow.
    # ------------------------------------------------------------------

    def begin(self, topic: str, session_id: str) -> str:
        """Save the initial state and return the first prompt to the user."""
        topic = (topic or "").strip(" .!?:'\"")
        if not topic:
            initial = {"step": "awaiting_topic"}
            self._memory().save_workflow_state(session_id, self.name, initial)
            return "What would you like me to research, sir?"

        state = {
            "step": "awaiting_mode",
            "topic": topic,
            "mode": None,
            "max_sources": None,
            "focus": None,
        }
        self._memory().save_workflow_state(session_id, self.name, state)
        return (
            f"Got it — research on '{topic}'. "
            "What depth would you like? **speed** (~2 iterations, fast), "
            "**balanced** (~6 iterations, default), or **quality** (~25 iterations, deep dive)?"
        )

    # ------------------------------------------------------------------
    # Per-turn handler
    # ------------------------------------------------------------------

    def _handle(self, state):
        user_text = (state.get("user_text") or "").strip()
        session_id = state["session_id"]
        ws = self._memory().get_active_workflow(session_id, workflow_name=self.name) or {}
        step = ws.get("step")

        if step == "awaiting_topic":
            topic = user_text.strip(" .!?:'\"")
            if not topic:
                return self._reply(state, ws, "I still need a topic, sir — what should I research?")
            ws["topic"] = topic
            ws["step"] = "awaiting_mode"
            self._save(session_id, ws)
            return self._reply(state, ws,
                f"Researching '{topic}'. Depth — speed, balanced, or quality?")

        if step == "awaiting_mode":
            mode = self._parse_mode(user_text)
            ws["mode"] = mode
            ws["step"] = "awaiting_sources"
            self._save(session_id, ws)
            cap = _MODE_CAPS[mode]
            return self._reply(state, ws,
                f"{mode.capitalize()} mode. How many sources should I gather? "
                f"(1–{cap}, default 5)")

        if step == "awaiting_sources":
            n = self._parse_sources(user_text, ws.get("mode") or "balanced")
            ws["max_sources"] = n
            ws["step"] = "awaiting_focus"
            self._save(session_id, ws)
            return self._reply(state, ws,
                f"{n} sources. Any specific focus or angle to emphasize? "
                "(say it now, or 'no' for general coverage)")

        if step == "awaiting_focus":
            focus = "" if self._is_negative(user_text) else user_text.strip(" .!?:'\"")
            ws["focus"] = focus
            ws["step"] = "awaiting_confirm"
            self._save(session_id, ws)
            recap_parts = [
                f"Researching '{ws['topic']}'",
                f"in **{ws['mode']}** mode",
                f"across **{ws['max_sources']}** sources",
            ]
            if focus:
                recap_parts.append(f"focused on: *{focus}*")
            recap = ", ".join(recap_parts)
            return self._reply(state, ws,
                f"{recap}. Shall I proceed?")

        if step == "awaiting_confirm":
            if self._is_negative(user_text):
                ws["step"] = "cancelled"
                self._save(session_id, ws)
                return self._reply(state, ws,
                    "Cancelled, sir. Let me know when you'd like to revisit it.")
            # Kick off the actual research.
            return self._kick_off_research(state, ws, session_id)

        if step == "awaiting_readout":
            if self._is_negative(user_text):
                ws["step"] = "done"
                self._save(session_id, ws)
                folder = ws.get("folder", "friday-research")
                folder_name = folder.rsplit("/", 1)[-1]
                return self._reply(state, ws,
                    f"Understood. The briefing is in friday-research/{folder_name} when you want it.")
            # Read the summary aloud (truncated to a TTS-friendly length).
            speech_text = self._summary_for_speech(ws.get("summary_path", ""))
            ws["step"] = "done"
            self._save(session_id, ws)
            return self._reply(state, ws, speech_text)

        # No matching step — bail out so the router can take over.
        state["result"] = WorkflowResult(handled=False, workflow_name=self.name, state=ws)
        return state

    # ------------------------------------------------------------------
    # Research kick-off and async completion
    # ------------------------------------------------------------------

    def _kick_off_research(self, state, ws, session_id):
        agent = getattr(self.app, "research_agent", None)
        if agent is None:
            ws["step"] = "done"
            self._save(session_id, ws)
            return self._reply(state, ws,
                "Research agent isn't loaded right now, sir.")

        topic = ws["topic"]
        focus = ws.get("focus") or ""
        full_topic = f"{topic} ({focus})" if focus else topic

        ws["step"] = "researching"
        self._save(session_id, ws)

        # Capture what we need so the async callback can update workflow state
        # without holding any reference to the LangGraph state dict.
        bound_session = session_id
        prior_ws = dict(ws)

        def _on_complete(report):
            self._on_research_done(report, bound_session, prior_ws)

        try:
            agent.start_research(
                full_topic,
                max_sources=ws["max_sources"],
                mode=ws["mode"],
                on_complete=_on_complete,
            )
        except Exception as exc:
            logger.exception("[research-planner] start_research failed")
            ws["step"] = "done"
            self._save(session_id, ws)
            return self._reply(state, ws,
                f"Couldn't start research: {exc}")

        return self._reply(state, ws,
            f"On it — researching '{full_topic}', {ws['mode']} mode, "
            f"{ws['max_sources']} sources. I'll let you know when the briefing is ready.")

    def _on_research_done(self, report, session_id, prior_ws):
        """Async completion: update workflow state + announce the result.

        Runs on the research worker thread, so we must not touch any
        per-turn LangGraph state — only the persisted workflow_state row.
        """
        ws = dict(prior_ws)
        ws["folder"] = getattr(report, "folder", "")
        ws["summary_path"] = getattr(report, "summary_path", "")
        ws["report_topic"] = getattr(report, "topic", "")

        if getattr(report, "error", None):
            ws["step"] = "done"
            self._save(session_id, ws)
            self._announce(
                f"Research on '{report.topic}' hit a snag, sir: {report.error}"
            )
            return

        ws["step"] = "awaiting_readout"
        self._save(session_id, ws)

        sources = getattr(report, "sources", []) or []
        usable = sum(
            1 for s in sources
            if getattr(s, "summary", "") and not getattr(s, "error", None)
        )
        folder_name = (getattr(report, "folder", "") or "").rsplit("/", 1)[-1]
        msg = (
            f"Briefing on '{report.topic}' is ready. "
            f"{usable} of {len(sources)} sources made it in. "
            f"Saved to friday-research/{folder_name}. "
            "Want me to read the summary aloud?"
        )
        self._announce(msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save(self, session_id, ws):
        self._memory().save_workflow_state(session_id, self.name, ws)

    def _reply(self, state, ws, message):
        state["result"] = WorkflowResult(
            handled=True,
            workflow_name=self.name,
            response=message,
            state=ws,
        )
        return state

    def _announce(self, message):
        emit = getattr(self.app, "emit_assistant_message", None)
        if callable(emit):
            try:
                emit(message, source="research")
                return
            except Exception:
                logger.exception("[research-planner] emit_assistant_message failed")
        bus = getattr(self.app, "event_bus", None)
        if bus is not None:
            bus.publish("voice_response", message)

    def _parse_mode(self, text: str) -> str:
        t = (text or "").lower()
        for mode in _MODE_CAPS:
            if mode in t:
                return mode
        if any(w in t for w in ("quick", "fast", "brief", "rapid", "shallow")):
            return "speed"
        if any(w in t for w in ("thorough", "deep", "exhaustive", "comprehensive", "detailed")):
            return "quality"
        return "balanced"

    def _parse_sources(self, text: str, mode: str) -> int:
        cap = _MODE_CAPS.get(mode, 8)
        m = re.search(r"\d+", text or "")
        if not m:
            return min(5, cap)
        try:
            n = int(m.group(0))
        except ValueError:
            return min(5, cap)
        return max(1, min(n, cap))

    def _is_negative(self, text: str) -> bool:
        t = (text or "").lower().strip(" .!?")
        if not t:
            return False
        if t in _NEGATIVE_TOKENS:
            return True
        return any(re.search(r"\b" + re.escape(tok) + r"\b", t) for tok in _NEGATIVE_TOKENS)

    def _summary_for_speech(self, path: str) -> str:
        if not path:
            return "I couldn't find the summary file, sir."
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            return f"Couldn't open the summary: {exc}"

        # Markdown stripping for TTS — strip headings/citations/code/emphasis.
        text = content
        text = re.sub(r"^#+\s*", "", text, flags=re.M)
        text = re.sub(r"\[(\d+)\]", r"reference \1", text)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.M)
        text = re.sub(r"\n{2,}", ". ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > 1500:
            text = text[:1500].rsplit(".", 1)[0] + "."
        return f"Reading the briefing now. {text}"
