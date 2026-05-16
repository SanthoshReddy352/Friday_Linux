from core.logger import logger
from core.plugin_manager import FridayPlugin

from .service import DictationService


class DictationPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "Dictation"
        self.service = DictationService(app)
        self.app.dictation_service = self.service
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "start_dictation",
            "description": (
                "Start a long-form dictation session. While active, FRIDAY captures "
                "everything spoken into a timestamped memo file in ~/Documents/friday-memos. "
                "Use when the user asks to take a memo, start dictation, or begin a journal entry."
            ),
            "parameters": {
                "label": "string – optional name for the memo (defaults to 'memo')",
            },
            "context_terms": ["take a memo", "dictation", "start dictation", "journal", "memo"],
        }, self.handle_start, capability_meta={
            "connectivity": "local",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "end_dictation",
            "description": "Finish and save the current dictation memo.",
            "parameters": {},
            "context_terms": ["end memo", "stop dictation", "save memo", "finish memo"],
        }, self.handle_end, capability_meta={
            "connectivity": "local",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "cancel_dictation",
            "description": "Discard the current dictation memo without saving.",
            "parameters": {},
            "context_terms": ["cancel memo", "discard memo"],
        }, self.handle_cancel, capability_meta={
            "connectivity": "local",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
        })

        logger.info("DictationPlugin loaded.")

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def handle_start(self, text, args):
        label = (args.get("label") or "").strip()
        ok, message = self.service.start(label)
        return message

    def handle_end(self, text, args):
        # Issue 6: if no dictation is active and the user's phrasing looks
        # like "save note ..." (which used to cross-route here via the
        # embedding router — now blocklisted but defence-in-depth still
        # pays off), redirect explicitly to the save_note tool instead of
        # surfacing the confusing "I'm not in a dictation session" reply.
        if not self.service.is_active():
            normalized = (text or "").lower()
            if "save note" in normalized or "note this" in normalized or "note that" in normalized:
                save_note = self.app.router._tools_by_name.get("save_note") if hasattr(self.app, "router") else None
                if save_note and save_note.get("callback"):
                    return save_note["callback"](text, {})
        ok, message = self.service.stop()
        return message

    def handle_cancel(self, text, args):
        ok, message = self.service.cancel()
        return message


def setup(app):
    return DictationPlugin(app)
