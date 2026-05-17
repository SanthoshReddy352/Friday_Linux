from core.plugin_manager import FridayPlugin
from core.logger import logger
import threading
import re
from datetime import datetime
from urllib.parse import urlparse
from .stt import STTEngine
from .tts import TextToSpeech
from core.model_output import strip_model_artifacts


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def _ordinal_suffix(day):
    if 10 <= day % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _spoken_date(day, month, year):
    try:
        dt = datetime(int(year), int(month), int(day))
    except Exception:
        return ""
    return f"{dt.day}{_ordinal_suffix(dt.day)} {dt.strftime('%B')} {dt.year}"


def _replace_slash_date(match):
    first = int(match.group(1))
    second = int(match.group(2))
    year = int(match.group(3))
    if first > 31 or second > 31:
        return match.group(0)
    if first > 12:
        day, month = first, second
    elif second > 12:
        day, month = second, first
    else:
        day, month = first, second
    return _spoken_date(day, month, year) or match.group(0)


def _replace_iso_date(match):
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    return _spoken_date(day, month, year) or match.group(0)


def _replace_url(match):
    parsed = urlparse(match.group(0).rstrip(".,)"))
    host = (parsed.netloc or "").removeprefix("www.")
    return f"link from {host}" if host else "link"


def sanitize_for_speech(text):
    if not text:
        return ""

    cleaned = strip_model_artifacts(text)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"https?://[^\s)]+", _replace_url, cleaned)
    cleaned = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", _replace_slash_date, cleaned)
    cleaned = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", _replace_iso_date, cleaned)
    cleaned = re.sub(r"```[a-zA-Z0-9_-]*", "", cleaned).replace("```", "")
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[*+-]\s+", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*\d+\.\s+", "", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"[_*~]", "", cleaned)
    cleaned = EMOJI_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


class VoiceIOPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "VoiceIO"

        self.tts = TextToSpeech(app)
        self.stt = STTEngine(app)

        # Expose TTS on app_core so STT can call app_core.tts.stop()
        app.tts = self.tts
        app.stt = self.stt

        self.on_load()

    def on_load(self):
        # Speak all voice_response events using chunked (interruptible) TTS
        self.app.event_bus.subscribe("voice_response", self.handle_speak)

        # Voice toggle commands
        self.app.router.register_tool({
            "name": "enable_voice",
            "description": "Enable the microphone and start listening for voice commands.",
            "parameters": {}
        }, lambda t, a: self.start_listening())

        self.app.router.register_tool({
            "name": "disable_voice",
            "description": "Disable the microphone and stop listening for voice commands.",
            "parameters": {}
        }, lambda t, a: self.stop_listening())

        self.app.router.register_tool({
            "name": "set_voice_mode",
            "description": "Switch voice listening mode between persistent, wake-word, on-demand, or manual.",
            "parameters": {
                "mode": "string - one of persistent, wake_word, on_demand, manual"
            }
        }, self.set_voice_mode)

        # GUI mic toggle
        self.app.event_bus.subscribe("gui_toggle_mic", self.toggle_mic)
        self.app.event_bus.subscribe("voice_activation_requested", self.activate_voice)
        self.app.event_bus.subscribe("media_control_mode_changed", lambda _payload: self.stt._emit_runtime_state())

        # Warm voice dependencies in the background so first-use latency is lower.
        threading.Thread(target=self._warm_voice_stack, daemon=True).start()

        logger.info("VoiceIOPlugin loaded.")

    def handle_speak(self, text):
        if getattr(self.app, 'telegram_turn_active', False):
            return
        if getattr(self.app, 'tts_muted', False):
            return
        if not text:
            return
        clean_text = sanitize_for_speech(text)
        if not clean_text:
            return
        self.tts.speak_chunked(clean_text)

    def start_listening(self, text=None):
        return "Voice listening enabled." if self.stt.activate_for_invocation(source="command") else "I couldn't enable voice listening."

    def stop_listening(self, text=None):
        return "Voice listening disabled." if self.stt.stop_listening() else "I couldn't disable voice listening."

    def set_voice_mode(self, text=None, args=None):
        args = dict(args or {})
        mode = str(args.get("mode") or "").strip().lower()
        raw_text = str(text or "").lower()
        if not mode:
            if "persistent" in raw_text or "always on" in raw_text:
                mode = "persistent"
            elif "wake word" in raw_text or "wake-word" in raw_text or "wakeword" in raw_text:
                mode = "wake_word"
            elif "manual" in raw_text or "off" in raw_text:
                mode = "manual"
            elif "on demand" in raw_text or "on-demand" in raw_text or "ondemand" in raw_text:
                mode = "on_demand"
        mode = self.app.set_listening_mode(mode)
        label = mode.replace("_", "-")
        if mode == "persistent":
            return "Voice mode set to persistent. I'll keep listening between turns."
        if mode == "wake_word":
            return "Voice mode set to wake-word. I'll stay armed for the wake word, then open a short session."
        if mode == "manual":
            return "Voice mode set to manual. I'll only listen when you turn the microphone on."
        return f"Voice mode set to {label}. I'll listen for one turn, then mute again."

    def toggle_mic(self, state):
        """Called from the GUI toggle switch."""
        if state:
            self.stt.start_listening()
        else:
            self.stt.stop_listening()

    def activate_voice(self, payload=None):
        source = "button"
        if isinstance(payload, dict):
            source = payload.get("source") or source
        self.stt.activate_for_invocation(source=source)

    def _warm_voice_stack(self):
        self.tts.warm_up()
        self.stt.warm_up()


def setup(app):
    return VoiceIOPlugin(app)
