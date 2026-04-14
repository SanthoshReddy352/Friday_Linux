import os
import queue
import shlex
import threading
from collections import deque

from prompt_toolkit.application import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea


CLI_STYLE = Style.from_dict(
    {
        "": "#e5e7eb bg:#020617",
        "header": "bg:#0b1220 #cbd5e1",
        "header.title": "bg:#0b1220 #7dd3fc bold",
        "header.dim": "bg:#0b1220 #94a3b8",
        "separator": "bg:#0f172a #1e293b",
        "transcript": "bg:#020617 #e5e7eb",
        "input-field": "bg:#020617 #f8fafc",
        "input.label": "#9ca3af bold",
        "prompt": "#7dd3fc bold",
        "text-area.prompt": "#7dd3fc bold",
        "footer": "bg:#0b1220 #94a3b8",
        "footer.strong": "bg:#0b1220 #e2e8f0 bold",
    }
)

SLASH_COMMANDS = [
    "/help",
    "/clear",
    "/stop",
    "/voice on",
    "/voice off",
    "/voice toggle",
    "/status",
    "/gui",
    "/exit",
]


class FridayTerminalUI:
    TRANSCRIPT_LABEL_WIDTH = 10

    def __init__(self, app_core):
        self.app_core = app_core
        self._running = True
        self._pending_ui_updates = queue.SimpleQueue()
        self._transcript_entries = deque(maxlen=400)
        self._command_in_flight = False

        self.transcript_area = TextArea(
            text="",
            read_only=True,
            focusable=False,
            wrap_lines=True,
            scrollbar=True,
            style="class:transcript",
        )
        self.input_field = TextArea(
            multiline=False,
            history=InMemoryHistory(),
            auto_suggest=AutoSuggestFromHistory(),
            completer=WordCompleter(SLASH_COMMANDS, ignore_case=True, sentence=True),
            complete_while_typing=True,
            prompt=HTML("<input.label>you</input.label> <prompt>></prompt> "),
            style="class:input-field",
            accept_handler=self._accept_input,
        )

        root_container = HSplit(
            [
                Window(
                    content=FormattedTextControl(self._header_fragments),
                    height=1,
                    style="class:header",
                ),
                Window(height=1, char="-", style="class:separator"),
                self.transcript_area,
                Window(height=1, char="-", style="class:separator"),
                self.input_field,
                Window(
                    content=FormattedTextControl(self._footer_fragments),
                    height=1,
                    style="class:footer",
                ),
            ]
        )

        self.application = Application(
            layout=Layout(root_container, focused_element=self.input_field),
            style=CLI_STYLE,
            full_screen=True,
            mouse_support=True,
            key_bindings=self._build_key_bindings(),
            refresh_interval=0.1,
            before_render=self._before_render,
        )

        self.app_core.event_bus.subscribe("conversation_message", self._queue_conversation_message)

    def run(self):
        self._emit_assistant_notice(self._build_startup_greeting())
        self.application.run(pre_run=self._drain_ui_updates, handle_sigint=False)

    def _build_key_bindings(self):
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            if getattr(self.app_core, "is_speaking", False):
                tts = getattr(self.app_core, "tts", None)
                if tts:
                    tts.stop()
                self._emit_assistant_notice("Speech interrupted.")
                return

            if self.input_field.buffer.text:
                self.input_field.buffer.reset()
                return

            self._emit_assistant_notice("Use /exit to quit.")

        @kb.add("c-l")
        def _(event):
            self._clear_transcript()

        return kb

    def _before_render(self, app):
        self._drain_ui_updates()

    def _header_fragments(self):
        return [
            ("class:header.title", " FRIDAY "),
            ("class:header", "text mode"),
            ("class:header.dim", "  |  Enter send  Tab complete  Ctrl+C interrupt  /help /exit "),
        ]

    def _footer_fragments(self):
        speech_state = "speaking" if getattr(self.app_core, "is_speaking", False) else "idle"
        run_state = "busy" if self._command_in_flight else "ready"
        router = getattr(self.app_core, "router", None)
        chat_model = os.path.basename(getattr(router, "llm_model_path", "gemma"))
        tool_model = os.path.basename(getattr(router, "tool_model_path", "qwen"))
        route_source = getattr(router, "current_route_source", "idle") if router else "idle"
        capabilities = getattr(self.app_core, "capabilities", None)
        disabled_skills = len(capabilities.disabled_skills()) if capabilities else 0

        return [
            ("class:footer", " mode:"),
            ("class:footer.strong", "text"),
            ("class:footer", "  speech:"),
            ("class:footer.strong", speech_state),
            ("class:footer", "  state:"),
            ("class:footer.strong", run_state),
            ("class:footer", "  route:"),
            ("class:footer.strong", route_source),
            ("class:footer", f"  chat:{chat_model}"),
            ("class:footer", f"  tool:{tool_model}"),
            ("class:footer", f"  disabled:{disabled_skills} "),
        ]

    def _accept_input(self, buffer):
        text = buffer.text.strip()
        if not text:
            return False

        if text.startswith("/"):
            if self._handle_slash_command(text):
                return False
            self._emit_assistant_notice("Unknown slash command. Try /help.")
            return False

        if self._command_in_flight:
            self._emit_assistant_notice("Please wait until the current request finishes.")
            return False

        self._command_in_flight = True
        self.application.invalidate()
        threading.Thread(target=self._process_cli_input, args=(text,), daemon=True).start()
        return False

    def _process_cli_input(self, text):
        try:
            self.app_core.process_input(text, source="cli")
        except Exception as exc:
            self._emit_assistant_notice(f"I hit an error while processing that: {exc}")
        finally:
            self._pending_ui_updates.put(("busy", False))
            self.application.invalidate()

    def _queue_conversation_message(self, payload):
        self._pending_ui_updates.put(("message", payload))
        self.application.invalidate()

    def _drain_ui_updates(self):
        while True:
            try:
                update_type, payload = self._pending_ui_updates.get_nowait()
            except queue.Empty:
                break

            if update_type == "message":
                self._append_transcript_message(payload)
            elif update_type == "busy":
                self._command_in_flight = bool(payload)

    def _append_transcript_message(self, payload):
        if not isinstance(payload, dict):
            return

        role = payload.get("role", "assistant")
        raw_text = str(payload.get("text", "")).strip()
        source = payload.get("source", role)
        if not raw_text:
            return

        if role == "user":
            label = "YOU"
        else:
            label = "FRIDAY" if source == "friday" else f"FRIDAY/{str(source).upper()}"

        self._transcript_entries.append(self._format_transcript_entry(label, raw_text))
        transcript = "\n".join(self._transcript_entries)
        self.transcript_area.buffer.set_document(
            Document(
                text=transcript,
                cursor_position=len(transcript),
            ),
            bypass_readonly=True,
        )

    def _format_transcript_entry(self, label, text):
        padded_label = f"{label:<{self.TRANSCRIPT_LABEL_WIDTH}}"
        indent = " " * self.TRANSCRIPT_LABEL_WIDTH
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return padded_label + normalized.replace("\n", f"\n{indent}")

    def _emit_assistant_notice(self, text, source="friday"):
        self.app_core.emit_message("assistant", text, source=source)

    def _clear_transcript(self):
        self._transcript_entries.clear()
        self.transcript_area.buffer.set_document(
            Document(text="", cursor_position=0),
            bypass_readonly=True,
        )
        self.application.invalidate()

    def _build_startup_greeting(self):
        checks = []
        router = getattr(self.app_core, "router", None)
        stt = getattr(self.app_core, "stt", None)
        tts = getattr(self.app_core, "tts", None)

        if router and os.path.exists(getattr(router, "llm_model_path", "")):
            checks.append("chat")
        if stt is not None:
            checks.append("voice input")
        if tts is not None:
            checks.append("speech")

        if checks == ["chat", "voice input", "speech"]:
            return "Hello. I'm FRIDAY — text mode. System check complete: chat, voice input, and speech are online."
        if checks:
            return f"Hello. I'm FRIDAY — text mode. System check complete: {', '.join(checks)} online."
        return "Hello. I'm FRIDAY — text mode. I started up, but some systems still need attention."

    def _handle_slash_command(self, text):
        try:
            parts = shlex.split(text)
        except ValueError:
            self._emit_assistant_notice("Couldn't parse that slash command.")
            return True

        if not parts:
            return True

        command = parts[0].lower()

        if command in {"/exit", "/quit"}:
            self._running = False
            self._emit_assistant_notice("Bye.")
            try:
                self.application.exit()
            except Exception:
                pass
            return True

        if command == "/help":
            self._emit_assistant_notice(
                "Commands:\n"
                "/help show commands\n"
                "/clear clear the transcript\n"
                "/stop stop current speech\n"
                "/voice on|off|toggle control the microphone\n"
                "/gui remind me about the legacy desktop UI\n"
                "/exit quit the session"
            )
            return True

        if command == "/clear":
            self._clear_transcript()
            return True

        if command == "/stop":
            tts = getattr(self.app_core, "tts", None)
            if tts:
                tts.stop()
            self._emit_assistant_notice("Speech interrupted.")
            return True

        if command == "/voice":
            stt = getattr(self.app_core, "stt", None)
            if stt is None:
                self._emit_assistant_notice("Voice input is not available in this session.")
                return True

            action = parts[1].lower() if len(parts) > 1 else "toggle"
            try:
                if action == "on":
                    stt.start_listening()
                    self._emit_assistant_notice("Voice listening enabled.")
                elif action == "off":
                    stt.stop_listening()
                    self._emit_assistant_notice("Voice listening disabled.")
                elif action == "toggle":
                    if getattr(stt, "is_listening", False):
                        stt.stop_listening()
                        self._emit_assistant_notice("Voice listening disabled.")
                    else:
                        stt.start_listening()
                        self._emit_assistant_notice("Voice listening enabled.")
                else:
                    self._emit_assistant_notice("Usage: /voice on, /voice off, or /voice toggle")
            except Exception as exc:
                self._emit_assistant_notice(f"I couldn't change the microphone state: {exc}")
            return True

        if command == "/gui":
            self._emit_assistant_notice("Launch the legacy window with: python main.py --gui")
            return True

        if command == "/status":
            router = getattr(self.app_core, "router", None)
            lane = getattr(router, "current_route_source", "unknown") if router else "unknown"
            speaking = "yes" if getattr(self.app_core, "is_speaking", False) else "no"
            listening = "yes" if getattr(getattr(self.app_core, "stt", None), "is_listening", False) else "no"
            self._emit_assistant_notice(
                f"Status: route={lane}, speaking={speaking}, listening={listening}."
            )
            return True

        return False


def start_cli(app_core):
    FridayTerminalUI(app_core).run()
