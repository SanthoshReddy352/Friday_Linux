import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QTextEdit, QLineEdit, QPushButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject


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

    def init_ui(self):
        self.setWindowTitle("FRIDAY")
        width = self.app_core.config.get('gui.window_width', 500)
        height = self.app_core.config.get('gui.window_height', 700)
        self.resize(width, height)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        main_layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command...")
        self.input_field.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)

        self.mic_button = QPushButton("🎤 Mic: OFF")
        self.mic_button.setCheckable(True)
        self.mic_button.clicked.connect(self.toggle_mic)

        # Stop / barge-in button
        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.setToolTip("Stop FRIDAY from speaking")
        self.stop_button.clicked.connect(self.stop_speaking)

        input_layout.addWidget(self.mic_button)
        input_layout.addWidget(self.stop_button)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

    def load_theme(self):
        theme_path = os.path.join(os.path.dirname(__file__), 'styles', 'dark_theme.qss')
        if os.path.exists(theme_path):
            with open(theme_path, 'r') as f:
                self.setStyleSheet(f.read())
        else:
            print(f"Theme file not found: {theme_path}")

    # ------------------------------------------------------------------
    # Mic toggle
    # ------------------------------------------------------------------

    def toggle_mic(self):
        is_active = self.mic_button.isChecked()
        if is_active:
            self.mic_button.setText("🎤 Mic: ON")
            self.mic_button.setStyleSheet("background-color: #ff3366; color: white;")
        else:
            self.mic_button.setText("🎤 Mic: OFF")
            self.mic_button.setStyleSheet("")
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
            self.add_assistant_message(payload)
            return

        role = payload.get("role", "assistant")
        text = payload.get("text", "")
        source = payload.get("source", role)

        if role == "user":
            self.add_user_message(text, source)
        else:
            self.add_assistant_message(text, source)

    def add_user_message(self, text, source="gui"):
        label = "You (Voice)" if source == "voice" else "You"
        self.chat_display.append(f"<b>{label}:</b> {text}")

    def add_assistant_message(self, text, source="friday"):
        label = "FRIDAY" if source == "friday" else f"FRIDAY ({source.title()})"
        self.chat_display.append(f"<b style='color:#00ffcc;'>{label}:</b> {text}")


def start_gui(app_core):
    app = QApplication(sys.argv)
    window = MainWindow(app_core)
    window.show()
    sys.exit(app.exec_())
