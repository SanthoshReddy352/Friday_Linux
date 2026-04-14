import sys
import random
import math
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox, QPushButton, QFrame, QTextEdit
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF, QRectF, QThread, QObject
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QLinearGradient, QFont
from modules.voice_io.audio_devices import list_audio_input_devices

# --- Colors ---
PRIMARY_COLOR = QColor("#00FFFF")  # Cyan
ACCENT_COLOR = QColor("#FFFFFF")   # White
BG_COLOR = QColor("#000000")       # Black
WARNING_COLOR = QColor("#FFA500")  # Orange (for Pause/Warning)
THINKING_COLOR = QColor("#8A2BE2") # BlueViolet (for Thinking)
SPEAKING_COLOR = QColor("#00FF00") # Green (for Speaking)

HUD_TEXT_MAX_CHARS = 420
HUD_TEXT_MAX_LINES = 8


def format_hud_message(role, text, max_chars=HUD_TEXT_MAX_CHARS, max_lines=HUD_TEXT_MAX_LINES):
    prefix = "USER" if role == "user" else "FRIDAY"
    cleaned = (text or "").strip()
    if not cleaned:
        return f"{prefix}:"

    compact = " ".join(cleaned.split())
    truncated_by_chars = len(compact) > max_chars
    compact = compact[:max_chars].rstrip()

    wrapped_lines = []
    current_line = ""
    for word in compact.split():
        candidate = f"{current_line} {word}".strip()
        if len(candidate) <= 52:
            current_line = candidate
        else:
            if current_line:
                wrapped_lines.append(current_line)
            current_line = word
    if current_line:
        wrapped_lines.append(current_line)

    truncated_by_lines = len(wrapped_lines) > max_lines
    visible_lines = wrapped_lines[:max_lines]
    message = "\n".join(visible_lines)
    if truncated_by_chars or truncated_by_lines:
        message = f"{message}\n..."
    return f"{prefix}: {message}" if "\n" not in message else f"{prefix}: {visible_lines[0]}\n" + "\n".join(visible_lines[1:] + (["..."] if (truncated_by_chars or truncated_by_lines) else []))

class HexagonPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.opacity = 50
        self.increasing = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(100)

    def animate(self):
        if self.increasing:
            self.opacity += 5
            if self.opacity >= 200: self.increasing = False
        else:
            self.opacity -= 5
            if self.opacity <= 50: self.increasing = True
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        size = 30
        rows = 4
        cols = 3
        x_offset = 20
        y_offset = 50

        for r in range(rows):
            for c in range(cols):
                color = QColor(PRIMARY_COLOR)
                current_opacity = self.opacity
                if (r + c) % 2 == 0:
                   current_opacity = max(50, current_opacity - 50)
                
                color.setAlpha(current_opacity)
                painter.setPen(QPen(color, 2))
                
                x = x_offset + c * (size * 1.5)
                y = y_offset + r * (size * math.sqrt(3))
                if c % 2 == 1:
                    y += size * math.sqrt(3) / 2
                
                self.draw_hexagon(painter, x, y, size)

    def draw_hexagon(self, painter, x, y, size):
        points = []
        for i in range(6):
            angle_deg = 60 * i
            angle_rad = math.radians(angle_deg)
            px = x + size * math.cos(angle_rad)
            py = y + size * math.sin(angle_rad)
            points.append(QPointF(px, py))
        painter.drawPolygon(QPolygonF(points))

class TelemetryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.bar_heights = [20, 40, 60, 30]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(100)

    def animate(self):
        self.bar_heights = [random.randint(10, 100) for _ in range(4)]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen(ACCENT_COLOR)
        pen.setWidth(2)
        painter.setPen(pen)
        
        path_points = [
            QPointF(10, 200), QPointF(50, 240), QPointF(150, 240), QPointF(180, 200)
        ]
        painter.drawPolyline(QPolygonF(path_points))
        
        bar_width = 30
        gap = 10
        start_x = 20
        base_y = 150
        
        painter.setBrush(QBrush(PRIMARY_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        
        for i, h in enumerate(self.bar_heights):
            x = start_x + i * (bar_width + gap)
            painter.drawRect(QRectF(x, base_y - h, bar_width, h))

class CentralReactor(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle_outer = 0
        self.angle_inner = 0
        self.state = "idle" # idle, listening, thinking, speaking
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(30)

    def animate(self):
        speed_outer = 2
        speed_inner = 4
        
        if self.state == "listening":
            speed_outer = 4
            speed_inner = 8
        elif self.state == "thinking":
            speed_outer = 8
            speed_inner = 12
        elif self.state == "speaking":
            speed_outer = 5
            speed_inner = 2
            
        self.angle_outer = (self.angle_outer + speed_outer) % 360
        self.angle_inner = (self.angle_inner - speed_inner) % 360
        self.update()

    def set_state(self, state):
        self.state = state
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        main_color = PRIMARY_COLOR
        if self.state == "listening":
            main_color = PRIMARY_COLOR
        elif self.state == "thinking":
            main_color = THINKING_COLOR
        elif self.state == "speaking":
            main_color = SPEAKING_COLOR
        
        # Core
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(main_color))
        core_radius = 20
        pulse = (math.sin(self.angle_outer * 0.1) + 1) * 5
        painter.drawEllipse(QPointF(center_x, center_y), core_radius + pulse, core_radius + pulse)

        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Middle Ring
        pen = QPen(main_color)
        pen.setWidth(12)
        pen.setDashPattern([10, 10]) 
        painter.setPen(pen)
        
        radius_mid = 100
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.angle_outer)
        painter.drawEllipse(QPointF(0, 0), radius_mid, radius_mid)
        painter.restore()

        # Inner Ring
        pen = QPen(ACCENT_COLOR)
        pen.setWidth(4)
        pen.setDashPattern([5, 5])
        painter.setPen(pen)
        
        radius_inner = 70
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.angle_inner)
        painter.drawEllipse(QPointF(0, 0), radius_inner, radius_inner)
        painter.restore()

        # Outer Bracket
        pen = QPen(main_color)
        pen.setWidth(3)
        painter.setPen(pen)
        radius_outer = 130
        rect_outer = QRectF(center_x - radius_outer, center_y - radius_outer, 2*radius_outer, 2*radius_outer)
        painter.drawArc(rect_outer, 45 * 16, 90 * 16)
        painter.drawArc(rect_outer, 225 * 16, 90 * 16)

class DeviceDiscoveryThread(QThread):
    devices_found = pyqtSignal(list)

    def run(self):
        try:
            from modules.voice_io.audio_devices import list_audio_input_devices
            devices = list_audio_input_devices()
            self.devices_found.emit(devices)
        except Exception as e:
            from core.logger import logger
            logger.error(f"DeviceDiscoveryThread: Error listing devices: {e}")
            self.devices_found.emit([])

class MicSelector(QFrame):
    device_selected = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 200); border: 1px solid #00FFFF; border-radius: 10px;")
        self.setFixedWidth(250)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("MICROPHONE SELECT")
        label.setStyleSheet("color: #00FFFF; font-weight: bold; border: none;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        self.combo = QComboBox()
        self.combo.setStyleSheet("""
            QComboBox {
                background-color: #1a1a1a;
                color: white;
                border: 1px solid #333;
                padding: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: white;
                selection-background-color: #00FFFF;
            }
        """)
        layout.addWidget(self.combo)
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(10000) # Refresh every 10s (was 5s)
        
        self.discovery_thread = None
        self.combo.currentIndexChanged.connect(self.on_selection_changed)
        self.refresh_devices()

    def refresh_devices(self):
        if self.discovery_thread and self.discovery_thread.isRunning():
            return

        if self.combo.count() == 0:
            self.combo.addItem("Searching for devices...", None)

        self.discovery_thread = DeviceDiscoveryThread()
        self.discovery_thread.devices_found.connect(self._on_devices_found)
        self.discovery_thread.start()

    def _on_devices_found(self, devices):
        try:
            current_id = self.combo.currentData()
            self.combo.blockSignals(True)
            self.combo.clear()

            if not devices:
                self.combo.addItem("No microphones found", None)
            else:
                for device in devices:
                    prefix = "[Default] " if device.is_default else ""
                    suffix = f" ({device.backend})"
                    self.combo.addItem(f"{prefix}{device.label}{suffix}", device.target)

            if current_id is not None:
                for index in range(self.combo.count()):
                    if self.combo.itemData(index) == current_id:
                        self.combo.setCurrentIndex(index)
                        break
            elif self.combo.count() > 0 and devices:
                # If no selection, try to select the default one
                for index in range(self.combo.count()):
                    label = self.combo.itemText(index)
                    if "[Default]" in label:
                        self.combo.setCurrentIndex(index)
                        break
            
            self.combo.blockSignals(False)
        except Exception as e:
            from core.logger import logger
            logger.error(f"MicSelector: Error updating combo: {e}")

    def on_selection_changed(self, index):
        if index >= 0:
            device_id = self.combo.itemData(index)
            self.device_selected.emit(device_id)

class JarvisHUD(QMainWindow):
    message_ready = pyqtSignal(object)
    shutdown_signal = pyqtSignal()

    def __init__(self, app_core):
        super().__init__()
        self.app_core = app_core
        self.is_paused = False
        self.drag_pos = None
        
        self.setWindowTitle("FRIDAY HUD")
        self.resize(1000, 600)
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: rgba(0, 0, 0, 150);")
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left Panel
        self.left_panel = HexagonPanel()
        main_layout.addWidget(self.left_panel)
        
        # Center
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(16, 16, 16, 16)
        center_layout.setSpacing(14)
        self.reactor = CentralReactor()
        self.reactor.setMinimumSize(320, 320)
        center_layout.addWidget(self.reactor, stretch=5)
        
        # Subtitle area for voice transcript
        self.transcript_panel = QFrame()
        self.transcript_panel.setStyleSheet(
            "background-color: rgba(0, 0, 0, 180);"
            "border: 1px solid rgba(0, 255, 255, 120);"
            "border-radius: 8px;"
        )
        transcript_layout = QVBoxLayout(self.transcript_panel)
        transcript_layout.setContentsMargins(10, 8, 10, 8)
        transcript_layout.setSpacing(6)

        self.transcript_title = QLabel("LIVE TRANSCRIPT")
        self.transcript_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.transcript_title.setStyleSheet(
            "color: #00FFFF; font-family: 'Courier New'; font-size: 12px; font-weight: bold; border: none;"
        )
        transcript_layout.addWidget(self.transcript_title)

        self.subtitle_label = QTextEdit()
        self.subtitle_label.setReadOnly(True)
        self.subtitle_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.subtitle_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.subtitle_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.subtitle_label.setStyleSheet(
            "color: white;"
            "font-family: 'Courier New';"
            "font-size: 16px;"
            "background-color: transparent;"
            "border: none;"
            "padding: 0px;"
        )
        self.subtitle_label.setMinimumHeight(120)
        self.subtitle_label.setMaximumHeight(150)
        transcript_layout.addWidget(self.subtitle_label)

        center_layout.addWidget(self.transcript_panel, stretch=0)

        self.status_label = QLabel("route: idle | lane: idle | disabled skills: 0")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #9ae6ff; font-family: 'Courier New'; font-size: 12px;")
        center_layout.addWidget(self.status_label, stretch=0)
        
        main_layout.addLayout(center_layout, stretch=2)
        
        # Right Panel
        self.right_panel_container = QVBoxLayout()
        self.telemetry = TelemetryPanel()
        self.right_panel_container.addWidget(self.telemetry, stretch=3)
        
        self.mic_selector = MicSelector()
        self.mic_selector.device_selected.connect(self.on_mic_selected)
        self.right_panel_container.addWidget(self.mic_selector, stretch=1)
        
        self.stop_btn = QPushButton("TERMINATE OUTPUT")
        self.stop_btn.setStyleSheet("background-color: #800; color: white; border: 1px solid red; padding: 10px; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_speaking)
        self.right_panel_container.addWidget(self.stop_btn)
        
        main_layout.addLayout(self.right_panel_container)

        # Connect core signals
        self.app_core.set_gui_callback(self._on_message_from_thread)
        self.message_ready.connect(self.render_message)
        self.shutdown_signal.connect(self.close)
        
        # Status subscriptions
        self.reactor.clicked.connect(self.toggle_pause_everything)
        self.app_core.event_bus.subscribe("gui_toggle_mic", self._on_mic_toggle)
        self.app_core.event_bus.subscribe("voice_response", lambda x: self.reactor.set_state("speaking"))
        self.app_core.event_bus.subscribe("system_shutdown", lambda x: self.shutdown_signal.emit())
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.check_status)
        self.status_timer.start(200)

        # Auto-start mic for voice-only interaction
        QTimer.singleShot(1000, lambda: self.app_core.event_bus.publish("gui_toggle_mic", True))

    def toggle_pause_everything(self):
        """Toggle mic ON/OFF with sequential logic for Bluetooth stability."""
        from core.logger import logger
        # Check current software gate state
        is_listening = getattr(self.app_core.stt, "is_listening", False)
        new_state = not is_listening
        
        logger.info(f"HUD: Reactor clicked. Toggling pause state. New Gate State: {new_state}")
        
        # Get natural phrase from Greeter plugin if available
        phrase = ""
        greeter = next((p for p in self.app_core.plugin_manager.plugins if p.name == "Greeter"), None)
        
        if not new_state:
            # --- PAUSING ---
            # Gate mic off immediately to stop input
            self.app_core.event_bus.publish("gui_toggle_mic", False)
            self.stop_speaking()
            self.reactor.set_state("idle")
            phrase = greeter.get_pause_phrase() if greeter else "I am going offline, sir."
            self._set_transcript_text("assistant", phrase)
            self.app_core.event_bus.publish("voice_response", phrase)
        else:
            # --- UNPAUSING / INTERRUPTING ---
            # 1. Update UI and State
            phrase = greeter.get_unpause_phrase() if greeter else "Back online, sir."
            self._set_transcript_text("assistant", phrase)
            
            # 2. Speak first (A2DP playback)
            self.app_core.event_bus.publish("voice_response", phrase)
            
            # 3. Wait for playback to likely finish or establish focus before opening mic gate (HFP/HSP)
            # This is the key for Bluetooth headsets.
            QTimer.singleShot(1500, lambda: self.app_core.event_bus.publish("gui_toggle_mic", True))
            
        QTimer.singleShot(2500, lambda: self.subtitle_label.clear())

    def check_status(self):
        # Update reactor state based on app core
        if self.app_core.is_speaking:
            self.reactor.set_state("speaking")
        elif getattr(self.app_core.stt, "is_listening", False):
            # This is a bit tricky, maybe add a "thinking" state detection
            if getattr(self.app_core.router, "is_thinking", False):
                self.reactor.set_state("thinking")
            else:
                self.reactor.set_state("listening")
        else:
            self.reactor.set_state("idle")

        router = getattr(self.app_core, "router", None)
        capabilities = getattr(self.app_core, "capabilities", None)
        route_source = getattr(router, "current_route_source", "idle") if router else "idle"
        lane = getattr(router, "current_model_lane", "idle") if router else "idle"
        disabled_count = len(capabilities.disabled_skills()) if capabilities else 0
        self.status_label.setText(
            f"route: {route_source} | lane: {lane} | disabled skills: {disabled_count}"
        )

    def _on_mic_toggle(self, active):
        if active:
            self.reactor.set_state("listening")
        else:
            self.reactor.set_state("idle")

    def stop_speaking(self):
        if self.app_core.tts:
            self.app_core.tts.stop()

    def on_mic_selected(self, device_id):
        from core.logger import logger
        logger.info(f"HUD: Microphone changed to device: {device_id}")
        if self.app_core.stt:
            if hasattr(self.app_core.stt, 'set_device'):
                self.app_core.stt.set_device(device_id)
                label = getattr(self.app_core.stt, "device_label", "selected device")
                self._set_transcript_text("assistant", f"Microphone switched to {label}")
                QTimer.singleShot(2000, lambda: self.subtitle_label.clear())

    def mousePressEvent(self, event):
        # Allow dragging the frameless window
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def closeEvent(self, event):
        """Perform core app shutdown when the window closes."""
        from core.logger import logger
        logger.info("HUD: closeEvent triggered. Shutting down system...")
        self.app_core.shutdown()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def _on_message_from_thread(self, payload):
        self.message_ready.emit(payload)

    def render_message(self, payload):
        from core.logger import logger
        text = payload.get("text", "")
        role = payload.get("role", "assistant")
        logger.info(f"HUD: Rendering message from {role}: {text[:50]}...")
        self._set_transcript_text(role, text)

    def _set_transcript_text(self, role, text):
        self.subtitle_label.setPlainText(format_hud_message(role, text))
        self.subtitle_label.verticalScrollBar().setValue(0)

def start_hud(app_core):
    app = QApplication(sys.argv)
    window = JarvisHUD(app_core)
    window.show()
    sys.exit(app.exec())
