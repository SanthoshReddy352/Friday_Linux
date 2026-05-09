"""VisionPlugin — registers VLM-backed screen analysis capabilities.

Phase 1 (Tier 1):  analyze_screen, read_text_from_image, summarize_screen
Phase 2 (Tier 1+): analyze_clipboard_image, debug_code_screenshot, fun features
Phase 3 (Tier 2):  compare_screenshots, find_ui_element, smart_error_detector

Each capability fires a voice ack immediately before VLM inference starts so
the user is never left in silence during the 5–20 s CPU inference window.
"""
from __future__ import annotations

from core.logger import logger
from core.plugin_manager import FridayPlugin


class VisionPlugin(FridayPlugin):
    name = "vision"

    def __init__(self, app):
        super().__init__(app)
        self.name = "vision"    # FridayPlugin.__init__ sets "BasePlugin"; restore it
        self._service = None
        self.on_load()

    def on_load(self) -> None:
        cfg = self._get_cfg()
        if not cfg.get("enabled", False):
            logger.info("[vision] Plugin disabled in config (vision.enabled: false).")
            return

        from modules.vision.service import VisionService
        self._service = VisionService(cfg)

        features = cfg.get("features", {})
        registered = 0

        if features.get("screenshot_explainer", True):
            self.app.router.register_tool(
                {
                    "name": "analyze_screen",
                    "description": (
                        "Take a screenshot of the current screen and explain what is on it. "
                        "Use for: errors, crash dialogs, popups, UI questions, 'what is this'."
                    ),
                    "aliases": [
                        "analyze my screen", "analyze screen", "analyze the screen",
                        "look at my screen", "look at the screen",
                        "what is on my screen", "what's on my screen",
                        "explain my screen", "explain the screen", "check my screen",
                        "what do you see on screen", "describe my screen",
                    ],
                    "patterns": [
                        r"\b(?:analyze|explain|check|describe|inspect)\s+(?:my\s+|the\s+)?screen\b",
                        r"\blook\s+at\s+(?:my\s+|the\s+)?screen\b",
                        r"\bwhat(?:'s|\s+is)\s+on\s+(?:my\s+|the\s+)?screen\b",
                    ],
                    "context_terms": [
                        "screen", "explain", "what is this", "what is on",
                        "error on screen", "popup", "what happened",
                        "what do you see", "analyze screen", "look at my screen",
                    ],
                    "side_effect_level": "write",
                    "latency_class": "slow",
                },
                self._handle_analyze_screen,
            )
            registered += 1

        if features.get("ocr_reader", True):
            self.app.router.register_tool(
                {
                    "name": "read_text_from_image",
                    "description": (
                        "Extract and read text from a screenshot, image, or photo. "
                        "Works on handwritten notes, receipts, terminal output, code screenshots."
                    ),
                    "aliases": [
                        "read the screen", "read my screen", "read screen",
                        "read the text", "read text from screen",
                        "extract text from screen", "what does this say",
                        "what is written on screen", "ocr my screen",
                    ],
                    "patterns": [
                        r"\bread\s+(?:the\s+|my\s+)?screen\b",
                        r"\bread\s+(?:the\s+)?text\s+(?:from|on)\s+(?:my\s+|the\s+)?screen\b",
                        r"\bextract\s+(?:the\s+)?text\b",
                        r"\bocr\s+(?:my\s+|the\s+)?screen\b",
                    ],
                    "context_terms": [
                        "read", "extract text", "ocr", "what does this say",
                        "text from image", "read the screen", "what is written",
                    ],
                    "side_effect_level": "write",
                    "latency_class": "slow",
                },
                self._handle_read_text,
            )
            registered += 1

        if features.get("screen_summarizer", True):
            self.app.router.register_tool(
                {
                    "name": "summarize_screen",
                    "description": (
                        "Take a screenshot and give a summary of what the user is currently looking at. "
                        "Good for dashboards, articles, presentations, and long documents."
                    ),
                    "aliases": [
                        "summarize screen", "summarize my screen", "summarize the screen",
                        "what am I looking at", "what is on screen",
                        "give me an overview of my screen", "summary of my screen",
                    ],
                    "patterns": [
                        r"\bsummarize\s+(?:my\s+|the\s+)?screen\b",
                        r"\bwhat\s+am\s+i\s+looking\s+at\b",
                        r"\bgive\s+me\s+(?:a\s+)?(?:summary|overview)\s+of\s+(?:my\s+|the\s+)?screen\b",
                    ],
                    "context_terms": [
                        "summarize screen", "what am I looking at", "overview",
                        "summary of my screen", "what is this page", "summarize this",
                    ],
                    "side_effect_level": "write",
                    "latency_class": "slow",
                },
                self._handle_summarize_screen,
            )
            registered += 1

        if features.get("clipboard_analyzer", False):
            self.app.router.register_tool(
                {
                    "name": "analyze_clipboard_image",
                    "description": (
                        "Analyze or explain the image currently copied in the clipboard. "
                        "Useful when the user has copied a chart, diagram, screenshot, or photo."
                    ),
                    "aliases": [
                        "analyze clipboard", "analyze clipboard image",
                        "explain this image", "what is in my clipboard",
                        "analyze the image I copied", "explain the clipboard image",
                    ],
                    "patterns": [
                        r"\banalyze\s+(?:the\s+)?clipboard\b",
                        r"\b(?:analyze|explain)\s+(?:this\s+|the\s+)?(?:clipboard\s+)?image\b",
                    ],
                    "context_terms": [
                        "clipboard", "analyze this", "explain the image",
                        "what did I copy", "clipboard image",
                    ],
                },
                self._handle_clipboard_image,
            )
            registered += 1

        if features.get("code_debugger", False):
            self.app.router.register_tool(
                {
                    "name": "debug_code_screenshot",
                    "description": (
                        "Read a screenshot of code, a terminal error, or a stack trace and explain the issue."
                    ),
                    "aliases": [
                        "debug this screenshot", "read the error", "explain this error",
                        "what is the error", "explain the stack trace",
                        "debug the error", "what is wrong with my code",
                    ],
                    "patterns": [
                        r"\b(?:read|explain|debug)\s+(?:the\s+|this\s+)?(?:error|stack\s+trace|crash)\b",
                        r"\bwhat(?:'s|\s+is)\s+(?:the\s+)?(?:error|bug|problem)\s+(?:here|on\s+screen)\b",
                    ],
                    "context_terms": [
                        "stack trace", "debug screenshot", "code error",
                        "terminal error", "syntax error", "what is wrong",
                        "read the error", "explain this error",
                    ],
                    "side_effect_level": "write",
                    "latency_class": "slow",
                },
                self._handle_debug_code,
            )
            registered += 1

        if features.get("fun_features", False):
            self.app.router.register_tool(
                {
                    "name": "explain_meme",
                    "description": "Explain a meme — the joke, the cultural context, and why it is funny.",
                    "aliases": [
                        "explain this meme", "explain the meme",
                        "why is this funny", "what is the joke",
                        "explain meme", "what is this meme",
                    ],
                    "patterns": [
                        r"\bexplain\s+(?:this\s+|the\s+)?meme\b",
                        r"\bwhy\s+is\s+this\s+funny\b",
                    ],
                    "context_terms": [
                        "explain this meme", "why is this funny",
                        "what is the joke", "explain meme",
                    ],
                },
                self._handle_explain_meme,
            )
            self.app.router.register_tool(
                {
                    "name": "roast_desktop",
                    "description": "Take a screenshot and make a funny comment about the current desktop.",
                    "aliases": [
                        "roast my desktop", "roast my screen", "roast desktop",
                        "roast the desktop", "make fun of my desktop",
                        "roast this desktop",
                    ],
                    "patterns": [
                        r"\broast\s+(?:my\s+|the\s+|this\s+)?(?:desktop|screen)\b",
                        r"\bmake\s+fun\s+of\s+(?:my\s+|the\s+)?desktop\b",
                    ],
                    "context_terms": [
                        "roast my desktop", "roast my screen",
                        "make fun of my desktop", "what is wrong with my screen",
                    ],
                },
                self._handle_roast_desktop,
            )
            self.app.router.register_tool(
                {
                    "name": "review_design",
                    "description": "Analyze a UI screenshot and give honest design or usability feedback.",
                    "aliases": [
                        "review this design", "how does this look",
                        "rate this ui", "rate this design",
                        "design feedback", "review my ui", "critique this design",
                    ],
                    "patterns": [
                        r"\b(?:review|rate|critique)\s+(?:this\s+|the\s+|my\s+)?(?:design|ui|interface)\b",
                        r"\bhow\s+does\s+this\s+(?:design\s+)?look\b",
                    ],
                    "context_terms": [
                        "how does this look", "review this design",
                        "rate this ui", "design feedback", "is this good design",
                    ],
                },
                self._handle_review_design,
            )
            registered += 3

        if features.get("compare_screenshots", False):
            self.app.router.register_tool(
                {
                    "name": "compare_screenshots",
                    "description": "Compare two screenshots and explain what changed or is different.",
                    "aliases": [
                        "compare screenshots", "compare these screenshots",
                        "what changed", "what is different", "before and after comparison",
                    ],
                    "patterns": [
                        r"\bcompare\s+(?:the\s+|these\s+)?screenshots?\b",
                        r"\bwhat\s+(?:has\s+)?changed\s+(?:between|on\s+screen)\b",
                    ],
                    "context_terms": [
                        "compare screenshots", "what changed",
                        "difference between", "before and after", "what is different",
                    ],
                },
                self._handle_compare_screenshots,
            )
            registered += 1

        if features.get("ui_element_finder", False):
            self.app.router.register_tool(
                {
                    "name": "find_ui_element",
                    "description": (
                        "Find a UI element on screen by description. "
                        "Returns its approximate location. Can optionally click it."
                    ),
                    "aliases": [
                        "find the button", "find element on screen",
                        "where is the button", "locate the button",
                        "find the settings button", "find the menu",
                    ],
                    "patterns": [
                        r"\bfind\s+(?:the\s+)?\w+\s+(?:button|element|input|field|menu|icon)\b",
                        r"\bwhere\s+is\s+(?:the\s+)?\w+\s+(?:button|element|menu)\b",
                        r"\blocate\s+(?:the\s+)?\w+\s+(?:on\s+screen|button|element)\b",
                    ],
                    "context_terms": [
                        "find the button", "where is", "locate", "click",
                        "find settings", "where is the", "find the",
                    ],
                },
                self._handle_find_ui_element,
            )
            registered += 1

        if features.get("smart_error_detector", False):
            self._start_error_monitor()

        logger.info("[vision] Plugin loaded — %d capability/ies registered.", registered)

    # ------------------------------------------------------------------
    # Tier 1 handlers
    # ------------------------------------------------------------------

    def _handle_analyze_screen(self, raw_text: str, args: dict):
        self._ack("Analyzing your screen…")
        try:
            from modules.vision.screenshot import take_screenshot
            from modules.vision import prompts
            img = take_screenshot()
            result = self._service.infer(img, prompts.ANALYZE_SCREEN, max_tokens=100)
            return self._ok("analyze_screen", result or "I can see your screen but the model didn't produce a description. Try again or increase max_tokens in the vision config.")
        except Exception as exc:
            return self._err("analyze_screen", exc)

    def _handle_read_text(self, raw_text: str, args: dict):
        self._ack("Reading that for you…")
        try:
            from modules.vision.screenshot import take_screenshot
            from modules.vision import prompts
            img = take_screenshot()
            result = self._service.infer(img, prompts.READ_TEXT, max_tokens=150)
            return self._ok("read_text_from_image", result or "I couldn't extract any text from the screen. The screen may not contain readable text, or the model needs more tokens.")
        except Exception as exc:
            return self._err("read_text_from_image", exc)

    def _handle_summarize_screen(self, raw_text: str, args: dict):
        self._ack("Summarizing your screen…")
        try:
            from modules.vision.screenshot import take_screenshot
            from modules.vision import prompts
            img = take_screenshot()
            result = self._service.infer(img, prompts.SUMMARIZE_SCREEN, max_tokens=100)
            return self._ok("summarize_screen", result or "I can see your screen but couldn't generate a summary. Try again or check the vision config.")
        except Exception as exc:
            return self._err("summarize_screen", exc)

    # ------------------------------------------------------------------
    # Tier 1+ handlers (Phase 2)
    # ------------------------------------------------------------------

    def _handle_clipboard_image(self, raw_text: str, args: dict):
        self._ack("Looking at your clipboard…")
        try:
            from modules.vision.screenshot import get_clipboard_image
            from modules.vision import prompts
            img = get_clipboard_image()
            if img is None:
                return self._ok(
                    "analyze_clipboard_image",
                    "There is no image in your clipboard. Copy an image first, then try again.",
                )
            result = self._service.infer(img, prompts.ANALYZE_CLIPBOARD, max_tokens=100)
            return self._ok("analyze_clipboard_image", result)
        except Exception as exc:
            return self._err("analyze_clipboard_image", exc)

    def _handle_debug_code(self, raw_text: str, args: dict):
        self._ack("Reading the error…")
        try:
            from modules.vision.screenshot import take_screenshot
            from modules.vision import prompts
            img = take_screenshot()
            result = self._service.infer(img, prompts.DEBUG_CODE, max_tokens=150)
            return self._ok("debug_code_screenshot", result or "I can see the screen but couldn't identify the error. The model may need more context or tokens.")
        except Exception as exc:
            return self._err("debug_code_screenshot", exc)

    def _handle_explain_meme(self, raw_text: str, args: dict):
        self._ack("Let me look at this…")
        try:
            from modules.vision.screenshot import get_clipboard_image, take_screenshot
            from modules.vision import prompts
            img = get_clipboard_image() or take_screenshot()
            result = self._service.infer(img, prompts.EXPLAIN_MEME, max_tokens=80)
            return self._ok("explain_meme", result or "I couldn't generate an explanation for this image.")
        except Exception as exc:
            return self._err("explain_meme", exc)

    def _handle_roast_desktop(self, raw_text: str, args: dict):
        self._ack("Taking a look…")
        try:
            from modules.vision.screenshot import take_screenshot
            from modules.vision import prompts
            img = take_screenshot()
            result = self._service.infer(img, prompts.ROAST_DESKTOP, max_tokens=60)
            return self._ok("roast_desktop", result or "Your desktop is so clean I have nothing to roast.")
        except Exception as exc:
            return self._err("roast_desktop", exc)

    def _handle_review_design(self, raw_text: str, args: dict):
        self._ack("Reviewing this design…")
        try:
            from modules.vision.screenshot import get_clipboard_image, take_screenshot
            from modules.vision import prompts
            img = get_clipboard_image() or take_screenshot()
            result = self._service.infer(img, prompts.REVIEW_DESIGN, max_tokens=80)
            return self._ok("review_design", result or "I couldn't generate design feedback for this image.")
        except Exception as exc:
            return self._err("review_design", exc)

    # ------------------------------------------------------------------
    # Tier 2 handlers (Phase 3)
    # ------------------------------------------------------------------

    def _handle_compare_screenshots(self, raw_text: str, args: dict):
        self._ack("Comparing screenshots…")
        try:
            from PIL import Image
            from modules.vision.screenshot import get_clipboard_image, take_screenshot
            from modules.vision.preprocess import load_and_resize
            from modules.vision import prompts

            img_a = get_clipboard_image()
            img_b = take_screenshot()

            if img_a is None:
                return self._ok(
                    "compare_screenshots",
                    "Copy Image A to clipboard first, then ask me to compare.",
                )

            img_a = load_and_resize(img_a)
            img_b = load_and_resize(img_b)
            target_height = min(img_a.height, img_b.height, 600)
            img_a = img_a.resize(
                (int(img_a.width * target_height / img_a.height), target_height),
            )
            img_b = img_b.resize(
                (int(img_b.width * target_height / img_b.height), target_height),
            )
            combined = Image.new("RGB", (img_a.width + img_b.width, target_height))
            combined.paste(img_a, (0, 0))
            combined.paste(img_b, (img_a.width, 0))

            result = self._service.infer(combined, prompts.COMPARE_SCREENSHOTS, max_tokens=120)
            return self._ok("compare_screenshots", result)
        except Exception as exc:
            return self._err("compare_screenshots", exc)

    def _handle_find_ui_element(self, raw_text: str, args: dict):
        target = (args.get("target") or raw_text).strip()
        self._ack(f"Looking for {target}…")
        try:
            from modules.vision.screenshot import take_screenshot
            from modules.vision import prompts
            img = take_screenshot()
            prompt = prompts.UI_ELEMENT_FINDER.format(target=target)
            result = self._service.infer(img, prompt, max_tokens=100)
            return self._ok("find_ui_element", result)
        except Exception as exc:
            return self._err("find_ui_element", exc)

    def _start_error_monitor(self) -> None:
        """Launch the smart error detector daemon thread."""
        try:
            from modules.vision.smart_error_detector import start_error_monitor
            event_bus = getattr(self.app, "event_bus", None)
            if event_bus is None:
                logger.warning("[vision] smart_error_detector: no event_bus on app — skipping.")
                return
            start_error_monitor(self._service, event_bus)
            logger.info("[vision] Smart error detector started.")
        except Exception as exc:
            logger.warning("[vision] Could not start smart error detector: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_cfg(self) -> dict:
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get("vision") or {}
        return {}

    def _ack(self, text: str) -> None:
        """Fire a voice ack immediately — before VLM inference begins."""
        tf = getattr(self.app, "turn_feedback", None)
        turn = getattr(self.app, "_active_turn_record", None)
        if tf and turn:
            try:
                tf.emit_ack(turn, text)
            except Exception:
                pass

    def _ok(self, name: str, output: str):
        from core.capability_registry import CapabilityExecutionResult
        return CapabilityExecutionResult(ok=True, name=name, output=output, output_type="text")

    def _err(self, name: str, exc: Exception):
        from core.capability_registry import CapabilityExecutionResult
        logger.error("[vision] %s failed: %s", name, exc)
        return CapabilityExecutionResult(ok=False, name=name, error=str(exc))
