import sys
import os
import time
from html import escape as html_escape
from core.model_output import math_to_display
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QFileDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QUrl
from PyQt5.QtGui import QTextCursor


# ------------------------------------------------------------------
# Custom chat display with reliable file drag-and-drop.
# Subclassing QTextEdit is more reliable than event filters because
# QTextEdit handles DragEnter, DragMove, and Drop separately — an
# event filter that only intercepts DragEnter will not receive Drop.
# ------------------------------------------------------------------

class _ChatDisplay(QTextEdit):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptDrops(True)

    def _local_file_from(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            return urls[0].toLocalFile()
        return None

    def dragEnterEvent(self, event):
        if self._local_file_from(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._local_file_from(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._local_file_from(event)
        if path:
            self.file_dropped.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()


# ------------------------------------------------------------------
# Main window
# ------------------------------------------------------------------

class MainWindow(QMainWindow):
    # Signal used to safely push text to QTextEdit from a background thread
    message_ready = pyqtSignal(object)
    route_ready = pyqtSignal(object)
    processing_state_changed = pyqtSignal(bool)

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
        self.processing_state_changed.connect(self.update_send_button_state)
        
        self.is_processing = False

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

        # Chat display area — _ChatDisplay subclass handles file drag-and-drop
        self.chat_display = _ChatDisplay()
        self.chat_display.setStyleSheet("background-color: #0d0d0d; color: #e0e0e0; font-family: 'Courier New', Courier, monospace; font-size: 14px; border: none;")
        self.chat_display.file_dropped.connect(self._load_rag_file)
        main_layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("❯ Type a command...")
        self.input_field.setStyleSheet("background-color: #1a1a1a; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-size: 14px; border: 1px solid #333333; border-radius: 4px; padding: 8px;")
        self.input_field.returnPressed.connect(self.handle_return_pressed)

        btn_style = "background-color: #262626; color: #e0e0e0; font-family: 'Courier New', Courier, monospace; font-weight: bold; border: 1px solid #333333; border-radius: 4px; padding: 6px 12px;"

        self.send_button = QPushButton("Enter")
        self.send_button.setStyleSheet(btn_style)
        self.send_button.clicked.connect(self.handle_send_button_clicked)

        self.mic_button = QPushButton("Mic: OFF")
        self.mic_button.setCheckable(True)
        self.mic_button.setStyleSheet(btn_style)
        self.mic_button.clicked.connect(self.toggle_mic)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet(btn_style)
        self.stop_button.setToolTip("Stop FRIDAY from speaking")
        self.stop_button.clicked.connect(self.stop_speaking)

        self.file_button = QPushButton("@")
        self.file_button.setStyleSheet(btn_style)
        self.file_button.setToolTip("Load file as session context (or drag & drop onto chat)")
        self.file_button.setFixedWidth(36)
        self.file_button.clicked.connect(self.open_file_picker)

        input_layout.addWidget(self.mic_button)
        input_layout.addWidget(self.stop_button)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.file_button)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

        # Accept drops anywhere on the window as a fallback for areas
        # outside the _ChatDisplay (title bar, buttons, input row).
        self.setAcceptDrops(True)

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
        self.app_core.event_bus.subscribe("turn_started", lambda x: (
            self.set_companion_state("thinking"),
            self.processing_state_changed.emit(True)
        ))
        self.app_core.event_bus.subscribe("assistant_ack", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("assistant_progress", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("tool_started", lambda x: (
            self.set_companion_state("executing"),
            self.route_ready.emit(x),
        ))
        self.app_core.event_bus.subscribe("llm_started", lambda x: self.set_companion_state("thinking"))
        self.app_core.event_bus.subscribe("turn_completed", lambda x: (
            self.set_companion_state("idle"),
            self.processing_state_changed.emit(False)
        ))
        self.app_core.event_bus.subscribe("turn_failed", lambda x: (
            self.set_companion_state("idle"),
            self.processing_state_changed.emit(False)
        ))

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
    # File context (session RAG)
    # ------------------------------------------------------------------

    _SUPPORTED_EXTENSIONS = (
        ".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt", ".html", ".csv"
    )

    def open_file_picker(self):
        ext_filter = "Documents (*.pdf *.docx *.pptx *.xlsx *.md *.txt *.html *.csv)"
        path, _ = QFileDialog.getOpenFileName(self, "Load file as session context", "", ext_filter)
        if path:
            self._load_rag_file(path)

    def _load_rag_file(self, path: str):
        import threading
        suffix = os.path.splitext(path)[1].lower()
        if suffix not in self._SUPPORTED_EXTENSIONS:
            self._insert_status(f"Unsupported file type: {suffix}")
            return
        name = os.path.basename(path)
        self._insert_status(f"Loading '{name}'...")

        def _do_load():
            try:
                msg = self.app_core.load_session_rag_file(path)
                # message_ready is thread-safe; _status key routes to _insert_status
                self.message_ready.emit({"_status": f"Context loaded: {msg}"})
            except Exception as exc:
                self.message_ready.emit({"_status": f"Failed to load '{name}': {exc}"})

        threading.Thread(target=_do_load, daemon=True).start()

    def _insert_status(self, text: str):
        safe = html_escape(text)
        html = (
            f'<p align="center">'
            f'<span style="color:#5a9a7a;font-size:11px;">[ {safe} ]</span>'
            f'</p>'
        )
        self._insert_raw_html(html)

    # Window-level drop fallback — catches drops on any area outside _ChatDisplay
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self._load_rag_file(path)
                event.acceptProposedAction()
                return
        event.ignore()

    # ------------------------------------------------------------------
    # Async message sending
    # ------------------------------------------------------------------

    def update_send_button_state(self, is_processing):
        self.is_processing = is_processing
        if is_processing:
            self.send_button.setText("■")
            self.send_button.setStyleSheet("background-color: #8b0000; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-weight: bold; border: 1px solid #ff0000; border-radius: 4px; padding: 6px 12px;")
            self.send_button.setToolTip("Stop Task")
        else:
            self.send_button.setText("Enter")
            self.send_button.setStyleSheet("background-color: #262626; color: #e0e0e0; font-family: 'Courier New', Courier, monospace; font-weight: bold; border: 1px solid #333333; border-radius: 4px; padding: 6px 12px;")
            self.send_button.setToolTip("Send Message")

    def handle_return_pressed(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        # File paths and file:// URIs dropped or typed into the input field
        # are intercepted here before reaching the LLM. The app-level
        # process_input also has this guard as a final safety net.
        if text.startswith("/") and os.path.isfile(text):
            self._load_rag_file(text)
            return
        if text.startswith("file://"):
            from urllib.parse import urlparse, unquote
            try:
                path = unquote(urlparse(text).path)
                if os.path.isfile(path):
                    self._load_rag_file(path)
                    return
            except Exception:
                pass
        self.app_core.process_input(text, source="gui")

    def handle_send_button_clicked(self):
        if self.is_processing:
            self.app_core.cancel_current_task(announce=False)
        else:
            self.handle_return_pressed()

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

        # Background file-load completion — route to status bar, not chat bubble
        if "_status" in payload:
            self._insert_status(payload["_status"])
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
        display_text = math_to_display(text.strip()) if role != "user" else text.strip()
        safe = html_escape(display_text).replace("\n", "<br/>")
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
