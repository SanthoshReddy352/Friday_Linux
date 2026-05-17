"""OnboardingWorkflow — five-question first-run user-profile dialog.

Registered by `WorkflowOrchestrator`. Activated by the greeter on first run
(`GreeterExtension.handle_startup` writes the initial workflow state and
returns the first question as the spoken greeting). Each subsequent user
turn lands here via `WorkflowOrchestrator.continue_active`.
"""
from __future__ import annotations

import re

from core.logger import logger
from core.workflow_orchestrator import BaseWorkflow, WorkflowResult
from modules.onboarding.extension import (
    PROFILE_FIELDS,
    mark_completed,
    write_profile_field,
)


WORKFLOW_NAME = "user_onboarding"

# Phrases that mean "skip this question" but NOT "abort the whole onboarding".
# Workflow-level cancel ("cancel", "stop", "abort") is handled upstream by
# `WorkflowOrchestrator.continue_active`, which calls `_is_workflow_cancel`.
_SKIP_TOKENS = frozenset({
    "skip", "later", "no", "nope", "pass", "dunno", "i dunno",
    "i don't know", "idk", "none", "no thanks", "next",
})

# Order matters — this is the script. Each step asks one question and stores
# the previous answer (except the first step, whose question was emitted by
# the greeter before this workflow ever ran).
_STEPS = ("name", "role", "location", "preferences", "comm_style")


def _next_step(current: str) -> str | None:
    try:
        idx = _STEPS.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(_STEPS):
        return None
    return _STEPS[idx + 1]


def _is_skip(text: str) -> bool:
    normalized = re.sub(r"[^\w\s']", "", (text or "").strip().lower())
    if not normalized:
        return True
    return normalized in _SKIP_TOKENS


def _extract_name(text: str) -> str:
    """Best-effort extract a name from a freeform answer.

    Handles 'My name is X', 'I'm X', 'Call me X', 'X' (bare). Falls back to
    the trimmed input. We don't try to be clever — the user can correct via
    `update_user_profile` if they say 'My name is X but call me Y'.
    """
    if not text:
        return ""
    stripped = text.strip().rstrip(".!?")
    m = re.search(
        r"^(?:my name is|i am|i'm|call me|it's|name's|the name's)\s+([A-Za-z][\w\s'\-]*)$",
        stripped,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # If the user just gave a bare token or two ("Tricky", "Tricky Reddy"), use it.
    if len(stripped.split()) <= 4:
        return stripped
    # Long sentence — take the first proper-looking token.
    for word in stripped.split():
        cleaned = word.strip(",.!?'\"")
        if cleaned and cleaned[0].isalpha():
            return cleaned
    return stripped


def initial_state() -> dict:
    """Initial workflow_state dict written by the greeter."""
    return {
        "workflow_name": WORKFLOW_NAME,
        "step": _STEPS[0],
        "answers": {},
    }


def first_question() -> str:
    return "Hello! Before we start — what should I call you?"


def _next_question(step: str, answers: dict) -> str:
    name = (answers.get("name") or "").strip() or "there"
    if step == "role":
        return f"Nice to meet you, {name}. What do you do?"
    if step == "location":
        return "Where are you based? Helps me with weather, time zone, and news."
    if step == "preferences":
        return "Any tools or topics you care about most? Short answer is fine."
    if step == "comm_style":
        return "How do you like me to talk to you — concise, detailed, or somewhere in between?"
    return ""


def _completion_message(answers: dict) -> str:
    name = (answers.get("name") or "").strip()
    if name:
        return f"Got it, {name}. Glad to meet you. How can I help?"
    return "Got it. Glad to meet you. How can I help?"


class OnboardingWorkflow(BaseWorkflow):
    name = WORKFLOW_NAME

    def should_start(self, user_text, context=None):
        # Onboarding is started explicitly by the greeter, never by an
        # incoming utterance — `should_start` is intentionally False so the
        # orchestrator won't trigger it on, say, the user saying "hello".
        return False

    def can_continue(self, user_text, state, context=None):
        if not state:
            return False
        if state.get("workflow_name") != WORKFLOW_NAME:
            return False
        return state.get("step") in _STEPS

    def _handle(self, state):
        user_text = (state.get("user_text") or "").strip()
        session_id = state["session_id"]
        memory = self._memory()
        workflow_state = (
            memory.get_active_workflow(session_id, workflow_name=WORKFLOW_NAME) or {}
        )
        if not workflow_state:
            state["result"] = WorkflowResult(
                handled=False, workflow_name=WORKFLOW_NAME,
            )
            return state

        current_step = workflow_state.get("step")
        if current_step not in _STEPS:
            # Defensive: stale or unknown step → close cleanly.
            try:
                memory.clear_workflow_state(session_id, WORKFLOW_NAME)
            except Exception:
                pass
            state["result"] = WorkflowResult(
                handled=False, workflow_name=WORKFLOW_NAME, state={},
            )
            return state

        answers = dict(workflow_state.get("answers") or {})

        # Record the user's answer for the current step.
        if _is_skip(user_text):
            answers[current_step] = ""
        elif current_step == "name":
            answers[current_step] = _extract_name(user_text)
        else:
            answers[current_step] = user_text

        # Persist immediately so a crash mid-onboarding doesn't lose data.
        context_store = self._context_store_for_writes()
        write_profile_field(context_store, current_step, answers.get(current_step, ""))

        nxt = _next_step(current_step)
        if nxt is None:
            # Final step done — close out.
            mark_completed(context_store)
            try:
                memory.clear_workflow_state(session_id, WORKFLOW_NAME)
            except Exception:
                pass
            logger.info(
                "[onboarding] Completed; captured fields: %s",
                ", ".join(k for k, v in answers.items() if v) or "none",
            )
            state["result"] = WorkflowResult(
                handled=True,
                workflow_name=WORKFLOW_NAME,
                response=_completion_message(answers),
                state={},
            )
            return state

        # Save updated state and ask the next question.
        new_state = {
            "workflow_name": WORKFLOW_NAME,
            "step": nxt,
            "answers": answers,
        }
        try:
            memory.save_workflow_state(session_id, WORKFLOW_NAME, new_state)
        except Exception as exc:
            logger.warning("[onboarding] save_workflow_state failed: %s", exc)

        state["result"] = WorkflowResult(
            handled=True,
            workflow_name=WORKFLOW_NAME,
            response=_next_question(nxt, answers),
            state=new_state,
        )
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _context_store_for_writes(self):
        """Resolve the underlying ContextStore even when self._memory()
        returns a MemoryService façade. The façade exposes `.context_store`."""
        mem = self._memory()
        store = getattr(mem, "context_store", None)
        if store is not None:
            return store
        # Fallback: assume `mem` is already a ContextStore.
        return mem
