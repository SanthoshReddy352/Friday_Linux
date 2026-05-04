"""ResponseFinalizer — extracted from CommandRouter._finalize_response.

Applies post-processing steps to a raw tool handler output:
  1. assistant_context.humanize_tool_result()  — strips boilerplate, trims
  2. dialog_state clarification detection      — sets pending_clarification
     when the response contains a "did you mean?" prompt

Extracted so that OrderedToolExecutor and ConversationAgent can call this
without importing CommandRouter.
"""

from __future__ import annotations

import re
from typing import Any


class ResponseFinalizer:
    def __init__(self, app):
        self._app = app

    def finalize(self, response: Any) -> Any:
        """Humanize and run clarification detection on a tool response."""
        if not isinstance(response, str):
            return response
        assistant_context = getattr(self._app, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "humanize_tool_result"):
            response = assistant_context.humanize_tool_result(response)
        return self._detect_clarification(response)

    def remember_tool_use(self, tool_name: str, args: dict) -> None:
        assistant_context = getattr(self._app, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "remember_tool_use"):
            assistant_context.remember_tool_use(tool_name, args)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_clarification(self, response: str) -> str:
        dialog_state = getattr(self._app, "dialog_state", None)
        if not dialog_state:
            return response

        search_match = re.search(
            r"Would you like me to search for [\"'](.+?)[\"'](?: on (YouTube(?: Music)?))?\?",
            response,
            re.IGNORECASE,
        )
        if search_match:
            query = search_match.group(1).strip()
            platform = (search_match.group(2) or "").lower()
            action_text = (
                f"play {query} in youtube music" if "music" in platform else f"play {query} in youtube"
            )
            dialog_state.set_pending_clarification(
                action_text=action_text,
                prompt=response,
                cancel_message="Okay. Tell me what you'd like instead.",
            )
            return response

        meant_match = re.search(r"\"([^\"]+)\"\.\s*Is that what you meant\?", response, re.IGNORECASE)
        if not meant_match:
            meant_match = re.search(
                r"(?:^|[\s])'([^']+)'\.\s*Is that what you meant\?", response, re.IGNORECASE
            )
        if meant_match:
            dialog_state.set_pending_clarification(
                action_text=meant_match.group(1).strip(),
                prompt=response,
                cancel_message="Okay. Please say it again in a different way.",
            )
        return response
