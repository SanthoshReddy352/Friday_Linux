import math
import random
import sys
import time
import logging

from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.voice_io.audio_devices import list_audio_input_devices


logger = logging.getLogger(__name__)

HUD_TEXT_MAX_CHARS = 420
HUD_TEXT_MAX_LINES = 8

BG = "#020104"
PANEL_BG = "rgba(7, 8, 14, 230)"
PANEL_BORDER = "rgba(168, 84, 255, 100)"
TEXT = "#d9fbff"
TEXT_DIM = "#8bb7c4"
CYAN = "#4deaff"
BLUE = "#4e82ff"
GREEN = "#5dffbf"
AMBER = "#ffcc66"
RED = "#ff6376"
PURPLE = "#b95cff"
MAGENTA = "#df7bff"
MUTED = "#51606b"


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
        if len(candidate) <= 56:
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
    if "\n" not in message:
        return f"{prefix}: {message}"
    return f"{prefix}: {visible_lines[0]}\n" + "\n".join(
        visible_lines[1:] + (["..."] if (truncated_by_chars or truncated_by_lines) else [])
    )


VOICE_MODE_LABELS = {
    "persistent": "PERSISTENT",
    "wake_word": "WAKE-WORD",
    "on_demand": "ON-DEMAND",
    "manual": "MANUAL",
}


def format_voice_mode_label(mode):
    normalized = str(mode or "").strip().lower().replace("-", "_")
    return VOICE_MODE_LABELS.get(normalized, "PERSISTENT")


def format_voice_runtime_status(state):
    state = dict(state or {})
    ui_state = str(state.get("ui_state") or "muted").upper()
    if state.get("wake_transcript_fallback") and state.get("wake_armed"):
        gate = "TRANSCRIPT WAKE"
    elif state.get("actively_transcribing"):
        gate = "OPEN"
    elif state.get("wake_armed"):
        gate = "ARMED"
    else:
        gate = "CLOSED"
    device = state.get("device_label") or "System default"
    rejected = state.get("last_rejected_reason") or "None"
    if rejected == "waiting for wake word":
        rejected = "None"
    return {
        "state": ui_state,
        "gate": gate,
        "device": device,
        "rejected": rejected,
        "wake_strategy": state.get("wake_strategy") or "Wake model",
    }


def panel_style(border=PANEL_BORDER):
    return (
        f"background-color: {PANEL_BG};"
        f"border: 1px solid {border};"
        "border-radius: 8px;"
    )


def label_style(color=TEXT_DIM, size=11, weight="normal"):
    return (
        f"color: {color};"
        "font-family: 'JetBrains Mono', 'Courier New', monospace;"
        f"font-size: {size}px;"
        f"font-weight: {weight};"
        "letter-spacing: 0px;"
        "border: none;"
    )


class TechPanel(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setStyleSheet(panel_style())
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 12, 14, 14)
        self.layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(label_style(CYAN, 12, "bold"))
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        self.indicator = QLabel("ONLINE")
        self.indicator.setStyleSheet(label_style(GREEN, 10, "bold"))
        title_row.addWidget(self.indicator)
        self.layout.addLayout(title_row)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(9)
        self.layout.addLayout(self.body, stretch=1)


class ParticleGlobeReactor(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        rng = random.Random(42)
        self.stars = [
            (
                rng.random(),
                rng.random(),
                rng.uniform(0.45, 1.8),
                rng.uniform(0.18, 0.72),
                rng.uniform(0, math.tau),
            )
            for _ in range(165)
        ]
        self.particles = []
        count = 2200
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        for index in range(count):
            z = 1.0 - (2.0 * (index + 0.5) / count)
            ring = math.sqrt(max(0.0, 1.0 - z * z))
            theta = index * golden_angle
            shell_bias = rng.uniform(0.82, 1.0) ** 0.38
            self.particles.append(
                {
                    "x": ring * math.cos(theta),
                    "y": z,
                    "z": ring * math.sin(theta),
                    "shell": shell_bias,
                    "size": rng.uniform(0.65, 1.65),
                    "phase": rng.uniform(0, math.tau),
                    "twinkle": rng.uniform(0.75, 1.25),
                }
            )

        self.state = "muted"
        self.phase = 0.0
        self.wave_phase = 0.0
        self.speech_energy = 0.0
        self._speaking_until = 0.0
        self.setMinimumSize(520, 520)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(24)

    def set_state(self, state):
        self.state = str(state or "muted")
        self.update()

    def pulse_speaking(self):
        self._speaking_until = time.monotonic() + 2.6
        self.speech_energy = max(self.speech_energy, 1.0)
        self.state = "speaking"
        self.update()

    def animate(self):
        active_speech = self.state == "speaking" or time.monotonic() < self._speaking_until
        target_energy = 1.0 if active_speech else 0.0
        self.speech_energy += (target_energy - self.speech_energy) * 0.10
        if active_speech:
            base_speed = 0.0
        else:
            base_speed = 0.006
            if self.state == "processing":
                base_speed = 0.013
            elif self.state == "listening":
                base_speed = 0.01
            elif self.state == "armed":
                base_speed = 0.008
        self.phase += base_speed
        self.wave_phase += 0.20 * self.speech_energy
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def _state_color(self):
        if self.state == "speaking" or self.speech_energy > 0.2:
            return QColor(MAGENTA)
        if self.state == "processing":
            return QColor(PURPLE)
        if self.state == "listening":
            return QColor(MAGENTA)
        if self.state == "armed":
            return QColor(PURPLE)
        return QColor(134, 69, 175)

    def _rotate_point(self, x, y, z, yaw, pitch, roll):
        cosy = math.cos(yaw)
        siny = math.sin(yaw)
        x, z = x * cosy + z * siny, -x * siny + z * cosy

        cosp = math.cos(pitch)
        sinp = math.sin(pitch)
        y, z = y * cosp - z * sinp, y * sinp + z * cosp

        cosr = math.cos(roll)
        sinr = math.sin(roll)
        x, y = x * cosr - y * sinr, x * sinr + y * cosr
        return x, y, z

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor("#000000"))

        cx = rect.width() / 2
        cy = rect.height() / 2
        radius = min(rect.width(), rect.height()) * 0.385
        color = self._state_color()

        for sx, sy, size, alpha, star_phase in self.stars:
            star = QColor(202, 172, 225)
            twinkle = 0.65 + 0.35 * math.sin(self.phase * 0.9 + star_phase)
            star.setAlpha(int(alpha * 120 * twinkle))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(star)
            painter.drawEllipse(QPointF(sx * rect.width(), sy * rect.height()), size, size)

        points = []
        yaw = self.phase * 0.28
        pitch = 0.18 * math.sin(self.phase * 0.17)
        roll = 0.08 * math.cos(self.phase * 0.11)
        for index, particle in enumerate(self.particles):
            base_x = particle["x"]
            base_y = particle["y"]
            base_z = particle["z"]
            x, y, z = self._rotate_point(base_x, base_y, base_z, yaw, pitch, roll)

            radius_scale = particle["shell"]

            perspective = 0.76 + 0.28 * z
            px = cx + x * radius * radius_scale * perspective
            py = cy + y * radius * radius_scale * (0.82 + 0.08 * z)
            edge = min(1.0, math.sqrt(base_x * base_x + base_y * base_y) * 1.06)
            depth = (z + 1.0) * 0.5
            if self.speech_energy > 0.02:
                row_wave = math.sin((base_y * 13.5) + self.wave_phase)
                secondary_wave = 0.42 * math.sin((base_y * 25.0) - (self.wave_phase * 1.35) + particle["phase"])
                local_jitter = 0.18 * math.sin((base_x * 10.0) + particle["phase"] + self.wave_phase * 0.8)
                depth_weight = 0.58 + (0.42 * depth)
                px += self.speech_energy * radius * 0.105 * depth_weight * (row_wave + secondary_wave + local_jitter)
            edge_visibility = edge ** 1.9
            alpha = int((16 + 104 * depth) * (0.16 + 0.84 * edge_visibility) * particle["twinkle"])
            size = particle["size"] * (0.48 + 0.46 * depth)
            points.append((z, px, py, size, max(6, min(150, alpha)), index))

        points.sort(key=lambda item: item[0])
        for z, px, py, size, alpha, index in points:
            if self.state == "muted" and self.speech_energy < 0.08:
                dot = QColor(131, 76, 169)
            elif index % 7 == 0:
                dot = QColor(194, 89, 255)
            else:
                dot = QColor(166, 74, 226)
            dot.setAlpha(max(8, min(210, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(px, py), size, size)

        painter.setFont(QFont("JetBrains Mono", 11, QFont.Weight.Bold))
        state_text = QColor(223, 200, 255)
        state_text.setAlpha(205)
        painter.setPen(QPen(state_text))
        painter.drawText(QRectF(0, cy + radius + 24, rect.width(), 28), Qt.AlignmentFlag.AlignCenter, self.state.upper())


class RadarPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.setMinimumHeight(210)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(45)

    def animate(self):
        self.angle = (self.angle + 2) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w * 0.5, h * 0.53
        r = min(w, h) * 0.38
        painter.setPen(QPen(QColor(77, 234, 255, 70), 1))
        for frac in (0.33, 0.66, 1.0):
            painter.drawEllipse(QPointF(cx, cy), r * frac, r * frac)
        painter.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        painter.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle)
        sweep = QLinearGradient(QPointF(0, 0), QPointF(r, 0))
        sweep.setColorAt(0, QColor(93, 255, 191, 15))
        sweep.setColorAt(1, QColor(93, 255, 191, 145))
        painter.setPen(QPen(QColor(GREEN), 2))
        painter.setBrush(sweep)
        painter.drawPie(QRectF(-r, -r, r * 2, r * 2), -14 * 16, 28 * 16)
        painter.restore()

        blips = ((0.18, -0.28), (-0.36, 0.22), (0.48, 0.14), (-0.08, -0.55))
        for i, (x, y) in enumerate(blips):
            color = QColor(AMBER if i == 1 else GREEN)
            color.setAlpha(190)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx + x * r, cy + y * r), 4, 4)


class CameraStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tick = 0
        self.setMinimumHeight(230)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(80)

    def animate(self):
        self.tick = (self.tick + 1) % 120
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        labels = ("FRONT", "DESK", "NET", "CORE")
        cols, rows = 2, 2
        gap = 10
        tile_w = (self.width() - gap) / cols
        tile_h = (self.height() - gap) / rows
        for row in range(rows):
            for col in range(cols):
                index = row * cols + col
                rect = QRectF(col * (tile_w + gap), row * (tile_h + gap), tile_w, tile_h)
                grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
                grad.setColorAt(0, QColor(10, 41, 55, 245))
                grad.setColorAt(1, QColor(3, 11, 20, 245))
                painter.setPen(QPen(QColor(77, 234, 255, 95), 1))
                painter.setBrush(grad)
                painter.drawRoundedRect(rect, 6, 6)
                painter.setPen(QPen(QColor(93, 255, 191, 55), 1))
                for line in range(5):
                    y = rect.top() + 18 + line * 16 + ((self.tick + index * 9) % 9)
                    painter.drawLine(QPointF(rect.left() + 8, y), QPointF(rect.right() - 8, y - 5))
                painter.setPen(QPen(QColor(TEXT_DIM), 1))
                painter.drawText(rect.adjusted(9, 8, -8, -8), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, labels[index])
                live = QColor(GREEN if index != 2 else AMBER)
                live.setAlpha(230)
                painter.setBrush(live)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(rect.right() - 18, rect.top() + 16), 4, 4)


class PulseBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = [34, 66, 48, 82, 58, 43]
        self.setMinimumHeight(150)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(220)

    def animate(self):
        self.values = [max(12, min(96, value + random.randint(-9, 9))) for value in self.values]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        names = ("CPU", "RAM", "IO", "NET", "LLM", "VAD")
        row_h = self.height() / len(names)
        for i, name in enumerate(names):
            y = i * row_h + 6
            painter.setPen(QPen(QColor(TEXT_DIM), 1))
            painter.drawText(QRectF(0, y, 46, row_h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            track = QRectF(52, y + row_h / 2 - 4, max(30, self.width() - 58), 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(29, 54, 68, 190))
            painter.drawRoundedRect(track, 4, 4)
            fill = QRectF(track.left(), track.top(), track.width() * self.values[i] / 100, track.height())
            painter.setBrush(QColor(GREEN if i % 2 else CYAN))
            painter.drawRoundedRect(fill, 4, 4)


class ProcessPanel(QWidget):
    def __init__(self, parent=None, app_core=None):
        super().__init__(parent)
        self.app_core = app_core
        self.setMinimumSize(420, 480)
        self.setStyleSheet(panel_style("rgba(93, 255, 191, 155)"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("PROCESS GRID")
        title.setStyleSheet(label_style(GREEN, 14, "bold"))
        layout.addWidget(title)

        self.stats_area = QLabel("Loading system telemetry...")
        self.stats_area.setStyleSheet(label_style(TEXT_DIM, 12))
        self.stats_area.setWordWrap(True)
        layout.addWidget(self.stats_area)

        self.plugin_area = QTextEdit()
        self.plugin_area.setReadOnly(True)
        self.plugin_area.setStyleSheet(
            "background-color: rgba(0, 0, 0, 105);"
            f"color: {TEXT};"
            "font-family: 'JetBrains Mono', 'Courier New', monospace;"
            "font-size: 12px;"
            "border: 1px solid rgba(77, 234, 255, 90);"
            "border-radius: 6px;"
            "padding: 8px;"
        )
        layout.addWidget(self.plugin_area, stretch=1)

        close_btn = QPushButton("CLOSE")
        close_btn.setStyleSheet(button_style())
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_info)
        self.update_timer.start(2000)
        self.update_info()

    def update_info(self):
        if not self.app_core:
            return
        try:
            from modules.system_control.sys_info import get_system_status

            status = get_system_status()
        except Exception as exc:
            status = f"Telemetry unavailable: {exc}"
        self.stats_area.setText(status.replace("\n", " | "))

        plugins = []
        plugin_manager = getattr(self.app_core, "plugin_manager", None)
        for plugin in getattr(plugin_manager, "plugins", []) or []:
            plugins.append(f"{plugin.name}  ACTIVE")
        self.plugin_area.setPlainText("LOADED MODULES\n" + "\n".join(plugins))


class DeviceDiscoveryThread(QThread):
    devices_found = pyqtSignal(list)

    def run(self):
        try:
            self.devices_found.emit(list_audio_input_devices())
        except Exception:
            self.devices_found.emit([])


class MicSelector(QFrame):
    device_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(panel_style("rgba(77, 234, 255, 90)"))
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        label = QLabel("INPUT DEVICE")
        label.setStyleSheet(label_style(CYAN, 11, "bold"))
        layout.addWidget(label)

        self.combo = QComboBox()
        self.combo.setStyleSheet(combo_style())
        layout.addWidget(self.combo)

        self.discovery_thread = None
        self.combo.currentIndexChanged.connect(self.on_selection_changed)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(10000)
        QTimer.singleShot(250, self.refresh_devices)

    def refresh_devices(self):
        if self.discovery_thread and self.discovery_thread.isRunning():
            return
        if self.combo.count() == 0:
            self.combo.addItem("Scanning...", None)
        self.discovery_thread = DeviceDiscoveryThread()
        self.discovery_thread.devices_found.connect(self._on_devices_found)
        self.discovery_thread.start()

    def _on_devices_found(self, devices):
        current_id = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        if not devices:
            self.combo.addItem("No microphone found", None)
        else:
            for device in devices:
                prefix = "Default - " if device.is_default else ""
                suffix = f" ({device.backend})"
                self.combo.addItem(f"{prefix}{device.label}{suffix}", device.target)
        if current_id is not None:
            for index in range(self.combo.count()):
                if self.combo.itemData(index) == current_id:
                    self.combo.setCurrentIndex(index)
                    break
        self.combo.blockSignals(False)

    def on_selection_changed(self, index):
        if index < 0:
            return
        text = self.combo.itemText(index)
        if text in {"Scanning...", "No microphone found"}:
            return
        self.device_selected.emit(self.combo.itemData(index))


def button_style(danger=False):
    if danger:
        return (
            "background-color: rgba(92, 18, 28, 235);"
            f"color: {TEXT};"
            f"border: 1px solid {RED};"
            "border-radius: 6px;"
            "padding: 10px;"
            "font-family: 'JetBrains Mono', 'Courier New', monospace;"
            "font-weight: bold;"
        )
    return (
        "background-color: rgba(8, 38, 52, 235);"
        f"color: {TEXT};"
        f"border: 1px solid {CYAN};"
        "border-radius: 6px;"
        "padding: 10px;"
        "font-family: 'JetBrains Mono', 'Courier New', monospace;"
        "font-weight: bold;"
    )


def combo_style():
    return (
        "QComboBox {"
        "background-color: rgba(2, 10, 18, 230);"
        f"color: {TEXT};"
        "border: 1px solid rgba(77, 234, 255, 115);"
        "border-radius: 5px;"
        "padding: 7px;"
        "font-family: 'JetBrains Mono', 'Courier New', monospace;"
        "font-size: 12px;"
        "}"
        "QComboBox QAbstractItemView {"
        "background-color: #06121f;"
        f"color: {TEXT};"
        f"selection-background-color: {BLUE};"
        "}"
    )


class JarvisHUD(QMainWindow):
    message_ready = pyqtSignal(object)
    shutdown_signal = pyqtSignal()
    mic_toggle_ready = pyqtSignal(object)
    voice_response_ready = pyqtSignal(object)
    turn_started_ready = pyqtSignal(object)
    turn_processing_ready = pyqtSignal(object)
    turn_finished_ready = pyqtSignal(object)
    listening_mode_ready = pyqtSignal(object)
    voice_runtime_ready = pyqtSignal(object)

    def __init__(self, app_core):
        super().__init__()
        self.app_core = app_core
        self.turn_state = "idle"
        self.voice_runtime_state = {}
        self.drag_pos = None
        self._speaking_until = 0.0

        self.setWindowTitle("FRIDAY")
        self.resize(1500, 920)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG}; color: {TEXT};")
        self.setCentralWidget(central)
        root = QGridLayout(central)
        root.setContentsMargins(18, 16, 18, 18)
        root.setHorizontalSpacing(14)
        root.setVerticalSpacing(14)

        header = self._build_header()
        root.addWidget(header, 0, 0, 1, 3)

        left = QVBoxLayout()
        left.setSpacing(14)
        radar_panel = TechPanel("SENSOR FIELD")
        self.radar = RadarPanel()
        radar_panel.body.addWidget(self.radar)
        left.addWidget(radar_panel, stretch=3)

        camera_panel = TechPanel("VISUAL FEEDS")
        self.camera_strip = CameraStrip()
        camera_panel.body.addWidget(self.camera_strip)
        left.addWidget(camera_panel, stretch=3)

        stream_panel = TechPanel("EVENT STREAM")
        self.event_stream = QTextEdit()
        self.event_stream.setReadOnly(True)
        self.event_stream.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.event_stream.setStyleSheet(text_box_style(font_size=12))
        self.event_stream.setPlainText("FRIDAY boot layer ready.\nVoice bus linked.\nTool registry standing by.")
        stream_panel.body.addWidget(self.event_stream)
        left.addWidget(stream_panel, stretch=2)
        root.addLayout(left, 1, 0)

        center = QVBoxLayout()
        center.setSpacing(14)
        reactor_panel = TechPanel("PARTICLE REACTOR")
        reactor_panel.setStyleSheet(
            "background-color: #000000;"
            "border: 1px solid rgba(185, 92, 255, 125);"
            "border-radius: 8px;"
        )
        reactor_panel.layout.setContentsMargins(10, 10, 10, 12)
        reactor_panel.indicator.setText("CORE")
        self.reactor = ParticleGlobeReactor()
        self.reactor.setMinimumSize(640, 560)
        reactor_panel.body.addWidget(self.reactor, stretch=1)
        center.addWidget(reactor_panel, stretch=7)

        transcript_panel = TechPanel("DIALOG")
        transcript_panel.indicator.setText("LIVE")
        self.subtitle_label = QTextEdit()
        self.subtitle_label.setReadOnly(True)
        self.subtitle_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.subtitle_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.subtitle_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.subtitle_label.setMinimumHeight(150)
        self.subtitle_label.setMaximumHeight(220)
        self.subtitle_label.setStyleSheet(text_box_style(font_size=15))
        transcript_panel.body.addWidget(self.subtitle_label)
        center.addWidget(transcript_panel, stretch=0)
        root.addLayout(center, 1, 1)

        right = QVBoxLayout()
        right.setSpacing(14)
        voice_panel = TechPanel("VOICE")
        self.voice_mode_combo = QComboBox()
        self.voice_mode_combo.setStyleSheet(combo_style())
        for value in ("persistent", "wake_word", "on_demand", "manual"):
            self.voice_mode_combo.addItem(format_voice_mode_label(value), value)
        self.voice_mode_combo.currentIndexChanged.connect(self.on_voice_mode_selected)
        voice_panel.body.addWidget(self.voice_mode_combo)

        self.voice_state_label = QLabel("STATE: MUTED")
        self.mic_gate_label = QLabel("MIC GATE: CLOSED")
        self.wake_strategy_label = QLabel("WAKE ENGINE: Wake model")
        self.current_device_label = QLabel("DEVICE: System default")
        self.rejected_reason_label = QLabel("LAST REJECTED: None")
        for label in (
            self.voice_state_label,
            self.mic_gate_label,
            self.wake_strategy_label,
            self.current_device_label,
            self.rejected_reason_label,
        ):
            label.setStyleSheet(label_style(TEXT_DIM, 11))
            label.setWordWrap(True)
            voice_panel.body.addWidget(label)
        right.addWidget(voice_panel, stretch=2)
        self.refresh_voice_mode_button()

        telemetry_panel = TechPanel("SYSTEM PULSE")
        self.telemetry = PulseBars()
        telemetry_panel.body.addWidget(self.telemetry)
        right.addWidget(telemetry_panel, stretch=2)

        self.mic_selector = MicSelector()
        self.mic_selector.device_selected.connect(self.on_mic_selected)
        right.addWidget(self.mic_selector, stretch=1)

        self.process_btn = QPushButton("PROCESS GRID")
        self.process_btn.setStyleSheet(button_style())
        self.process_btn.clicked.connect(self.toggle_process_panel)
        right.addWidget(self.process_btn)

        self.stop_btn = QPushButton("STOP SPEECH")
        self.stop_btn.setStyleSheet(button_style(danger=True))
        self.stop_btn.clicked.connect(self.stop_speaking)
        right.addWidget(self.stop_btn)
        root.addLayout(right, 1, 2)

        root.setColumnStretch(0, 2)
        root.setColumnStretch(1, 7)
        root.setColumnStretch(2, 2)
        root.setRowStretch(1, 1)

        self.process_panel = ProcessPanel(self, self.app_core)
        self.process_panel.hide()
        self.process_panel.move(380, 120)

        self._connect_runtime()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.check_status)
        self.status_timer.start(180)

        if getattr(self.app_core, "should_auto_start_voice", lambda: True)():
            QTimer.singleShot(1000, lambda: self.app_core.event_bus.publish("gui_toggle_mic", True))

    def _build_header(self):
        header = QFrame()
        header.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("FRIDAY")
        title.setStyleSheet(
            f"color: {TEXT};"
            "font-family: 'JetBrains Mono', 'Courier New', monospace;"
            "font-size: 34px;"
            "font-weight: bold;"
            "letter-spacing: 0px;"
            "border: none;"
        )
        layout.addWidget(title)

        subtitle = QLabel("LOCAL INTELLIGENCE SURFACE")
        subtitle.setStyleSheet(label_style(TEXT_DIM, 12, "bold"))
        layout.addWidget(subtitle)
        layout.addStretch(1)

        self.status_label = QLabel("route: idle | lane: idle | voice: idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet(label_style(TEXT_DIM, 11))
        layout.addWidget(self.status_label)
        return header

    def _connect_runtime(self):
        self.app_core.set_gui_callback(self._on_message_from_thread)
        self.message_ready.connect(self.render_message)
        self.shutdown_signal.connect(self.close)
        self.mic_toggle_ready.connect(self._on_mic_toggle)
        self.voice_response_ready.connect(self._on_voice_response)
        self.turn_started_ready.connect(self._on_turn_started)
        self.turn_processing_ready.connect(self._on_turn_processing)
        self.turn_finished_ready.connect(self._on_turn_finished)
        self.listening_mode_ready.connect(self._on_listening_mode_changed)
        self.voice_runtime_ready.connect(self._on_voice_runtime_state_changed)

        self.reactor.clicked.connect(self.toggle_pause_everything)
        bus = self.app_core.event_bus
        bus.subscribe("gui_toggle_mic", lambda payload: self.mic_toggle_ready.emit(payload))
        bus.subscribe("voice_response", lambda payload: self.voice_response_ready.emit(payload))
        bus.subscribe("turn_started", lambda payload: self.turn_started_ready.emit(payload))
        bus.subscribe("assistant_ack", lambda payload: self.turn_processing_ready.emit(payload))
        bus.subscribe("assistant_progress", lambda payload: self.turn_processing_ready.emit(payload))
        bus.subscribe("tool_started", lambda payload: self.turn_processing_ready.emit(payload))
        bus.subscribe("llm_started", lambda payload: self.turn_processing_ready.emit(payload))
        bus.subscribe("turn_completed", lambda payload: self.turn_finished_ready.emit(payload))
        bus.subscribe("turn_failed", lambda payload: self.turn_finished_ready.emit(payload))
        bus.subscribe("listening_mode_changed", lambda payload: self.listening_mode_ready.emit(payload))
        bus.subscribe("voice_runtime_state_changed", lambda payload: self.voice_runtime_ready.emit(payload))
        bus.subscribe("system_shutdown", lambda _payload: self.shutdown_signal.emit())

    def toggle_process_panel(self, _checked=False):
        if self.process_panel.isVisible():
            self.process_panel.hide()
            return
        self.process_panel.show()
        self.process_panel.raise_()

    def on_voice_mode_selected(self, index):
        try:
            mode = self.voice_mode_combo.itemData(index)
            if mode and hasattr(self.app_core, "set_listening_mode"):
                self.app_core.set_listening_mode(mode)
        except Exception as exc:
            self._report_option_error("VOICE MODE", exc)
            self.refresh_voice_mode_button()

    def refresh_voice_mode_button(self):
        self.voice_mode_combo.blockSignals(True)
        try:
            mode = getattr(self.app_core, "get_listening_mode", lambda: "persistent")()
            for index in range(self.voice_mode_combo.count()):
                if self.voice_mode_combo.itemData(index) == mode:
                    self.voice_mode_combo.setCurrentIndex(index)
                    break
        finally:
            self.voice_mode_combo.blockSignals(False)

    def _on_listening_mode_changed(self, _payload):
        self.refresh_voice_mode_button()

    def _on_voice_runtime_state_changed(self, payload):
        try:
            self.voice_runtime_state = dict(payload or {})
            formatted = format_voice_runtime_status(self.voice_runtime_state)
            self.voice_state_label.setText(f"STATE: {formatted['state']}")
            self.mic_gate_label.setText(f"MIC GATE: {formatted['gate']}")
            self.wake_strategy_label.setText(f"WAKE ENGINE: {formatted['wake_strategy']}")
            self.current_device_label.setText(f"DEVICE: {formatted['device']}")
            self.rejected_reason_label.setText(f"LAST REJECTED: {formatted['rejected']}")
            if time.monotonic() >= self._speaking_until:
                self.reactor.set_state(str(self.voice_runtime_state.get("ui_state") or "muted"))
        except Exception as exc:
            self._report_option_error("VOICE STATUS", exc)

    def _on_voice_response(self, text):
        self._speaking_until = time.monotonic() + 2.8
        self.reactor.pulse_speaking()
        if text:
            self._append_event("SPEECH", str(text)[:90])

    def toggle_pause_everything(self):
        stt = getattr(self.app_core, "stt", None)
        is_active = bool(
            getattr(stt, "is_listening", False)
            or getattr(stt, "wake_armed", False)
        )
        if is_active:
            self.app_core.event_bus.publish("gui_toggle_mic", False)
            self.stop_speaking()
            self.reactor.set_state("muted")
            phrase = "Voice gate closed."
        else:
            phrase = "Voice gate opening."
            self.app_core.event_bus.publish("voice_response", phrase)
            QTimer.singleShot(1200, lambda: self.app_core.event_bus.publish("voice_activation_requested", {"source": "button"}))
        self._set_transcript_text("assistant", phrase)
        QTimer.singleShot(2500, lambda: self.subtitle_label.clear())

    def check_status(self):
        try:
            if getattr(self.app_core, "is_speaking", False) or time.monotonic() < self._speaking_until:
                self.reactor.set_state("speaking")
            else:
                runtime_state = self.voice_runtime_state or {}
                runtime_ui_state = runtime_state.get("ui_state")
                if runtime_ui_state in {"muted", "armed", "listening", "processing", "speaking"}:
                    self.reactor.set_state(runtime_ui_state)
                elif self.turn_state in {"thinking", "executing", "processing"}:
                    self.reactor.set_state("processing")
                elif getattr(getattr(self.app_core, "stt", None), "is_listening", False):
                    self.reactor.set_state("listening")
                else:
                    self.reactor.set_state("muted")

            router = getattr(self.app_core, "router", None)
            capabilities = getattr(self.app_core, "capabilities", None)
            route_source = getattr(router, "current_route_source", "idle") if router else "idle"
            lane = getattr(router, "current_model_lane", "idle") if router else "idle"
            disabled_count = len(capabilities.disabled_skills()) if capabilities else 0
            mode = getattr(self.app_core, "get_listening_mode", lambda: "persistent")()
            self.status_label.setText(f"route: {route_source} | lane: {lane} | voice: {mode} | disabled: {disabled_count}")
        except Exception as exc:
            logger.exception("HUD status refresh failed: %s", exc)

    def _on_mic_toggle(self, active):
        stt = getattr(self.app_core, "stt", None)
        if active and getattr(stt, "wake_armed", False):
            self.reactor.set_state("armed")
        elif active:
            self.reactor.set_state("listening")
        else:
            self.reactor.set_state("muted")

    def _on_turn_started(self, payload):
        self.turn_state = "processing"
        self.reactor.set_state("processing")
        self._append_event("TURN", str((payload or {}).get("text", ""))[:90] if isinstance(payload, dict) else "")

    def _on_turn_processing(self, payload):
        self.turn_state = "processing"
        self.reactor.set_state("processing")
        if isinstance(payload, dict):
            self._append_event("RUN", str(payload.get("tool") or payload.get("text") or "")[:90])

    def _on_turn_finished(self, _payload):
        self.turn_state = "idle"

    def stop_speaking(self, _checked=False):
        if getattr(self.app_core, "tts", None):
            self.app_core.tts.stop()
        self._speaking_until = 0.0

    def on_mic_selected(self, device_id):
        stt = getattr(self.app_core, "stt", None)
        if not stt or not hasattr(stt, "set_device"):
            return
        try:
            stt.set_device(device_id)
        except Exception as exc:
            self._report_option_error("MIC", exc)
            return
        label = getattr(stt, "device_label", "selected device")
        self._set_transcript_text("assistant", f"Microphone switched to {label}")
        self._append_event("MIC", label)
        QTimer.singleShot(2000, lambda: self.subtitle_label.clear())

    def _report_option_error(self, label, exc):
        message = str(exc) or exc.__class__.__name__
        logger.exception("HUD %s option failed: %s", label, exc)
        self._append_event(label, f"FAILED: {message}"[:90])
        self._set_transcript_text("assistant", f"{label.title()} option failed: {message}")
        QTimer.singleShot(3500, lambda: self.subtitle_label.clear())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def closeEvent(self, event):
        self.app_core.shutdown()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def _on_message_from_thread(self, payload):
        self.message_ready.emit(payload)

    def render_message(self, payload):
        if not isinstance(payload, dict):
            self._set_transcript_text("assistant", str(payload))
            return
        text = payload.get("text", "")
        role = payload.get("role", "assistant")
        self._set_transcript_text(role, text)
        self._append_event(role.upper(), text[:90])

    def _set_transcript_text(self, role, text):
        self.subtitle_label.setPlainText(format_hud_message(role, text))
        self.subtitle_label.verticalScrollBar().setValue(0)

    def _append_event(self, label, text):
        if not hasattr(self, "event_stream"):
            return
        line = f"{time.strftime('%H:%M:%S')}  {label:<7} {text}".rstrip()
        existing = self.event_stream.toPlainText().splitlines()
        next_lines = (existing + [line])[-9:]
        self.event_stream.setPlainText("\n".join(next_lines))
        self.event_stream.verticalScrollBar().setValue(self.event_stream.verticalScrollBar().maximum())


def text_box_style(font_size=13):
    return (
        "background-color: rgba(0, 0, 0, 88);"
        f"color: {TEXT};"
        "font-family: 'JetBrains Mono', 'Courier New', monospace;"
        f"font-size: {font_size}px;"
        "border: 1px solid rgba(77, 234, 255, 70);"
        "border-radius: 6px;"
        "padding: 8px;"
    )


def start_hud(app_core):
    app = QApplication(sys.argv)
    window = JarvisHUD(app_core)
    window.showFullScreen()
    sys.exit(app.exec())
