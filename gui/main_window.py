import sys
import os
import time
from html import escape as html_escape
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QTextCursor


# ------------------------------------------------------------------
# Background worker — runs process_input() off the main thread
# ------------------------------------------------------------------

class InputWorker(QObject):
    """Runs FridayApp.process_input in a QThread to avoid blocking the GUI."""
    finished = pyqtSignal()

    def __init__(self, app_core, text, source="gui"):
        super().__init__()
        self.app_core = app_core
        self.text = text
        self.source = source

    def run(self):
        try:
            self.app_core.process_input(self.text, source=self.source)
        except Exception as e:
            pass
        finally:
            self.finished.emit()


# ------------------------------------------------------------------
# Main window
# ------------------------------------------------------------------

class MainWindow(QMainWindow):
    # Signal used to safely push text to QTextEdit from a background thread
    message_ready = pyqtSignal(object)
    route_ready = pyqtSignal(object)

    def __init__(self, app_core):
        super().__init__()
        self.app_core = app_core
        self._worker_thread = None
        self._worker = None

        self.init_ui()
        self.load_theme()

        # Wire GUI callback — will be called from background thread, so use signal
        self.app_core.set_gui_callback(self._on_message_from_thread)
        self.message_ready.connect(self.render_message)
        self.route_ready.connect(self._on_route_event)

    def init_ui(self):
        self.setWindowTitle("FRIDAY")
        width = self.app_core.config.get('gui.window_width', 500)
        height = self.app_core.config.get('gui.window_height', 700)
        self.resize(width, height)

        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: #0d0d0d;")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Companion Display
        self.companion_display = QLabel("( ^_^ )")
        self.companion_display.setAlignment(Qt.AlignLeft)
        self.companion_display.setStyleSheet("font-family: 'Courier New', Courier, monospace; font-size: 16px; min-height: 30px; color: #a8a8a8;")
        main_layout.addWidget(self.companion_display)

        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("background-color: #0d0d0d; color: #e0e0e0; font-family: 'Courier New', Courier, monospace; font-size: 14px; border: none;")
        main_layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("❯ Type a command...")
        self.input_field.setStyleSheet("background-color: #1a1a1a; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-size: 14px; border: 1px solid #333333; border-radius: 4px; padding: 8px;")
        self.input_field.returnPressed.connect(self.send_message)

        btn_style = "background-color: #262626; color: #e0e0e0; font-family: 'Courier New', Courier, monospace; font-weight: bold; border: 1px solid #333333; border-radius: 4px; padding: 6px 12px;"

        self.send_button = QPushButton("Enter")
        self.send_button.setStyleSheet(btn_style)
        self.send_button.clicked.connect(self.send_message)

        self.mic_button = QPushButton("Mic: OFF")
        self.mic_button.setCheckable(True)
        self.mic_button.setStyleSheet(btn_style)
        self.mic_button.clicked.connect(self.toggle_mic)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet(btn_style)
        self.stop_button.setToolTip("Stop FRIDAY from speaking")
        self.stop_button.clicked.connect(self.stop_speaking)

        input_layout.addWidget(self.mic_button)
        input_layout.addWidget(self.stop_button)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

        # Animation State
        self.companion_state = "idle"
        self.companion_tick = 0
        self.companion_frames = {
            "idle": ["( ^_^ )", "( ^_^ )", "( ^_^ )", "( -_- )", "( ^_^ )"],
            "listening": ["( o_o ) •", "( o_o ) ••", "( o_o ) •••"],
            "thinking": ["( •_• )o", "( •_• )o.", "( •_• )o.."],
            "speaking": ["( >_< )", "( ^_^ )", "( >_< )", "( ^O^ )"],
            "executing": ["( ⌐■_■ )", "( ⌐■_■ )p", "( ⌐■_■ )q"]
        }
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_companion_frame)
        self.anim_timer.start(500)
        
        # Subscribe to State Changes
        self.app_core.event_bus.subscribe("gui_toggle_mic", lambda x: self.set_companion_state("listening" if x else "idle"))
        self.app_core.event_bus.subscribe("voice_response", lambda x: self.set_companion_state("speaking"))
        self.app_core.event_bus.subscribe("turn_started", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("assistant_ack", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("assistant_progress", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("tool_started", lambda x: (
            self.set_companion_state("executing"),
            self.route_ready.emit(x),
        ))
        self.app_core.event_bus.subscribe("llm_started", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("turn_completed", lambda x: self.set_companion_state("idle"))
        self.app_core.event_bus.subscribe("turn_failed", lambda x: self.set_companion_state("idle"))

    def set_companion_state(self, state):
        if self.companion_state != state:
            self.companion_state = state
            self.companion_tick = 0
            
    def update_companion_frame(self):
        # Auto-reset states based on app_core
        if self.companion_state == "speaking" and not getattr(self.app_core, "is_speaking", False):
            self.set_companion_state("idle")
            
        frames = self.companion_frames.get(self.companion_state, self.companion_frames["idle"])
        self.companion_display.setText(frames[self.companion_tick % len(frames)])
        self.companion_tick += 1

    def load_theme(self):
        # We explicitly skip the old dark_theme.qss to maintain our CLI exact styling
        pass

    # ------------------------------------------------------------------
    # Mic toggle
    # ------------------------------------------------------------------

    def toggle_mic(self):
        is_active = self.mic_button.isChecked()
        if is_active:
            self.mic_button.setText("Mic: ON")
            self.mic_button.setStyleSheet("background-color: #004d40; color: #4db6ac; font-family: 'Courier New', Courier, monospace; font-weight: bold; border: 1px solid #4db6ac; border-radius: 4px; padding: 6px 12px;")
        else:
            self.mic_button.setText("Mic: OFF")
            self.mic_button.setStyleSheet("background-color: #262626; color: #e0e0e0; font-family: 'Courier New', Courier, monospace; font-weight: bold; border: 1px solid #333333; border-radius: 4px; padding: 6px 12px;")
        self.app_core.event_bus.publish("gui_toggle_mic", is_active)

    # ------------------------------------------------------------------
    # Stop / barge-in from GUI button
    # ------------------------------------------------------------------

    def stop_speaking(self):
        tts = getattr(self.app_core, 'tts', None)
        if tts:
            tts.stop()

    # ------------------------------------------------------------------
    # Async message sending
    # ------------------------------------------------------------------

    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()

        # Disable input while processing to prevent double-sends
        self.send_button.setEnabled(False)
        self.input_field.setEnabled(False)

        # Run process_input in a background QThread
        self._worker_thread = QThread()
        self._worker = InputWorker(self.app_core, text, source="gui")
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._on_worker_done)
        self._worker_thread.start()

    def _on_worker_done(self):
        """Re-enable input after background processing finishes."""
        self.send_button.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()

    # ------------------------------------------------------------------
    # Thread-safe GUI callbacks
    # ------------------------------------------------------------------

    def _on_message_from_thread(self, payload):
        """Called from background thread — emit signal to update GUI safely."""
        self.message_ready.emit(payload)

    def render_message(self, payload):
        if isinstance(payload, str):
            self._insert_bubble("assistant", payload)
            return

        role = payload.get("role", "assistant")
        text = payload.get("text", "")
        if not text:
            return
        self._insert_bubble(role, text)

    def _on_route_event(self, payload):
        if not isinstance(payload, dict):
            return
        tool = payload.get("tool_name", "")
        if not tool:
            return
        args = payload.get("args") or {}
        label = tool.replace("_", " ")
        key = next((k for k in ("query", "topic", "text", "path", "url", "app") if k in args), None)
        suffix = f" ({html_escape(str(args[key])[:35])})" if key else ""
        safe = f"▶ {html_escape(label)}{html_escape(suffix)}"
        html = (
            f'<p align="center">'
            f'<span style="color:#3a5a4a;font-size:11px;">{safe}</span>'
            f'</p>'
        )
        self._insert_raw_html(html)

    def _insert_bubble(self, role: str, text: str):
        safe = html_escape(text.strip()).replace("\n", "<br/>")
        ts = time.strftime("%H:%M")
        if role == "user":
            html = (
                '<table width="100%" cellpadding="5" cellspacing="0" border="0">'
                '<tr><td width="20%">&nbsp;</td>'
                '<td align="right" bgcolor="#0d1e38">'
                f'<span style="color:#8ab4ff;font-size:10px;font-weight:bold;">YOU</span>'
                f'&nbsp;<span style="color:#3a5a7a;font-size:9px;">{ts}</span><br/>'
                f'<span style="color:#ccdeff;font-size:13px;">{safe}</span>'
                '</td></tr></table>'
                '<p style="margin:0;padding:0;font-size:3px;">&nbsp;</p>'
            )
        else:
            html = (
                '<table width="100%" cellpadding="5" cellspacing="0" border="0">'
                '<tr><td align="left" bgcolor="#061410">'
                f'<span style="color:#5dffbf;font-size:10px;font-weight:bold;">FRIDAY</span>'
                f'&nbsp;<span style="color:#2a4a3a;font-size:9px;">{ts}</span><br/>'
                f'<span style="color:#b0f0cc;font-size:13px;">{safe}</span>'
                '</td><td width="20%">&nbsp;</td></tr></table>'
                '<p style="margin:0;padding:0;font-size:3px;">&nbsp;</p>'
            )
        self._insert_raw_html(html)

    def _insert_raw_html(self, html: str):
        cursor = QTextCursor(self.chat_display.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # kept for backward compat — internal callers replaced by _insert_bubble
    def add_user_message(self, text, source="gui"):
        self._insert_bubble("user", text)

    def add_assistant_message(self, text, source="friday"):
        self._insert_bubble("assistant", text)


def start_gui(app_core):
    app = QApplication(sys.argv)
    window = MainWindow(app_core)
    window.show()
    sys.exit(app.exec_())
