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
        ok, message = self.service.stop()
        return message

    def handle_cancel(self, text, args):
        ok, message = self.service.cancel()
        return message


def setup(app):
    return DictationPlugin(app)
