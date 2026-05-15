import json
import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from html import escape as html_escape

from PyQt6.QtCore import QDateTime, QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.voice_io.audio_devices import list_audio_input_devices


logger = logging.getLogger(__name__)

HUD_TEXT_MAX_CHARS = 420
HUD_TEXT_MAX_LINES = 8
_EVENT_STREAM_MAX_LINES = 60
NELLORE_LAT = 14.4426
NELLORE_LON = 79.9865
NELLORE_TZ = "Asia/Kolkata"
NELLORE_LABEL = "Nellore, AP, India"

_THEME_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "gui_state.json"
)


# ---------------------------------------------------------------------------
# Pure formatter helpers (used by tests/test_hud.py — keep stable)
# ---------------------------------------------------------------------------


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


def format_weather_status(weather):
    weather = dict(weather or {})
    status = str(weather.get("status") or "").lower()
    if status != "success":
        return {
            "temperature": "--.- C",
            "condition": "Weather unavailable",
            "details": str(weather.get("message") or "Waiting for update"),
        }
    temperature = weather.get("temperature_c")
    feels_like = weather.get("feels_like_c")
    humidity = weather.get("humidity")
    wind = weather.get("wind_kmh")
    condition = str(weather.get("condition") or "Current conditions")

    def _metric(value, suffix, precision=0):
        try:
            numeric = float(value)
        except Exception:
            return f"--{suffix}"
        return f"{numeric:.{precision}f}{suffix}"

    details = (
        f"Feels {_metric(feels_like, ' C', 1)}  |  "
        f"Humidity {_metric(humidity, '%')}  |  "
        f"Wind {_metric(wind, ' km/h')}"
    )
    return {
        "temperature": _metric(temperature, " C", 1),
        "condition": condition,
        "details": details,
    }


def format_calendar_event_item(event):
    event = dict(event or {})
    title = str(event.get("title") or "").strip() or "Untitled reminder"
    try:
        remind_at = datetime.fromisoformat(str(event.get("remind_at") or ""))
        when = remind_at.strftime("%d %b %I:%M %p").lstrip("0")
    except Exception:
        when = "No time"
    return f"{when}  {title}"


# ---------------------------------------------------------------------------
# Theme system
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    surface: str
    surface_alt: str
    panel: str
    panel_border: str
    text: str
    text_dim: str
    text_muted: str
    accent: str
    accent_soft: str
    user_bubble: str
    user_bubble_text: str
    assistant_bubble: str
    assistant_bubble_text: str
    system_bubble: str
    success: str
    warning: str
    danger: str
    info: str
    purple: str
    magenta: str
    badge_bg: str
    scroll_track: str
    scroll_handle: str


def _theme_dark() -> Theme:
    return Theme(
        name="dark",
        bg="#0b0d12",
        surface="#13161e",
        surface_alt="#1a1e2a",
        panel="rgba(22, 25, 33, 235)",
        panel_border="rgba(120, 140, 200, 45)",
        text="#eef1f7",
        text_dim="#9aa3b8",
        text_muted="#6b7384",
        accent="#7aa2ff",
        accent_soft="rgba(122, 162, 255, 55)",
        user_bubble="rgba(122, 162, 255, 60)",
        user_bubble_text="#dbe5ff",
        assistant_bubble="rgba(72, 220, 176, 30)",
        assistant_bubble_text="#cdf6e6",
        system_bubble="rgba(255, 255, 255, 12)",
        success="#48dcb0",
        warning="#ffc857",
        danger="#ff6b6b",
        info="#7aa2ff",
        purple="#bf86ff",
        magenta="#ff7ab6",
        badge_bg="rgba(255, 255, 255, 20)",
        scroll_track="rgba(255, 255, 255, 8)",
        scroll_handle="rgba(255, 255, 255, 55)",
    )


def _theme_light() -> Theme:
    return Theme(
        name="light",
        bg="#f4f6fb",
        surface="#ffffff",
        surface_alt="#eef1f8",
        panel="rgba(255, 255, 255, 240)",
        panel_border="rgba(20, 35, 70, 45)",
        text="#161a23",
        text_dim="#576074",
        text_muted="#8b94a8",
        accent="#3461d8",
        accent_soft="rgba(52, 97, 216, 35)",
        user_bubble="rgba(52, 97, 216, 30)",
        user_bubble_text="#1b3a8f",
        assistant_bubble="rgba(30, 165, 120, 22)",
        assistant_bubble_text="#0c5e44",
        system_bubble="rgba(20, 30, 60, 10)",
        success="#1fa278",
        warning="#d18a00",
        danger="#d34a4a",
        info="#3461d8",
        purple="#7c4dd3",
        magenta="#c93b80",
        badge_bg="rgba(20, 35, 70, 18)",
        scroll_track="rgba(20, 30, 60, 10)",
        scroll_handle="rgba(20, 30, 60, 55)",
    )


_THEMES = {"dark": _theme_dark(), "light": _theme_light()}


class ThemeManager:
    """Owns the active theme; widgets subscribe via callbacks."""

    def __init__(self, name: str = "dark"):
        self._name = name if name in _THEMES else "dark"
        self._listeners: list = []

    @property
    def theme(self) -> Theme:
        return _THEMES[self._name]

    @property
    def name(self) -> str:
        return self._name

    def set(self, name: str) -> None:
        if name not in _THEMES or name == self._name:
            return
        self._name = name
        self._notify()

    def toggle(self) -> str:
        self.set("light" if self._name == "dark" else "dark")
        return self._name

    def subscribe(self, fn) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn(self.theme)
            except Exception:
                logger.exception("Theme listener failed")


def _load_theme_pref() -> str:
    try:
        with open(_THEME_STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
            name = str(data.get("theme") or "dark").lower()
            return name if name in _THEMES else "dark"
    except Exception:
        return "dark"


def _save_theme_pref(name: str) -> None:
    try:
        os.makedirs(os.path.dirname(_THEME_STATE_PATH), exist_ok=True)
        try:
            with open(_THEME_STATE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
        except Exception:
            data = {}
        data["theme"] = name
        with open(_THEME_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        logger.exception("Failed to save theme preference")


# ---------------------------------------------------------------------------
# Style helpers (theme-aware)
# ---------------------------------------------------------------------------


FONT_STACK = "'Segoe UI Variable', 'SF Pro Display', 'Inter', 'Helvetica Neue', sans-serif"
MONO_STACK = "'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Menlo', monospace"


def panel_style(theme: Theme, border: str | None = None) -> str:
    return (
        f"background-color: {theme.panel};"
        f"border: 1px solid {border or theme.panel_border};"
        "border-radius: 14px;"
    )


def label_style(theme: Theme, color: str | None = None, size: int = 11, weight: str = "normal") -> str:
    return (
        f"color: {color or theme.text_dim};"
        f"font-family: {FONT_STACK};"
        f"font-size: {size}px;"
        f"font-weight: {weight};"
        "letter-spacing: 0.2px;"
        "border: none;"
        "background: transparent;"
    )


def button_style(theme: Theme, *, danger: bool = False, primary: bool = False) -> str:
    if danger:
        bg = theme.danger
        fg = "#ffffff"
        hover = "rgba(0,0,0,0.18)"
    elif primary:
        bg = theme.accent
        fg = "#ffffff"
        hover = "rgba(0,0,0,0.15)"
    else:
        bg = theme.surface_alt
        fg = theme.text
        hover = theme.accent_soft
    return (
        "QPushButton {"
        f"background-color: {bg};"
        f"color: {fg};"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 10px;"
        "padding: 9px 16px;"
        f"font-family: {FONT_STACK};"
        "font-weight: 600;"
        "font-size: 12px;"
        "letter-spacing: 0.4px;"
        "}"
        "QPushButton:hover {"
        f"background-color: {hover};"
        "}"
        "QPushButton:pressed { padding-top: 10px; padding-bottom: 8px; }"
    )


def text_box_style(theme: Theme, font_size: int = 13) -> str:
    return (
        f"background-color: {theme.surface_alt};"
        f"color: {theme.text};"
        f"font-family: {FONT_STACK};"
        f"font-size: {font_size}px;"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 10px;"
        "padding: 10px 12px;"
        f"selection-background-color: {theme.accent};"
        "selection-color: white;"
    )


def combo_style(theme: Theme) -> str:
    return (
        "QComboBox {"
        f"background-color: {theme.surface_alt};"
        f"color: {theme.text};"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 10px;"
        "padding: 8px 12px;"
        f"font-family: {FONT_STACK};"
        "font-size: 12px;"
        "}"
        "QComboBox::drop-down { border: none; width: 20px; }"
        "QComboBox QAbstractItemView {"
        f"background-color: {theme.surface};"
        f"color: {theme.text};"
        f"selection-background-color: {theme.accent};"
        "selection-color: white;"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 8px;"
        "padding: 4px;"
        "}"
    )


def scrollbar_style(theme: Theme) -> str:
    return (
        "QScrollBar:vertical, QScrollBar:horizontal {"
        f"background: {theme.scroll_track};"
        "border: none; margin: 2px; border-radius: 4px;"
        "}"
        "QScrollBar:vertical { width: 9px; }"
        "QScrollBar:horizontal { height: 9px; }"
        "QScrollBar::handle {"
        f"background: {theme.scroll_handle};"
        "border-radius: 4px; min-height: 24px; min-width: 24px;"
        "}"
        "QScrollBar::handle:hover {"
        f"background: {theme.accent};"
        "}"
        "QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }"
        "QScrollBar::add-page, QScrollBar::sub-page { background: none; }"
    )


# ---------------------------------------------------------------------------
# Tech-panel container
# ---------------------------------------------------------------------------


class TechPanel(QFrame):
    def __init__(self, title: str, theme_mgr: ThemeManager, parent=None, indicator: str = "ONLINE"):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._initial_indicator = indicator
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 16)
        self.layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        self.indicator = QLabel(indicator)
        title_row.addWidget(self.indicator)
        self.layout.addLayout(title_row)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(9)
        self.layout.addLayout(self.body, stretch=1)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(panel_style(theme))
        self.title_label.setStyleSheet(label_style(theme, theme.accent, 12, "bold"))
        self.indicator.setStyleSheet(label_style(theme, theme.success, 10, "bold"))


# ---------------------------------------------------------------------------
# Canvas widgets (preserved from the original HUD, lightly theme-aware)
# ---------------------------------------------------------------------------


class ParticleGlobeReactor(QWidget):
    clicked = pyqtSignal()

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
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
        self.setMinimumSize(250, 200)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(24)
        theme_mgr.subscribe(lambda _t: self.update())

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
        theme = self._theme_mgr.theme
        if self.state == "speaking" or self.speech_energy > 0.2:
            return QColor(theme.magenta)
        if self.state == "processing":
            return QColor(theme.purple)
        if self.state == "listening":
            return QColor(theme.magenta)
        if self.state == "armed":
            return QColor(theme.purple)
        return QColor(theme.accent)

    def _rotate_point(self, x, y, z, yaw, pitch, roll):
        cosy = math.cos(yaw); siny = math.sin(yaw)
        x, z = x * cosy + z * siny, -x * siny + z * cosy
        cosp = math.cos(pitch); sinp = math.sin(pitch)
        y, z = y * cosp - z * sinp, y * sinp + z * cosp
        cosr = math.cos(roll); sinr = math.sin(roll)
        x, y = x * cosr - y * sinr, x * sinr + y * cosr
        return x, y, z

    def paintEvent(self, event):
        theme = self._theme_mgr.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        bg = QColor(theme.bg)
        painter.fillRect(rect, bg)

        cx = rect.width() / 2
        cy = rect.height() / 2
        radius = min(rect.width(), rect.height()) * 0.385
        accent = self._state_color()

        star_color_base = QColor(theme.text)
        for sx, sy, size, alpha, star_phase in self.stars:
            star = QColor(star_color_base)
            twinkle = 0.65 + 0.35 * math.sin(self.phase * 0.9 + star_phase)
            star.setAlpha(int(alpha * 80 * twinkle))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(star)
            painter.drawEllipse(QPointF(sx * rect.width(), sy * rect.height()), size, size)

        points = []
        yaw = self.phase * 0.28
        pitch = 0.18 * math.sin(self.phase * 0.17)
        roll = 0.08 * math.cos(self.phase * 0.11)
        for index, particle in enumerate(self.particles):
            base_x = particle["x"]; base_y = particle["y"]; base_z = particle["z"]
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
            dot = QColor(accent)
            if index % 7 == 0:
                dot = QColor(theme.purple)
            dot.setAlpha(max(8, min(210, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(px, py), size, size)

        painter.setFont(QFont("JetBrains Mono", 11, QFont.Weight.Bold))
        state_text = QColor(theme.text)
        state_text.setAlpha(180)
        painter.setPen(QPen(state_text))
        painter.drawText(QRectF(0, cy + radius + 24, rect.width(), 28), Qt.AlignmentFlag.AlignCenter, self.state.upper())


# ---------------------------------------------------------------------------
# Clock + Weather
# ---------------------------------------------------------------------------


WEATHER_CODE_LABELS = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Heavy showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
}


class WeatherFetchThread(QThread):
    weather_ready = pyqtSignal(dict)

    def run(self):
        try:
            import requests
            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": NELLORE_LAT,
                    "longitude": NELLORE_LON,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "timezone": NELLORE_TZ,
                },
                timeout=8,
            )
            response.raise_for_status()
            current = (response.json() or {}).get("current") or {}
            code = int(current.get("weather_code") or 0)
            self.weather_ready.emit({
                "status": "success",
                "temperature_c": current.get("temperature_2m"),
                "feels_like_c": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_kmh": current.get("wind_speed_10m"),
                "condition": WEATHER_CODE_LABELS.get(code, "Current conditions"),
            })
        except Exception as exc:
            self.weather_ready.emit({"status": "error", "message": str(exc) or exc.__class__.__name__})


class ClockWeatherWidget(QWidget):
    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self.weather_thread = None
        self.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.clock_label = QLabel("--:--:--")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.clock_label)

        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.date_label)

        self.location_label = QLabel(NELLORE_LABEL.upper())
        self.location_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.location_label)

        self.temperature_label = QLabel("--.- C")
        self.temperature_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.temperature_label)

        self.condition_label = QLabel("Weather loading")
        self.condition_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.condition_label.setWordWrap(True)
        layout.addWidget(self.condition_label)

        self.weather_detail_label = QLabel("Waiting for update")
        self.weather_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weather_detail_label.setWordWrap(True)
        layout.addWidget(self.weather_detail_label)
        layout.addStretch(1)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()

        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self.refresh_weather)
        self.weather_timer.start(15 * 60 * 1000)
        QTimer.singleShot(200, self.refresh_weather)

    def _apply_theme(self, theme: Theme) -> None:
        self.clock_label.setStyleSheet(label_style(theme, theme.text, 34, "bold"))
        self.date_label.setStyleSheet(label_style(theme, theme.text_dim, 12, "bold"))
        self.location_label.setStyleSheet(label_style(theme, theme.accent, 11, "bold"))
        self.temperature_label.setStyleSheet(label_style(theme, theme.success, 22, "bold"))
        self.condition_label.setStyleSheet(label_style(theme, theme.text, 12, "bold"))
        self.weather_detail_label.setStyleSheet(label_style(theme, theme.text_dim, 11))

    def update_clock(self):
        now = QDateTime.currentDateTime()
        self.clock_label.setText(now.toString("hh:mm:ss"))
        self.date_label.setText(now.toString("dddd, dd MMM yyyy") + "  IST")

    def refresh_weather(self):
        if self.weather_thread and self.weather_thread.isRunning():
            return
        self.weather_thread = WeatherFetchThread()
        self.weather_thread.weather_ready.connect(self.set_weather)
        self.weather_thread.start()

    def set_weather(self, weather):
        formatted = format_weather_status(weather)
        self.temperature_label.setText(formatted["temperature"])
        self.condition_label.setText(formatted["condition"])
        self.weather_detail_label.setText(formatted["details"])


# ---------------------------------------------------------------------------
# System status + Pulse bars
# ---------------------------------------------------------------------------


class SystemStatusWidget(QWidget):
    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        import platform
        info = [
            ("OS PLATFORM", f"{platform.system()} {platform.release()}"),
            ("ARCHITECTURE", platform.machine()),
            ("PYTHON ENV", sys.version.split()[0]),
            ("HUD ENGINE", "PyQt6"),
            ("UI SCALING", "Adaptive"),
        ]
        self._rows = []
        for label_text, val in info:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            v = QLabel(val)
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(v)
            layout.addLayout(row)
            self._rows.append((lbl, v))
        layout.addStretch(1)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

    def _apply_theme(self, theme: Theme) -> None:
        for lbl, v in self._rows:
            lbl.setStyleSheet(label_style(theme, theme.text_dim, 11, "bold"))
            v.setStyleSheet(label_style(theme, theme.text, 11))


class PulseBars(QWidget):
    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self.values = [34, 66, 48, 82, 58, 43]
        self.setMinimumHeight(96)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(220)
        theme_mgr.subscribe(lambda _t: self.update())

    def animate(self):
        self.values = [max(12, min(96, value + random.randint(-9, 9))) for value in self.values]
        self.update()

    def paintEvent(self, event):
        theme = self._theme_mgr.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        names = ("CPU", "RAM", "IO", "NET", "LLM", "VAD")
        row_h = self.height() / len(names)
        for i, name in enumerate(names):
            y = i * row_h + 2
            painter.setPen(QPen(QColor(theme.text_dim), 1))
            painter.setFont(QFont(MONO_STACK.split(",")[0].strip("'"), 9, QFont.Weight.Bold))
            painter.drawText(QRectF(0, y, 46, row_h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            track = QRectF(52, y + row_h / 2 - 4, max(30, self.width() - 58), 7)
            painter.setPen(Qt.PenStyle.NoPen)
            track_color = QColor(theme.surface_alt)
            painter.setBrush(track_color)
            painter.drawRoundedRect(track, 4, 4)
            fill = QRectF(track.left(), track.top(), track.width() * self.values[i] / 100, track.height())
            painter.setBrush(QColor(theme.success if i % 2 else theme.accent))
            painter.drawRoundedRect(fill, 4, 4)


# ---------------------------------------------------------------------------
# Process panel (overlay)
# ---------------------------------------------------------------------------


class ProcessPanel(QWidget):
    def __init__(self, theme_mgr: ThemeManager, parent=None, app_core=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self.app_core = app_core
        self.setMinimumSize(420, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        self.title = QLabel("PROCESS GRID")
        layout.addWidget(self.title)

        self.stats_area = QLabel("Loading system telemetry...")
        self.stats_area.setWordWrap(True)
        layout.addWidget(self.stats_area)

        self.plugin_area = QTextEdit()
        self.plugin_area.setReadOnly(True)
        layout.addWidget(self.plugin_area, stretch=1)

        self.close_btn = QPushButton("CLOSE")
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.close_btn)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_info)
        self.update_timer.start(2000)
        self.update_info()

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(panel_style(theme, theme.success))
        self.title.setStyleSheet(label_style(theme, theme.success, 14, "bold"))
        self.stats_area.setStyleSheet(label_style(theme, theme.text_dim, 12))
        self.plugin_area.setStyleSheet(text_box_style(theme, 13))
        self.close_btn.setStyleSheet(button_style(theme))

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
            plugins.append(f"  •  {plugin.name}")
        self.plugin_area.setPlainText("LOADED MODULES\n" + "\n".join(plugins))


# ---------------------------------------------------------------------------
# Mic selector
# ---------------------------------------------------------------------------


class DeviceDiscoveryThread(QThread):
    devices_found = pyqtSignal(list)

    def run(self):
        try:
            self.devices_found.emit(list_audio_input_devices())
        except Exception:
            self.devices_found.emit([])


class MicSelector(QFrame):
    device_selected = pyqtSignal(object)

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self.setMinimumWidth(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self.label = QLabel("INPUT DEVICE")
        layout.addWidget(self.label)

        self.combo = QComboBox()
        layout.addWidget(self.combo)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

        self.discovery_thread = None
        self.combo.currentIndexChanged.connect(self.on_selection_changed)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(10000)
        QTimer.singleShot(250, self.refresh_devices)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(panel_style(theme))
        self.label.setStyleSheet(label_style(theme, theme.accent, 11, "bold"))
        self.combo.setStyleSheet(combo_style(theme))

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


# ---------------------------------------------------------------------------
# NEW: Chat view — message bubble cards
# ---------------------------------------------------------------------------


@dataclass
class _ChatMessage:
    role: str
    text: str
    model_lane: str | None = None
    model_label: str | None = None
    timestamp: str = field(default_factory=lambda: time.strftime("%H:%M"))


class ChatBubble(QFrame):
    """A single styled message bubble. Adapts to theme via apply_theme()."""

    def __init__(self, message: _ChatMessage, theme: Theme, parent=None):
        super().__init__(parent)
        self.message = message
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        outer.addLayout(self._row)

        self._inner = QFrame()
        self._inner.setMaximumWidth(640)
        inner_layout = QVBoxLayout(self._inner)
        inner_layout.setContentsMargins(14, 10, 14, 12)
        inner_layout.setSpacing(4)

        self.meta_label = QLabel(self._meta_text(message))
        self.text_label = QLabel(message.text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        inner_layout.addWidget(self.meta_label)
        inner_layout.addWidget(self.text_label)

        if message.role == "user":
            self._row.addStretch(1)
            self._row.addWidget(self._inner)
        elif message.role == "assistant":
            self._row.addWidget(self._inner)
            self._row.addStretch(1)
        else:
            self._row.addStretch(1)
            self._row.addWidget(self._inner)
            self._row.addStretch(1)

        self.apply_theme(theme)

    def _meta_text(self, msg: _ChatMessage) -> str:
        role_label = {"user": "YOU", "assistant": "FRIDAY", "system": "SYSTEM"}.get(msg.role, msg.role.upper())
        parts = [role_label, msg.timestamp]
        if msg.role == "assistant" and msg.model_label:
            parts.append(f"· {msg.model_label}")
        return "   ".join(parts)

    def update_model(self, lane: str | None, label: str | None) -> None:
        self.message.model_lane = lane
        self.message.model_label = label
        self.meta_label.setText(self._meta_text(self.message))

    def apply_theme(self, theme: Theme) -> None:
        if self.message.role == "user":
            bg = theme.user_bubble
            fg = theme.user_bubble_text
            border = theme.accent_soft
            meta_color = theme.accent
        elif self.message.role == "assistant":
            bg = theme.assistant_bubble
            fg = theme.assistant_bubble_text
            border = "rgba(72, 220, 176, 60)" if theme.name == "dark" else "rgba(30, 165, 120, 55)"
            meta_color = theme.success
        else:
            bg = theme.system_bubble
            fg = theme.text_dim
            border = theme.panel_border
            meta_color = theme.text_muted

        self._inner.setStyleSheet(
            f"background-color: {bg};"
            f"border: 1px solid {border};"
            "border-radius: 14px;"
        )
        self.meta_label.setStyleSheet(label_style(theme, meta_color, 10, "bold"))
        self.text_label.setStyleSheet(
            f"color: {fg};"
            f"font-family: {FONT_STACK};"
            "font-size: 13px;"
            "background: transparent;"
            "border: none;"
        )


class RouteLine(QLabel):
    """A small inline marker between bubbles (e.g. '▸ tool_name (query)')."""

    def __init__(self, text: str, theme: Theme, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(
            f"color: {theme.text_muted};"
            f"font-family: {MONO_STACK};"
            "font-size: 10px;"
            "padding: 2px 0px;"
            "background: transparent;"
            "border: none;"
        )


class ChatView(QScrollArea):
    """Scrollable chat panel: list of ChatBubble + RouteLine widgets."""

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self.setWidget(self._inner)

        self._bubbles: list = []
        self._last_assistant_bubble: ChatBubble | None = None

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(
            f"QScrollArea {{ background: {theme.surface}; border: 1px solid {theme.panel_border}; border-radius: 12px; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {theme.surface}; }}"
            + scrollbar_style(theme)
        )
        for widget in self._bubbles:
            if hasattr(widget, "apply_theme"):
                widget.apply_theme(theme)

    def add_message(self, role: str, text: str, model_lane: str | None = None, model_label: str | None = None) -> ChatBubble | None:
        if not text or not str(text).strip():
            return None
        msg = _ChatMessage(role=role, text=str(text).strip(), model_lane=model_lane, model_label=model_label)
        bubble = ChatBubble(msg, self._theme_mgr.theme, parent=self._inner)
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        self._bubbles.append(bubble)
        if role == "assistant":
            self._last_assistant_bubble = bubble
        QTimer.singleShot(10, self._scroll_bottom)
        return bubble

    def add_route(self, text: str) -> None:
        line = RouteLine(text, self._theme_mgr.theme, parent=self._inner)
        self._layout.insertWidget(self._layout.count() - 1, line)
        self._bubbles.append(line)
        QTimer.singleShot(10, self._scroll_bottom)

    def mark_assistant_model(self, lane: str | None, label: str | None) -> None:
        if self._last_assistant_bubble is not None:
            self._last_assistant_bubble.update_model(lane, label)

    def _scroll_bottom(self) -> None:
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# NEW: Event stream — color-coded list
# ---------------------------------------------------------------------------


_EVENT_COLORS = {
    "TURN": "accent",
    "RUN": "warning",
    "LLM": "purple",
    "DONE": "success",
    "FAIL": "danger",
    "SPEECH": "magenta",
    "MIC": "info",
    "INFO": "text_dim",
    "USER": "accent",
    "ASSISTANT": "success",
    "SYSTEM": "text_dim",
}


class EventStreamView(QListWidget):
    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setUniformItemSizes(False)
        self.setSpacing(0)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(
            "QListWidget {"
            f"background: {theme.surface};"
            f"border: 1px solid {theme.panel_border};"
            "border-radius: 10px;"
            "padding: 4px;"
            "outline: 0;"
            "}"
            "QListWidget::item {"
            f"color: {theme.text};"
            "padding: 4px 6px;"
            "border: none;"
            "}"
            + scrollbar_style(theme)
        )
        # Reapply per-item html with new colors.
        for i in range(self.count()):
            item = self.item(i)
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                self._format_item(item, payload)

    def append(self, tag: str, text: str) -> None:
        payload = {
            "tag": tag.upper(),
            "text": str(text or ""),
            "ts": time.strftime("%H:%M:%S"),
        }
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, payload)
        self._format_item(item, payload)
        self.addItem(item)
        while self.count() > _EVENT_STREAM_MAX_LINES:
            self.takeItem(0)
        self.scrollToBottom()

    def _format_item(self, item: QListWidgetItem, payload: dict) -> None:
        theme = self._theme_mgr.theme
        tag = payload["tag"]
        color_key = _EVENT_COLORS.get(tag, "text_dim")
        tag_color = getattr(theme, color_key, theme.text_dim)
        ts = html_escape(payload["ts"])
        text = html_escape(payload["text"])
        tag_padded = html_escape(tag.ljust(7)).replace(" ", "&nbsp;")
        item.setText("")
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(
            f"<span style=\"color:{theme.text_muted};font-family:{MONO_STACK};font-size:10px;\">{ts}</span>"
            f"&nbsp;&nbsp;<span style=\"color:{tag_color};font-family:{MONO_STACK};font-size:10px;font-weight:bold;\">{tag_padded}</span>"
            f"&nbsp;&nbsp;<span style=\"color:{theme.text};font-family:{FONT_STACK};font-size:11px;\">{text}</span>"
        )
        label.setStyleSheet("background: transparent; border: none; padding: 0;")
        label.setWordWrap(False)
        label.adjustSize()
        item.setSizeHint(label.sizeHint())
        self.setItemWidget(item, label)


# ---------------------------------------------------------------------------
# NEW: Models panel
# ---------------------------------------------------------------------------


class ModelsPanel(QWidget):
    """Lists available local models + status; highlights the active lane."""

    def __init__(self, theme_mgr: ThemeManager, app_core, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._app_core = app_core
        self._active_lane: str | None = None
        self._rows: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(6)
        layout.addLayout(self._rows_container)
        layout.addStretch(1)

        theme_mgr.subscribe(self._apply_theme)
        self._build_rows()
        self._apply_theme(theme_mgr.theme)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._refresh_timer.start(2000)

    def _build_rows(self) -> None:
        mm = getattr(self._app_core, "router", None)
        manager = getattr(mm, "model_manager", None) if mm else None
        profiles = manager._profiles if manager else {}
        for role, profile in profiles.items():
            card = QFrame()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)

            header = QHBoxLayout()
            lane_label = QLabel(role.upper())
            status_dot = QLabel("●")
            header.addWidget(lane_label)
            header.addStretch(1)
            header.addWidget(status_dot)
            card_layout.addLayout(header)

            name_label = QLabel(os.path.basename(profile.path))
            name_label.setWordWrap(True)
            card_layout.addWidget(name_label)

            detail_label = QLabel(f"ctx {profile.n_ctx}  ·  temp {profile.temperature}")
            card_layout.addWidget(detail_label)

            self._rows_container.addWidget(card)
            self._rows[role] = {
                "card": card,
                "lane_label": lane_label,
                "status_dot": status_dot,
                "name_label": name_label,
                "detail_label": detail_label,
            }
        if not profiles:
            empty = QLabel("No model profiles registered")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._rows_container.addWidget(empty)
            self._rows["__empty"] = {"card": empty}

    def _apply_theme(self, theme: Theme) -> None:
        for role, row in self._rows.items():
            if role == "__empty":
                row["card"].setStyleSheet(label_style(theme, theme.text_dim, 11))
                continue
            highlight = (role == self._active_lane)
            border = theme.accent if highlight else theme.panel_border
            row["card"].setStyleSheet(
                f"background-color: {theme.surface_alt};"
                f"border: 1px solid {border};"
                "border-radius: 10px;"
            )
            row["lane_label"].setStyleSheet(label_style(theme, theme.accent if highlight else theme.text, 11, "bold"))
            row["name_label"].setStyleSheet(
                f"color: {theme.text};"
                f"font-family: {MONO_STACK};"
                "font-size: 11px;"
                "background: transparent; border: none;"
            )
            row["detail_label"].setStyleSheet(label_style(theme, theme.text_muted, 10))
            row["status_dot"].setStyleSheet(label_style(theme, self._dot_color(theme, role), 14, "bold"))

    def _dot_color(self, theme: Theme, role: str) -> str:
        status = self._lane_status(role)
        if status == "loaded":
            return theme.success
        if status == "missing":
            return theme.danger
        if status == "failed":
            return theme.warning
        return theme.text_muted  # exists but not loaded

    def _lane_status(self, role: str) -> str:
        manager = self._manager()
        if not manager:
            return "unknown"
        try:
            status = manager.status(role)
        except Exception:
            return "unknown"
        if status.get("failed"):
            return "failed"
        if not status.get("exists"):
            return "missing"
        if status.get("loaded"):
            return "loaded"
        return "available"

    def _manager(self):
        router = getattr(self._app_core, "router", None)
        return getattr(router, "model_manager", None) if router else None

    def set_active_lane(self, lane: str | None) -> None:
        if lane and lane not in self._rows:
            lane = None
        if lane == self._active_lane:
            return
        self._active_lane = lane
        self._apply_theme(self._theme_mgr.theme)

    def _refresh_status(self) -> None:
        self._apply_theme(self._theme_mgr.theme)


# ---------------------------------------------------------------------------
# Background worker for input
# ---------------------------------------------------------------------------


class _InputWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, app_core, text: str, parent=None):
        super().__init__(parent)
        self._app_core = app_core
        self._text = text

    def run(self):
        try:
            self._app_core.process_input(self._text, source="gui")
        except Exception:
            pass
        finally:
            self.finished.emit()


# ---------------------------------------------------------------------------
# JarvisHUD — main window
# ---------------------------------------------------------------------------


class JarvisHUD(QMainWindow):
    message_ready = pyqtSignal(object)
    shutdown_signal = pyqtSignal()
    mic_toggle_ready = pyqtSignal(object)
    voice_response_ready = pyqtSignal(object)
    turn_started_ready = pyqtSignal(object)
    turn_processing_ready = pyqtSignal(object)
    turn_finished_ready = pyqtSignal(object)
    tool_finished_ready = pyqtSignal(object)
    listening_mode_ready = pyqtSignal(object)
    voice_runtime_ready = pyqtSignal(object)

    def __init__(self, app_core):
        super().__init__()
        self.app_core = app_core
        self.theme_mgr = ThemeManager(_load_theme_pref())
        self.turn_state = "idle"
        self.voice_runtime_state = {}
        self.drag_pos = None
        self._speaking_until = 0.0
        self._input_worker: _InputWorker | None = None
        self._current_layout_mode = None
        self._pending_lane: str | None = None

        self.setWindowTitle("FRIDAY")
        self.resize(1180, 720)

        self.central = QWidget()
        self.setCentralWidget(self.central)

        self.root = QGridLayout(self.central)
        self.root.setContentsMargins(22, 22, 22, 22)
        self.root.setHorizontalSpacing(16)
        self.root.setVerticalSpacing(16)

        self.header_widget = self._build_header()
        self.root.addWidget(self.header_widget, 0, 0, 1, 3)

        # ----- LEFT column -----
        left = QVBoxLayout()
        left.setSpacing(14)
        self.clock_panel = TechPanel("NELLORE CLOCK", self.theme_mgr, indicator="IST")
        self.clock_weather = ClockWeatherWidget(self.theme_mgr)
        self.clock_panel.body.addWidget(self.clock_weather)
        left.addWidget(self.clock_panel, stretch=3)

        self.system_panel_frame = TechPanel("SYSTEM SPECS", self.theme_mgr, indicator="HOST")
        self.system_panel = SystemStatusWidget(self.theme_mgr)
        self.system_panel_frame.body.addWidget(self.system_panel)
        left.addWidget(self.system_panel_frame, stretch=2)

        self.event_panel = TechPanel("EVENT STREAM", self.theme_mgr, indicator="LIVE")
        self.event_stream = EventStreamView(self.theme_mgr)
        self.event_panel.body.addWidget(self.event_stream)
        left.addWidget(self.event_panel, stretch=4)

        self.left_widget = QWidget()
        self.left_widget.setLayout(left)
        self.root.addWidget(self.left_widget, 1, 0)

        # ----- CENTER column -----
        center = QVBoxLayout()
        center.setSpacing(14)
        self.reactor_panel = TechPanel("PARTICLE REACTOR", self.theme_mgr, indicator="CORE")
        self.reactor = ParticleGlobeReactor(self.theme_mgr)
        self.reactor.setMinimumSize(260, 220)
        self.reactor_panel.body.addWidget(self.reactor, stretch=1)
        center.addWidget(self.reactor_panel, stretch=5)

        self.transcript_panel = TechPanel("DIALOG", self.theme_mgr, indicator="LIVE")
        self.chat_view = ChatView(self.theme_mgr)
        self.chat_view.setMinimumHeight(220)
        self.transcript_panel.body.addWidget(self.chat_view, stretch=1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(10)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command...")
        self.input_field.returnPressed.connect(self.handle_return_pressed)
        input_row.addWidget(self.input_field)
        self.send_button = QPushButton("SEND")
        self.send_button.clicked.connect(self.handle_send_button_clicked)
        input_row.addWidget(self.send_button)
        self.transcript_panel.body.addLayout(input_row)

        center.addWidget(self.transcript_panel, stretch=5)
        self.center_widget = QWidget()
        self.center_widget.setLayout(center)
        self.root.addWidget(self.center_widget, 1, 1)

        # ----- RIGHT column -----
        right = QVBoxLayout()
        right.setSpacing(14)

        self.models_panel_frame = TechPanel("MODELS", self.theme_mgr, indicator="LOCAL")
        self.models_panel = ModelsPanel(self.theme_mgr, self.app_core)
        self.models_panel_frame.body.addWidget(self.models_panel)
        right.addWidget(self.models_panel_frame, stretch=3)

        self.voice_panel_frame = TechPanel("VOICE", self.theme_mgr, indicator="IO")
        self.voice_mode_combo = QComboBox()
        for value in ("persistent", "wake_word", "on_demand", "manual"):
            self.voice_mode_combo.addItem(format_voice_mode_label(value), value)
        self.voice_mode_combo.currentIndexChanged.connect(self.on_voice_mode_selected)
        self.voice_panel_frame.body.addWidget(self.voice_mode_combo)

        self.voice_state_label = QLabel("STATE: MUTED")
        self.mic_gate_label = QLabel("MIC GATE: CLOSED")
        self.wake_strategy_label = QLabel("WAKE ENGINE: Wake model")
        self.current_device_label = QLabel("DEVICE: System default")
        self.rejected_reason_label = QLabel("LAST REJECTED: None")
        self._voice_labels = [
            self.voice_state_label,
            self.mic_gate_label,
            self.wake_strategy_label,
            self.current_device_label,
            self.rejected_reason_label,
        ]
        for label in self._voice_labels:
            label.setWordWrap(True)
            self.voice_panel_frame.body.addWidget(label)
        right.addWidget(self.voice_panel_frame, stretch=2)

        self.telemetry_panel = TechPanel("SYSTEM PULSE", self.theme_mgr, indicator="LIVE")
        self.telemetry = PulseBars(self.theme_mgr)
        self.telemetry_panel.body.addWidget(self.telemetry)
        right.addWidget(self.telemetry_panel, stretch=2)

        self.mic_selector = MicSelector(self.theme_mgr)
        self.mic_selector.device_selected.connect(self.on_mic_selected)
        right.addWidget(self.mic_selector, stretch=1)

        self.process_btn = QPushButton("PROCESS GRID")
        self.process_btn.clicked.connect(self.toggle_process_panel)
        right.addWidget(self.process_btn)

        self.stop_btn = QPushButton("STOP SPEECH")
        self.stop_btn.clicked.connect(self.stop_speaking)
        right.addWidget(self.stop_btn)

        self.right_widget = QWidget()
        self.right_widget.setLayout(right)
        self.root.addWidget(self.right_widget, 1, 2)

        self.root.setColumnStretch(0, 3)
        self.root.setColumnStretch(1, 6)
        self.root.setColumnStretch(2, 3)
        self.root.setRowStretch(1, 1)

        self.process_panel = ProcessPanel(self.theme_mgr, self, self.app_core)
        self.process_panel.hide()
        self.process_panel.move(380, 120)

        self.theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(self.theme_mgr.theme)

        self._connect_runtime()
        self.refresh_voice_mode_button()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.check_status)
        self.status_timer.start(180)

        if getattr(self.app_core, "should_auto_start_voice", lambda: True)():
            QTimer.singleShot(1000, lambda: self.app_core.event_bus.publish("gui_toggle_mic", True))

    # -------- header ----------
    def _build_header(self):
        header = QFrame()
        header.setObjectName("hud_header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(14)

        self.title_label = QLabel("FRIDAY")
        layout.addWidget(self.title_label)
        self.subtitle_label = QLabel("LOCAL INTELLIGENCE SURFACE")
        layout.addWidget(self.subtitle_label)
        layout.addStretch(1)

        self.status_label = QLabel("route: idle  ·  lane: idle  ·  voice: idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.status_label)

        self.theme_btn = QPushButton()
        self.theme_btn.setFixedWidth(110)
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)
        return header

    def _toggle_theme(self) -> None:
        name = self.theme_mgr.toggle()
        _save_theme_pref(name)

    def _apply_theme(self, theme: Theme) -> None:
        self.central.setStyleSheet(f"background-color: {theme.bg};")
        self.title_label.setStyleSheet(
            f"color: {theme.text};"
            f"font-family: {FONT_STACK};"
            "font-size: 32px;"
            "font-weight: 800;"
            "letter-spacing: -0.5px;"
            "border: none;"
            "background: transparent;"
        )
        self.subtitle_label.setStyleSheet(label_style(theme, theme.text_dim, 12, "bold"))
        self.status_label.setStyleSheet(label_style(theme, theme.text_dim, 11))
        self.theme_btn.setStyleSheet(button_style(theme))
        self.theme_btn.setText("◐  LIGHT" if theme.name == "dark" else "◑  DARK")

        self.input_field.setStyleSheet(text_box_style(theme, 14))
        self.send_button.setStyleSheet(button_style(theme, primary=True))
        self.process_btn.setStyleSheet(button_style(theme))
        self.stop_btn.setStyleSheet(button_style(theme, danger=True))
        self.voice_mode_combo.setStyleSheet(combo_style(theme))
        for label in self._voice_labels:
            label.setStyleSheet(label_style(theme, theme.text_dim, 11))

    # -------- runtime wiring ----------
    def _connect_runtime(self):
        self.app_core.set_gui_callback(self._on_message_from_thread)
        self.message_ready.connect(self.render_message)
        self.shutdown_signal.connect(self.close)
        self.mic_toggle_ready.connect(self._on_mic_toggle)
        self.voice_response_ready.connect(self._on_voice_response)
        self.turn_started_ready.connect(self._on_turn_started)
        self.turn_processing_ready.connect(self._on_turn_processing)
        self.turn_finished_ready.connect(self._on_turn_finished)
        self.tool_finished_ready.connect(self._on_tool_finished)
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
        bus.subscribe("tool_finished", lambda payload: self.tool_finished_ready.emit(payload))
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
            self.event_stream.append("SPEECH", str(text)[:120])

    def toggle_pause_everything(self):
        stt = getattr(self.app_core, "stt", None)
        is_active = bool(getattr(stt, "is_listening", False) or getattr(stt, "wake_armed", False))
        if is_active:
            self.app_core.event_bus.publish("gui_toggle_mic", False)
            self.stop_speaking()
            self.reactor.set_state("muted")
            phrase = "Voice gate closed."
        else:
            phrase = "Voice gate opening."
            self.app_core.event_bus.publish("voice_response", phrase)
            QTimer.singleShot(1200, lambda: self.app_core.event_bus.publish("voice_activation_requested", {"source": "button"}))
        self.chat_view.add_message("system", phrase)

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
            routing_state = getattr(self.app_core, "routing_state", None)
            route_source = getattr(router, "current_route_source", "idle") if router else "idle"
            lane = getattr(router, "current_model_lane", "idle") if router else "idle"
            disabled_count = len(capabilities.disabled_skills()) if capabilities else 0
            mode = getattr(self.app_core, "get_listening_mode", lambda: "persistent")()
            last_tool = ""
            if routing_state:
                last_tool = getattr(routing_state.last_decision, "tool_name", "") or ""
            tool_part = f"  →  {last_tool}" if last_tool and last_tool != "idle" else ""
            self.status_label.setText(
                f"route: {route_source}{tool_part}  ·  lane: {lane}  ·  voice: {mode}  ·  disabled: {disabled_count}"
            )
            if lane and lane != "idle":
                self.models_panel.set_active_lane(lane)
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
        self.is_processing = True
        self.update_send_button_state()
        self.reactor.set_state("processing")
        self._pending_lane = None
        if isinstance(payload, dict):
            self.event_stream.append("TURN", str(payload.get("text", ""))[:120])

    def _on_turn_processing(self, payload):
        self.turn_state = "processing"
        self.is_processing = True
        self.update_send_button_state()
        self.reactor.set_state("processing")
        if not isinstance(payload, dict):
            return
        if "tool_name" in payload:
            tool = payload["tool_name"]
            args = payload.get("args") or {}
            self._append_route_line(tool, args)
            key = next((k for k in ("query", "topic", "text", "path", "url", "app", "command") if k in args), None)
            summary = tool
            if key:
                summary += f": {str(args[key])[:35]}"
            self.event_stream.append("RUN", summary[:120])
        elif "lane" in payload:
            lane = str(payload["lane"])
            self._pending_lane = lane
            self.event_stream.append("LLM", lane[:60])
            self.models_panel.set_active_lane(lane)
        elif payload.get("text"):
            self.event_stream.append("INFO", str(payload["text"])[:120])

    def _on_turn_finished(self, payload):
        self.turn_state = "idle"
        self.is_processing = False
        self.update_send_button_state()
        if isinstance(payload, dict) and payload.get("metrics"):
            metrics = payload["metrics"]
            dur = metrics.get("duration_ms", 0)
            ok = payload.get("ok", True)
            tag = "DONE" if ok else "FAIL"
            self.event_stream.append(tag, f"{'OK' if ok else 'FAIL'}  ·  {dur:.0f}ms")

    def _on_tool_finished(self, payload):
        if not isinstance(payload, dict):
            return
        tool = payload.get("tool_name", "?")
        ok = payload.get("ok", True)
        dur = payload.get("duration_ms", 0)
        status = "OK" if ok else "FAIL"
        err = payload.get("error", "")
        detail = f"  —  {err[:40]}" if err else ""
        tag = "DONE" if ok else "FAIL"
        self.event_stream.append(tag, f"{tool}  [{status}]  {dur:.0f}ms{detail}")

    def update_send_button_state(self):
        if not hasattr(self, "send_button"):
            return
        theme = self.theme_mgr.theme
        if getattr(self, "is_processing", False):
            self.send_button.setText("■ STOP")
            self.send_button.setStyleSheet(button_style(theme, danger=True))
        else:
            self.send_button.setText("SEND")
            self.send_button.setStyleSheet(button_style(theme, primary=True))

    def handle_return_pressed(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.app_core.process_input(text, source="gui")

    def handle_send_button_clicked(self):
        if getattr(self, "is_processing", False):
            self.app_core.cancel_current_task(announce=False)
        else:
            self.handle_return_pressed()

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
        self.chat_view.add_message("system", f"Microphone switched to {label}")
        self.event_stream.append("MIC", label)

    def _report_option_error(self, label, exc):
        message = str(exc) or exc.__class__.__name__
        logger.exception("HUD %s option failed: %s", label, exc)
        self.event_stream.append("FAIL", f"{label} {message}"[:120])
        self.chat_view.add_message("system", f"{label.title()} option failed: {message}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if offset.y() < 80:
                self.drag_pos = offset
                event.accept()
                return
        self.drag_pos = None
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        mode = "narrow" if w < 980 else "wide"
        if self._current_layout_mode == mode:
            return
        self._current_layout_mode = mode
        if mode == "narrow":
            self.root.addWidget(self.header_widget, 0, 0, 1, 1)
            self.root.addWidget(self.center_widget, 1, 0, 1, 1)
            self.root.addWidget(self.left_widget, 2, 0, 1, 1)
            self.root.addWidget(self.right_widget, 3, 0, 1, 1)
            self.root.setColumnStretch(0, 1)
            self.root.setColumnStretch(1, 0)
            self.root.setColumnStretch(2, 0)
        else:
            self.root.addWidget(self.header_widget, 0, 0, 1, 3)
            self.root.addWidget(self.left_widget, 1, 0, 1, 1)
            self.root.addWidget(self.center_widget, 1, 1, 1, 1)
            self.root.addWidget(self.right_widget, 1, 2, 1, 1)
            self.root.setColumnStretch(0, 3)
            self.root.setColumnStretch(1, 6)
            self.root.setColumnStretch(2, 3)

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
        elif event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif event.key() == Qt.Key.Key_T and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._toggle_theme()

    def _on_message_from_thread(self, payload):
        self.message_ready.emit(payload)

    def render_message(self, payload):
        if not isinstance(payload, dict):
            self.chat_view.add_message("assistant", str(payload), model_lane=self._pending_lane, model_label=self._lane_label(self._pending_lane))
            self.event_stream.append("ASSISTANT", str(payload)[:120])
            return
        text = payload.get("text", "")
        role = payload.get("role", "assistant")
        if not text:
            return
        lane = self._pending_lane if role == "assistant" else None
        self.chat_view.add_message(role, text, model_lane=lane, model_label=self._lane_label(lane))
        self.event_stream.append(role.upper(), text[:120])

    def _lane_label(self, lane: str | None) -> str | None:
        if not lane:
            return None
        manager = getattr(getattr(self.app_core, "router", None), "model_manager", None)
        if not manager:
            return lane
        try:
            profile = manager.profile(lane)
        except Exception:
            return lane
        return os.path.basename(profile.path).replace(".gguf", "")

    def _append_route_line(self, tool_name: str, args: dict | None = None):
        label = tool_name.replace("_", " ")
        parts = [f"▸ {label}"]
        if args:
            key = next((k for k in ("query", "topic", "text", "path", "url", "app", "command") if k in args), None)
            if key:
                val = str(args[key])[:40]
                parts.append(f"({val})")
        self.chat_view.add_route("  ".join(parts))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def start_hud(app_core):
    app = QApplication.instance() or QApplication(sys.argv)
    window = JarvisHUD(app_core)
    # Global scrollbar styles already injected per-widget; set window-level too.
    app.setStyleSheet(scrollbar_style(window.theme_mgr.theme))
    window.theme_mgr.subscribe(lambda t: app.setStyleSheet(scrollbar_style(t)))
    window.showMaximized()
    sys.exit(app.exec())
