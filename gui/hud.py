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

from PyQt6.QtCore import QDateTime, QPointF, QRectF, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
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
    glow: str
    gold: str


def _theme_dark() -> Theme:
    return Theme(
        name="dark",
        bg="#050505",
        surface="#0d0d0d",
        surface_alt="rgba(28, 28, 28, 0.70)",
        panel="rgba(10, 10, 10, 0.94)",
        panel_border="#2a2a2a",
        text="#d0d0d0",
        text_dim="#808080",
        text_muted="#454545",
        accent="#888888",
        accent_soft="rgba(150, 150, 150, 22)",
        user_bubble="rgba(50, 50, 50, 0.70)",
        user_bubble_text="#d0d0d0",
        assistant_bubble="rgba(22, 22, 22, 0.85)",
        assistant_bubble_text="#c8c8c8",
        system_bubble="rgba(18, 18, 18, 0.65)",
        success="#4ad66d",
        warning="#f5a623",
        danger="#e53935",
        info="#6a9ab0",
        purple="#a060d0",
        magenta="#e040aa",
        badge_bg="rgba(150, 150, 150, 18)",
        scroll_track="rgba(35, 35, 35, 0.60)",
        scroll_handle="rgba(100, 100, 100, 0.55)",
        glow="#e0e0e0",
        gold="#c8a040",
    )


def _theme_light() -> Theme:
    return Theme(
        name="light",
        bg="#eeeeee",
        surface="#ffffff",
        surface_alt="#e0e0e0",
        panel="rgba(250, 250, 250, 0.97)",
        panel_border="#b8b8b8",
        text="#111111",
        text_dim="#505050",
        text_muted="#909090",
        accent="#444444",
        accent_soft="rgba(0, 0, 0, 14)",
        user_bubble="rgba(0, 0, 0, 0.07)",
        user_bubble_text="#111111",
        assistant_bubble="rgba(0, 0, 0, 0.04)",
        assistant_bubble_text="#1a1a1a",
        system_bubble="rgba(0, 0, 0, 0.03)",
        success="#1a7a3c",
        warning="#b06800",
        danger="#c62828",
        info="#2c6080",
        purple="#5e3490",
        magenta="#9e1f70",
        badge_bg="rgba(0, 0, 0, 10)",
        scroll_track="rgba(0, 0, 0, 0.08)",
        scroll_handle="rgba(0, 0, 0, 0.28)",
        glow="#222222",
        gold="#8a6000",
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


def _load_tts_muted() -> bool:
    try:
        with open(_THEME_STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
            return bool(data.get("tts_muted", False))
    except Exception:
        return False


def _save_tts_muted(muted: bool) -> None:
    try:
        os.makedirs(os.path.dirname(_THEME_STATE_PATH), exist_ok=True)
        try:
            with open(_THEME_STATE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
        except Exception:
            data = {}
        data["tts_muted"] = muted
        with open(_THEME_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        logger.exception("Failed to save TTS mute preference")


# ---------------------------------------------------------------------------
# Style helpers (theme-aware)
# ---------------------------------------------------------------------------


FONT_STACK = "'Segoe UI Variable', 'SF Pro Display', 'Inter', 'Helvetica Neue', sans-serif"
MONO_STACK = "'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Menlo', monospace"


def panel_style(theme: Theme, border: str | None = None) -> str:
    b = border or theme.panel_border
    return (
        f"background-color: {theme.panel};"
        f"border: 1px solid {b};"
        "border-radius: 0px;"
        f"border-top: 2px solid {theme.accent};"
    )


def panel_title_style(theme: Theme) -> str:
    return (
        f"color: {theme.accent};"
        f"font-family: {MONO_STACK};"
        "font-size: 9px;"
        "font-weight: bold;"
        "letter-spacing: 3px;"
        "border: none;"
        "background: transparent;"
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
        "border-radius: 2px;"
        "padding: 9px 16px;"
        f"font-family: {MONO_STACK};"
        "font-weight: 600;"
        "font-size: 12px;"
        "letter-spacing: 1px;"
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
        f"font-family: {MONO_STACK};"
        f"font-size: {font_size}px;"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 2px;"
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
        "border-radius: 2px;"
        "padding: 8px 12px;"
        f"font-family: {MONO_STACK};"
        "font-size: 12px;"
        "}"
        "QComboBox::drop-down { border: none; width: 20px; }"
        "QComboBox QAbstractItemView {"
        f"background-color: {theme.surface};"
        f"color: {theme.text};"
        f"selection-background-color: {theme.accent};"
        "selection-color: white;"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 2px;"
        "padding: 4px;"
        "}"
    )


def scrollbar_style(theme: Theme) -> str:
    """Global application stylesheet: scrollbars + context menus."""
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
        # Right-click context menu (Copy, Select All, etc.)
        "QMenu {"
        f"background: {theme.surface};"
        f"color: {theme.text};"
        f"border: 1px solid {theme.panel_border};"
        "border-radius: 2px;"
        "padding: 4px 0px;"
        "}"
        "QMenu::item {"
        "padding: 5px 22px 5px 12px;"
        "border-radius: 0px;"
        "}"
        "QMenu::item:selected {"
        f"background: {theme.accent_soft};"
        f"color: {theme.accent};"
        "}"
        "QMenu::separator {"
        f"height: 1px; background: {theme.panel_border}; margin: 3px 0px;"
        "}"
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
        self.title_label.setStyleSheet(panel_title_style(theme))
        self.indicator.setStyleSheet(label_style(theme, theme.success, 9, "bold"))


# ---------------------------------------------------------------------------
# Arc Reactor — Iron Man JARVIS-style animated core widget
# ---------------------------------------------------------------------------


class _MiniReactorIcon(QWidget):
    """Tiny 3-ring arc reactor icon used in the header."""

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._phase = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(50)
        theme_mgr.subscribe(lambda _t: self.update())

    def _tick(self):
        self._phase = (self._phase + 0.04) % math.tau
        self.update()

    def paintEvent(self, event):
        theme = self._theme_mgr.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 2
        p.setPen(Qt.PenStyle.NoPen)
        # Outer dot ring — 36 dots, every 3rd is accent-colored tick
        border_c = QColor(theme.panel_border)
        for i in range(36):
            ang = self._phase * 0.5 + i * math.tau / 36
            px = cx + r * math.cos(ang)
            py = cy + r * math.sin(ang)
            is_tick = (i % 3 == 0)
            dot = QColor(theme.accent if is_tick else theme.panel_border)
            dot.setAlpha(150 if is_tick else 70)
            p.setBrush(dot)
            p.drawEllipse(QPointF(px, py), 1.4 if is_tick else 0.8, 1.4 if is_tick else 0.8)
        # Mid rotating dot ring — 24 pulsing dots
        for i in range(24):
            ang = self._phase + i * math.tau / 24
            px = cx + r * 0.65 * math.cos(ang)
            py = cy + r * 0.65 * math.sin(ang)
            wave = 0.5 + 0.5 * math.sin(ang * 2 + self._phase * 0.7)
            dot = QColor(theme.accent)
            dot.setAlpha(int(55 + 140 * wave))
            p.setBrush(dot)
            p.drawEllipse(QPointF(px, py), 0.7 + wave * 0.7, 0.7 + wave * 0.7)
        # Core glow — radial gradient filled dot, no outline
        grad = QRadialGradient(QPointF(cx, cy), r * 0.32)
        grad.setColorAt(0.0, QColor(theme.glow))
        grad.setColorAt(1.0, QColor(theme.accent))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), r * 0.32, r * 0.32)


class ArcReactorWidget(QWidget):
    """Hybrid particle-globe + arc reactor — particle cloud orbiting arc reactor structure."""

    clicked = pyqtSignal()

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr

        # Particle globe (original golden-spiral distribution)
        rng = random.Random(42)
        self.stars = [
            (rng.random(), rng.random(), rng.uniform(0.45, 1.8),
             rng.uniform(0.18, 0.72), rng.uniform(0, math.tau))
            for _ in range(120)
        ]
        count = 1800
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        self.particles = []
        for index in range(count):
            z = 1.0 - (2.0 * (index + 0.5) / count)
            ring = math.sqrt(max(0.0, 1.0 - z * z))
            theta = index * golden_angle
            shell_bias = rng.uniform(0.82, 1.0) ** 0.38
            self.particles.append({
                "x": ring * math.cos(theta),
                "y": z,
                "z": ring * math.sin(theta),
                "shell": shell_bias,
                "size": rng.uniform(0.65, 1.65),
                "phase": rng.uniform(0, math.tau),
                "twinkle": rng.uniform(0.75, 1.25),
            })

        self.state = "muted"
        self.phase = 0.0
        self.inner_phase = 0.0
        self.pulse_phase = 0.0
        self.ripple_phase = 0.0
        self.wave_phase = 0.0
        self.speech_energy = 0.0
        self._speaking_until = 0.0
        self.setMinimumSize(250, 200)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(22)
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

        speeds = {
            "speaking":   (0.028, -0.018),
            "processing": (0.018, -0.012),
            "listening":  (0.014, -0.009),
            "armed":      (0.010, -0.006),
            "muted":      (0.005, -0.003),
        }
        outer_speed, inner_speed = speeds.get(self.state, (0.005, -0.003))
        self.phase = (self.phase + outer_speed) % math.tau
        self.inner_phase = (self.inner_phase + inner_speed) % math.tau
        self.pulse_phase = (self.pulse_phase + 0.05) % math.tau
        self.ripple_phase = (self.ripple_phase + 0.16 * max(0.05, self.speech_energy)) % math.tau
        self.wave_phase = (self.wave_phase + 0.18 * self.speech_energy) % math.tau
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()

    def _state_color(self) -> QColor:
        theme = self._theme_mgr.theme
        if self.state == "speaking" or self.speech_energy > 0.2:
            return QColor(theme.magenta)
        if self.state == "processing":
            return QColor(theme.purple)
        if self.state == "listening":
            return QColor(theme.info)
        if self.state == "armed":
            return QColor(theme.glow)
        return QColor(theme.text_muted)

    def _rotate_point(self, x, y, z, yaw, pitch):
        cosy, siny = math.cos(yaw), math.sin(yaw)
        x, z = x * cosy + z * siny, -x * siny + z * cosy
        cosp, sinp = math.cos(pitch), math.sin(pitch)
        y, z = y * cosp - z * sinp, y * sinp + z * cosp
        return x, y, z

    def paintEvent(self, event):
        theme = self._theme_mgr.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        cx = rect.width() / 2
        cy = rect.height() / 2
        min_r = min(cx, cy)
        radius = min_r * 0.42
        state_c = self._state_color()

        # --- Background ---
        painter.fillRect(rect, QColor(theme.bg))
        painter.setPen(Qt.PenStyle.NoPen)

        # --- Stars (background twinkle) ---
        star_base = QColor(theme.text_dim)
        for sx, sy, size, alpha, sph in self.stars:
            sc = QColor(star_base)
            twinkle = 0.5 + 0.5 * math.sin(self.phase * 0.7 + sph)
            sc.setAlpha(int(alpha * 55 * twinkle))
            painter.setBrush(sc)
            painter.drawEllipse(QPointF(sx * rect.width(), sy * rect.height()), size * 0.7, size * 0.7)

        # --- Outer particle ring (72 dots rotating; every 6th is a bright tick dot) ---
        outer_r = min_r * 0.88
        ring_base = QColor(theme.panel_border)
        for i in range(72):
            ang = self.phase + i * math.tau / 72
            px = cx + outer_r * math.cos(ang)
            py = cy + outer_r * math.sin(ang)
            is_tick = (i % 6 == 0)
            dot = QColor(state_c if is_tick else ring_base)
            dot.setAlpha(200 if is_tick else 70)
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(px, py), 2.4 if is_tick else 1.0, 2.4 if is_tick else 1.0)

        # --- Mid particle ring (48 dots counter-rotating with pulse wave) ---
        mid_r = min_r * 0.65
        for i in range(48):
            ang = self.inner_phase + i * math.tau / 48
            px = cx + mid_r * math.cos(ang)
            py = cy + mid_r * math.sin(ang)
            wave = 0.5 + 0.5 * math.sin(ang * 3 + self.pulse_phase)
            dot = QColor(state_c)
            dot.setAlpha(int(25 + 165 * wave))
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(px, py), 1.1 + wave * 1.7, 1.1 + wave * 1.7)

        # --- Inner particle ring (36 dots, slow counter-rotate) ---
        inner_ring_r = min_r * 0.46
        for i in range(36):
            ang = -self.phase * 0.55 + i * math.tau / 36
            px = cx + inner_ring_r * math.cos(ang)
            py = cy + inner_ring_r * math.sin(ang)
            wave = 0.4 + 0.6 * math.sin(ang * 2 - self.pulse_phase * 0.6)
            dot = QColor(state_c)
            dot.setAlpha(max(0, int(12 + 70 * wave)))
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(px, py), 0.8 + wave * 0.7, 0.8 + wave * 0.7)

        # --- Particle globe cloud ---
        yaw = self.phase * 0.30
        pitch = 0.16 * math.sin(self.phase * 0.15)
        points = []
        for index, p in enumerate(self.particles):
            x, y, z = self._rotate_point(p["x"], p["y"], p["z"], yaw, pitch)
            rs = p["shell"]
            perspective = 0.76 + 0.26 * z
            px = cx + x * radius * rs * perspective
            py = cy + y * radius * rs * (0.82 + 0.08 * z)
            edge = min(1.0, math.sqrt(p["x"] * p["x"] + p["y"] * p["y"]) * 1.06)
            depth = (z + 1.0) * 0.5
            if self.speech_energy > 0.02:
                row_wave = math.sin((p["y"] * 13.5) + self.wave_phase)
                sec_wave = 0.40 * math.sin((p["y"] * 24.0) - self.wave_phase * 1.3 + p["phase"])
                px += self.speech_energy * radius * 0.10 * (0.55 + 0.45 * depth) * (row_wave + sec_wave)
            ev = edge ** 1.8
            alpha = int((14 + 90 * depth) * (0.18 + 0.82 * ev) * p["twinkle"])
            size = p["size"] * (0.50 + 0.44 * depth)
            points.append((z, px, py, size, max(5, min(140, alpha)), index))

        points.sort(key=lambda item: item[0])
        for z, px, py, size, alpha, index in points:
            dot = QColor(state_c)
            if index % 9 == 0:
                dot = QColor(theme.text_dim)
            dot.setAlpha(max(6, min(190, alpha)))
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(px, py), size, size)

        # --- Triangle constellation (vertex clusters + edge particles, no lines) ---
        tri_r = min_r * 0.36
        drift = self.inner_phase * 0.28
        for vi in range(3):
            vx = cx + tri_r * math.cos(drift + vi * math.tau / 3 - math.pi / 2)
            vy = cy + tri_r * math.sin(drift + vi * math.tau / 3 - math.pi / 2)
            vx2 = cx + tri_r * math.cos(drift + (vi + 1) * math.tau / 3 - math.pi / 2)
            vy2 = cy + tri_r * math.sin(drift + (vi + 1) * math.tau / 3 - math.pi / 2)
            # Bright vertex dot
            bright = QColor(state_c)
            bright.setAlpha(235)
            painter.setBrush(bright)
            painter.drawEllipse(QPointF(vx, vy), 2.8, 2.8)
            # Halo cluster around vertex
            for di in range(7):
                sang = di * math.tau / 7 + self.pulse_phase * 0.4
                sr = 4.0 + 1.8 * math.sin(self.pulse_phase + di)
                halo = QColor(state_c)
                halo.setAlpha(max(0, int(75 + 80 * math.sin(self.pulse_phase + di * 0.9))))
                painter.setBrush(halo)
                painter.drawEllipse(
                    QPointF(vx + sr * math.cos(sang), vy + sr * math.sin(sang)), 1.0, 1.0
                )
            # Edge particles between this vertex and next
            for step in range(1, 9):
                t = step / 9.0
                ex = vx + t * (vx2 - vx)
                ey = vy + t * (vy2 - vy)
                edge_c = QColor(state_c)
                edge_c.setAlpha(max(0, int(40 + 55 * math.sin(self.pulse_phase * 1.2 + t * math.tau))))
                painter.setBrush(edge_c)
                painter.drawEllipse(QPointF(ex, ey), 0.9, 0.9)

        # --- Gold center ring particles ---
        gold_r = min_r * 0.14
        gold_base = QColor(theme.gold)
        for i in range(20):
            ang = self.phase * 0.55 + i * math.tau / 20
            px = cx + gold_r * math.cos(ang)
            py = cy + gold_r * math.sin(ang)
            pulse = 0.5 + 0.5 * math.sin(self.pulse_phase + i * 0.63)
            gold_c = QColor(gold_base)
            gold_c.setAlpha(int(90 + 140 * pulse))
            sz = 0.9 + pulse * 1.4
            painter.setBrush(gold_c)
            painter.drawEllipse(QPointF(px, py), sz, sz)

        # --- Radial core pulse (gradient filled dot, no outline) ---
        core_r = min_r * 0.26 * (1.0 + 0.16 * math.sin(self.pulse_phase))
        grad = QRadialGradient(QPointF(cx, cy), core_r)
        ic = QColor(state_c); ic.setAlpha(210)
        mc = QColor(state_c); mc.setAlpha(70)
        tc = QColor(state_c); tc.setAlpha(0)
        grad.setColorAt(0.0, QColor("#ffffff"))
        grad.setColorAt(0.14, ic)
        grad.setColorAt(0.55, mc)
        grad.setColorAt(1.0, tc)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # --- Ripple particle rings when speaking (dots on expanding circles, no drawn arcs) ---
        if self.speech_energy > 0.02:
            for i in range(3):
                rp = (self.ripple_phase + i * math.tau / 3) % math.tau
                rr = min_r * 0.80 * (rp / math.tau)
                fade = 1.0 - (rp / math.tau)
                for di in range(28):
                    ang = di * math.tau / 28
                    rx = cx + rr * math.cos(ang)
                    ry = cy + rr * math.sin(ang)
                    rip_c = QColor(state_c)
                    rip_c.setAlpha(int(105 * fade * self.speech_energy))
                    painter.setBrush(rip_c)
                    painter.drawEllipse(QPointF(rx, ry), max(0.7, 1.5 * fade), max(0.7, 1.5 * fade))

        # --- State label ---
        lbl_c = QColor(state_c)
        lbl_c.setAlpha(190)
        painter.setPen(QPen(lbl_c))
        painter.setFont(QFont("JetBrains Mono", 9, QFont.Weight.Bold))
        painter.drawText(
            QRectF(0, cy + min_r * 0.88 + 6, rect.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            self.state.upper(),
        )


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
            painter.drawRoundedRect(track, 1, 1)
            fill = QRectF(track.left(), track.top(), track.width() * self.values[i] / 100, track.height())
            painter.setBrush(QColor(theme.success if i % 2 else theme.accent))
            painter.drawRoundedRect(fill, 1, 1)


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


class _TypewriterEffect:
    """Reveals text character-by-character for assistant messages."""

    _CHARS_PER_TICK = 5
    _INTERVAL_MS = 16

    def __init__(self, label: "QLabel", full_text: str, parent: "QWidget"):
        self._label = label
        self._full = full_text
        self._pos = 0
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._INTERVAL_MS)

    def _tick(self) -> None:
        self._pos = min(self._pos + self._CHARS_PER_TICK, len(self._full))
        cursor = "▋" if self._pos < len(self._full) else ""
        self._label.setText(self._full[:self._pos] + cursor)
        if self._pos >= len(self._full):
            self._timer.stop()

    def finish(self) -> None:
        self._timer.stop()
        self._label.setText(self._full)


class ChatBubble(QFrame):
    """Full-width message bubble. User = right-aligned text. Assistant = left-aligned text."""

    def __init__(self, message: _ChatMessage, theme: Theme, parent=None):
        super().__init__(parent)
        self.message = message
        self._typewriter: "_TypewriterEffect | None" = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        inner_layout = QVBoxLayout(self)
        inner_layout.setContentsMargins(16, 10, 16, 12)
        inner_layout.setSpacing(4)

        align_flag = Qt.AlignmentFlag.AlignRight if message.role == "user" else Qt.AlignmentFlag.AlignLeft

        self.meta_label = QLabel(self._meta_text(message))
        self.meta_label.setAlignment(align_flag)
        self.text_label = QLabel(message.text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(align_flag | Qt.AlignmentFlag.AlignTop)
        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        inner_layout.addWidget(self.meta_label)
        inner_layout.addWidget(self.text_label)

        self.apply_theme(theme)

    def start_typewriter(self, text: str) -> None:
        """Animate assistant reply text appearing progressively."""
        self._typewriter = _TypewriterEffect(self.text_label, text, self)

    def stop_typewriter(self) -> None:
        if self._typewriter:
            self._typewriter.finish()
            self._typewriter = None

    def set_streaming_text(self, text: str) -> None:
        """Update text live during chunk streaming (no typewriter effect)."""
        if self._typewriter:
            self._typewriter.finish()
            self._typewriter = None
        self.text_label.setText(text)

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
            border_top = theme.accent
            meta_color = theme.text_dim
        elif self.message.role == "assistant":
            bg = theme.assistant_bubble
            fg = theme.assistant_bubble_text
            border_top = theme.success
            meta_color = theme.success
        else:
            bg = theme.system_bubble
            fg = theme.text_dim
            border_top = theme.panel_border
            meta_color = theme.text_muted

        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: none; border-left: 2px solid {border_top}; border-radius: 0px; }}"
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
        # Return a compact fixed hint so Qt's layout never tries to grow the
        # parent window when chat bubbles are added. Actual size is determined
        # entirely by the layout's stretch factors — content scrolls internally.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self.setWidget(self._inner)

        self._bubbles: list = []
        self._last_assistant_bubble: ChatBubble | None = None
        self._streaming_bubble: ChatBubble | None = None

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

    def sizeHint(self):
        return QSize(400, 300)

    def minimumSizeHint(self):
        return QSize(200, 220)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(
            f"QScrollArea {{ background: {theme.surface}; border: 1px solid {theme.panel_border}; border-radius: 0px; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {theme.surface}; }}"
            + scrollbar_style(theme)
        )
        for widget in self._bubbles:
            if hasattr(widget, "apply_theme"):
                widget.apply_theme(theme)

    def add_message(self, role: str, text: str, model_lane: str | None = None, model_label: str | None = None) -> ChatBubble | None:
        if not text or not str(text).strip():
            return None
        clean = str(text).strip()
        msg = _ChatMessage(role=role, text=clean, model_lane=model_lane, model_label=model_label)
        # Start assistant bubbles empty so typewriter can fill them
        display_text = "" if role == "assistant" else clean
        msg_display = _ChatMessage(role=role, text=display_text, model_lane=model_lane, model_label=model_label)
        bubble = ChatBubble(msg_display, self._theme_mgr.theme, parent=self._inner)
        bubble.message = msg  # store full message for model updates
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        self._bubbles.append(bubble)
        if role == "assistant":
            self._last_assistant_bubble = bubble
            bubble.start_typewriter(clean)
        QTimer.singleShot(30, self._scroll_bottom)
        return bubble

    def add_route(self, text: str) -> None:
        line = RouteLine(text, self._theme_mgr.theme, parent=self._inner)
        self._layout.insertWidget(self._layout.count() - 1, line)
        self._bubbles.append(line)
        QTimer.singleShot(30, self._scroll_bottom)

    def mark_assistant_model(self, lane: str | None, label: str | None) -> None:
        if self._last_assistant_bubble is not None:
            self._last_assistant_bubble.update_model(lane, label)

    @property
    def streaming_bubble(self) -> "ChatBubble | None":
        return self._streaming_bubble

    def start_streaming_bubble(self, model_lane=None, model_label=None) -> "ChatBubble":
        """Create an empty assistant bubble and register it as the live-streaming target."""
        msg = _ChatMessage(role="assistant", text="▋", model_lane=model_lane, model_label=model_label)
        bubble = ChatBubble(msg, self._theme_mgr.theme, parent=self._inner)
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        self._bubbles.append(bubble)
        self._last_assistant_bubble = bubble
        self._streaming_bubble = bubble
        QTimer.singleShot(30, self._scroll_bottom)
        return bubble

    def finalize_streaming_bubble(self, model_lane=None, model_label=None) -> None:
        """Mark streaming complete; optionally update model metadata on the bubble."""
        if self._streaming_bubble:
            if model_lane or model_label:
                self._streaming_bubble.update_model(model_lane, model_label)
            self._streaming_bubble = None

    def _scroll_bottom(self) -> None:
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())
        QTimer.singleShot(80, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))


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
    "ROUTE": "info",      # which router picked the tool (deterministic/embed/etc.)
    "GEMMA": "magenta",   # LoRA-tuned 270M shadow prediction
}


class EventStreamView(QTextEdit):
    """Stable event log using QTextEdit with HTML rows — no per-item widget glitches."""

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._events: list[dict] = []
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.document().setDocumentMargin(6)

        theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(theme_mgr.theme)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(
            "QTextEdit {"
            f"background-color: {theme.surface};"
            f"color: {theme.text};"
            f"border: none;"
            "border-radius: 0px;"
            "padding: 4px;"
            "}"
            + scrollbar_style(theme)
        )
        self._rebuild()

    def append(self, tag: str, text: str) -> None:
        self._events.append({
            "tag": tag.upper(),
            "text": str(text or ""),
            "ts": time.strftime("%H:%M:%S"),
        })
        if len(self._events) > _EVENT_STREAM_MAX_LINES:
            self._events = self._events[-_EVENT_STREAM_MAX_LINES:]
        # Append just the new row without full rebuild — fast path
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.insertHtml(self._row_html(self._events[-1]) + "<br>")
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _rebuild(self) -> None:
        self.clear()
        if not self._events:
            return
        html = "".join(self._row_html(ev) + "<br>" for ev in self._events)
        self.setHtml(f"<html><body style='margin:0;padding:0;'>{html}</body></html>")
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _row_html(self, payload: dict) -> str:
        theme = self._theme_mgr.theme
        tag = payload["tag"]
        color_key = _EVENT_COLORS.get(tag, "text_dim")
        tag_color = getattr(theme, color_key, theme.text_dim)
        ts = html_escape(payload["ts"])
        text = html_escape(payload["text"])
        tag_str = html_escape(tag[:8])
        mono = MONO_STACK.replace("'", "")
        sans = FONT_STACK.replace("'", "")
        return (
            f"<span style='color:{theme.text_dim};font-family:{mono};font-size:10px;'>{ts}</span>"
            f"&nbsp;"
            f"<span style='color:{tag_color};font-family:{mono};font-size:10px;font-weight:bold;"
            f"padding:1px 4px;'>{tag_str}</span>"
            f"&nbsp;&nbsp;"
            f"<span style='color:{theme.text};font-family:{sans};font-size:12px;"
            f"line-height:1.5;'>{text}</span>"
        )


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

        self._build_vision_row()
        self._build_gemma_row()

    def _build_gemma_row(self) -> None:
        """Add a card for the LoRA-tuned Gemma 270M intent router.

        Always rendered when the GGUF exists in ``models/`` so users can
        see (a) whether the model is on disk and (b) whether the
        ``FRIDAY_USE_GEMMA_ROUTER=1`` flag actually loaded it. The card
        highlights green when ``app.gemma_router`` is loaded, dim when
        the file is there but the flag is off, red when the file is
        missing.
        """
        role = "gemma"
        if role in self._rows:
            return
        # Match the path bench / app.py use.
        gguf = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", "gemma-3-270m-it-Q4_K_M.gguf",
        )

        card = QFrame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        header = QHBoxLayout()
        lane_label = QLabel("GEMMA")
        status_dot = QLabel("●")
        header.addWidget(lane_label)
        header.addStretch(1)
        header.addWidget(status_dot)
        card_layout.addLayout(header)

        name_label = QLabel("gemma-3-270m-it-Q4_K_M.gguf  (LoRA — intent router)")
        name_label.setWordWrap(True)
        card_layout.addWidget(name_label)

        detail_label = QLabel(self._gemma_detail(gguf))
        card_layout.addWidget(detail_label)

        self._rows_container.addWidget(card)
        self._rows[role] = {
            "card":         card,
            "lane_label":   lane_label,
            "status_dot":   status_dot,
            "name_label":   name_label,
            "detail_label": detail_label,
            "_gguf_path":   gguf,
        }

    def _gemma_detail(self, gguf_path: str) -> str:
        enabled = bool(getattr(self._app_core, "gemma_router", None))
        on_disk = os.path.exists(gguf_path)
        if enabled:
            return "active  ·  shadow-routing every turn"
        if on_disk:
            return "loaded on disk  ·  set FRIDAY_USE_GEMMA_ROUTER=1 to activate"
        return "missing  ·  retrain via scripts/train_gemma_lora.py"

    def _build_vision_row(self) -> None:
        """Add a card for the VLM if vision is enabled in config."""
        cfg = getattr(self._app_core, "config", None)
        vis_cfg = cfg.get("vision", {}) if cfg else {}
        if not vis_cfg.get("enabled", False):
            return
        model_path = vis_cfg.get("model_path", "")
        if not model_path:
            return

        role = "vision"
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

        name_label = QLabel(os.path.basename(model_path))
        name_label.setWordWrap(True)
        card_layout.addWidget(name_label)

        n_ctx = vis_cfg.get("n_ctx", 2048)
        detail_label = QLabel(f"ctx {n_ctx}  ·  lazy")
        card_layout.addWidget(detail_label)

        self._rows_container.addWidget(card)
        self._rows[role] = {
            "card": card,
            "lane_label": lane_label,
            "status_dot": status_dot,
            "name_label": name_label,
            "detail_label": detail_label,
        }

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
                "border-radius: 0px;"
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
        if role == "vision":
            return self._vision_status()
        if role == "gemma":
            row = self._rows.get("gemma") or {}
            gguf = row.get("_gguf_path", "")
            if not gguf or not os.path.exists(gguf):
                return "missing"
            if getattr(self._app_core, "gemma_router", None) is not None:
                return "loaded"
            return "available"
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

    def _vision_status(self) -> str:
        cfg = getattr(self._app_core, "config", None)
        vis_cfg = cfg.get("vision", {}) if cfg else {}
        model_path = vis_cfg.get("model_path", "")
        if not model_path:
            return "unknown"
        manager = self._manager()
        base_dir = getattr(manager, "base_dir", None) if manager else None
        if base_dir and not os.path.isabs(model_path):
            abs_path = os.path.join(base_dir, model_path)
        else:
            abs_path = model_path
        if not os.path.exists(abs_path):
            return "missing"
        svc = self._vision_service()
        if svc and svc._llm is not None:
            return "loaded"
        return "available"

    def _vision_service(self):
        loader = getattr(self._app_core, "extension_loader", None)
        for ext in getattr(loader, "extensions", []):
            plugin = getattr(ext, "plugin", ext)
            svc = getattr(plugin, "_service", None)
            if svc and hasattr(svc, "_model_path") and hasattr(svc, "_llm"):
                return svc
        return None

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
        # Keep the Gemma card's detail line in sync with the flag/file state.
        gemma_row = self._rows.get("gemma")
        if gemma_row:
            gemma_row["detail_label"].setText(self._gemma_detail(gemma_row.get("_gguf_path", "")))
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
# Scan-line overlay — sweeping horizontal line over the left column
# ---------------------------------------------------------------------------


class ScanLineOverlay(QWidget):
    """Transparent overlay that draws a faint JARVIS-style scan line sweep."""

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._y = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)
        theme_mgr.subscribe(lambda _t: self.update())

    def _tick(self):
        h = self.height() or 600
        self._y = (self._y + 3) % h
        self.update()

    def paintEvent(self, event):
        theme = self._theme_mgr.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(theme.accent)
        for offset in range(20):
            y_pos = self._y - offset
            if y_pos < 0:
                continue
            c.setAlpha(max(0, 80 - offset * 4))
            p.setPen(QPen(c, 1))
            p.drawLine(0, y_pos, self.width(), y_pos)


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
    router_decision_ready = pyqtSignal(object)
    gemma_prediction_ready = pyqtSignal(object)
    listening_mode_ready = pyqtSignal(object)
    voice_runtime_ready = pyqtSignal(object)
    llm_chunk_ready = pyqtSignal(object)

    def __init__(self, app_core):
        super().__init__()
        self.app_core = app_core
        self.theme_mgr = ThemeManager(_load_theme_pref())
        self.app_core.tts_muted = _load_tts_muted()
        self.turn_state = "idle"
        self.voice_runtime_state = {}
        self.drag_pos = None
        self._speaking_until = 0.0
        self._input_worker: _InputWorker | None = None
        self._current_layout_mode = None
        self._pending_lane: str | None = None
        self._turn_cancelled = False  # True only when STOP was clicked mid-turn

        self.setWindowTitle("FRIDAY")

        # Fit the window inside the available screen area (excludes taskbar).
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            win_w = min(1180, avail.width())
            win_h = min(720, avail.height())
            self.resize(win_w, win_h)
            # Centre on the available area
            x = avail.x() + (avail.width() - win_w) // 2
            y = avail.y() + (avail.height() - win_h) // 2
            self.move(x, y)
        else:
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
        left.addWidget(self.clock_panel, stretch=2)

        self.event_panel = TechPanel("EVENT STREAM", self.theme_mgr, indicator="LIVE")
        self.event_stream = EventStreamView(self.theme_mgr)
        self.event_panel.body.addWidget(self.event_stream)
        left.addWidget(self.event_panel, stretch=5)

        self.left_widget = QWidget()
        self.left_widget.setLayout(left)
        self.root.addWidget(self.left_widget, 1, 0)

        # Scan-line overlay over the left column
        self.scan_overlay = ScanLineOverlay(self.theme_mgr, self.left_widget)
        QTimer.singleShot(100, lambda: (
            self.scan_overlay.resize(self.left_widget.size()),
            self.scan_overlay.raise_(),
        ))

        # ----- CENTER column -----
        center = QVBoxLayout()
        center.setSpacing(14)
        self.reactor_panel = TechPanel("ARC REACTOR", self.theme_mgr, indicator="CORE")
        self.reactor = ArcReactorWidget(self.theme_mgr)
        self.reactor.setMinimumSize(260, 220)
        self.reactor_panel.body.addWidget(self.reactor, stretch=1)
        center.addWidget(self.reactor_panel, stretch=5)

        self.transcript_panel = TechPanel("DIALOG", self.theme_mgr, indicator="LIVE")
        self.chat_view = ChatView(self.theme_mgr)
        self.chat_view.setMinimumHeight(220)
        self.transcript_panel.body.addWidget(self.chat_view, stretch=1)

        self._attached_file_path: str | None = None
        self._attached_file_label = QLabel("")
        self._attached_file_label.setVisible(False)
        self.transcript_panel.body.addWidget(self._attached_file_label)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(8)
        self.file_btn = QPushButton("@")
        self.file_btn.setFixedWidth(38)
        self.file_btn.setToolTip("Attach file")
        self.file_btn.clicked.connect(self._handle_file_attach)
        input_row.addWidget(self.file_btn)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("COMMAND INPUT...")
        self.input_field.returnPressed.connect(self.handle_return_pressed)
        input_row.addWidget(self.input_field, stretch=1)
        self.send_button = QPushButton("SEND")
        self.send_button.setFixedWidth(80)
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

        self.stop_btn = QPushButton("STOP SPEECH")
        self.stop_btn.clicked.connect(self.stop_speaking)
        self.voice_panel_frame.body.addWidget(self.stop_btn)

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
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.voice_panel_frame.body.addWidget(label)
        right.addWidget(self.voice_panel_frame, stretch=2)

        self.telemetry_panel = TechPanel("SYSTEM PULSE", self.theme_mgr, indicator="LIVE")
        self.telemetry = PulseBars(self.theme_mgr)
        self.telemetry_panel.body.addWidget(self.telemetry)
        right.addWidget(self.telemetry_panel, stretch=2)

        self.mic_selector = MicSelector(self.theme_mgr)
        self.mic_selector.device_selected.connect(self.on_mic_selected)
        right.addWidget(self.mic_selector, stretch=1)

        # Cap each right-column panel's minimum so their summed minimum never
        # forces the window to grow beyond the screen height.  Stretch factors
        # distribute the actual space proportionally at runtime.
        self.models_panel_frame.setMinimumHeight(60)
        self.voice_panel_frame.setMinimumHeight(60)
        self.telemetry_panel.setMinimumHeight(60)
        self.mic_selector.setMinimumHeight(40)

        self.right_widget = QWidget()
        self.right_widget.setLayout(right)
        self.root.addWidget(self.right_widget, 1, 2)

        self.root.setColumnStretch(0, 3)
        self.root.setColumnStretch(1, 6)
        self.root.setColumnStretch(2, 3)
        self.root.setRowStretch(1, 1)

        self.theme_mgr.subscribe(self._apply_theme)
        self._apply_theme(self.theme_mgr.theme)

        # Decouple the window's minimum size from its content layout so Qt
        # never auto-resizes the window downward when bubble sizeHints grow.
        self.setMinimumSize(0, 0)

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
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        # Left zone — branding
        left_zone = QVBoxLayout()
        left_zone.setSpacing(2)
        self.title_label = QLabel("F.R.I.D.A.Y.")
        self.subtitle_label = QLabel("LOCAL INTELLIGENCE SURFACE")
        left_zone.addWidget(self.title_label)
        left_zone.addWidget(self.subtitle_label)
        layout.addLayout(left_zone, stretch=3)

        layout.addStretch(1)

        # Center zone — mini reactor + spaced name + status
        center_zone = QVBoxLayout()
        center_zone.setSpacing(2)
        center_zone.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        center_top = QHBoxLayout()
        center_top.setSpacing(8)
        center_top.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.mini_reactor = _MiniReactorIcon(self.theme_mgr)
        self.mini_reactor.setFixedSize(28, 28)
        self.center_header_label = QLabel("F · R · I · D · A · Y")
        self.center_header_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        center_top.addWidget(self.mini_reactor)
        center_top.addWidget(self.center_header_label)
        center_zone.addStretch(1)
        center_zone.addLayout(center_top)
        self.status_label = QLabel("route: idle  ·  lane: idle  ·  voice: idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_zone.addWidget(self.status_label)
        center_zone.addStretch(1)
        layout.addLayout(center_zone, stretch=4)

        layout.addStretch(1)

        # Right zone — theme toggle only (time shown in left-column clock panel)
        right_zone = QVBoxLayout()
        right_zone.setSpacing(2)
        right_zone.addStretch(1)

        right_btns = QHBoxLayout()
        right_btns.setSpacing(8)
        right_btns.addStretch(1)
        self.preflight_badge = self._build_preflight_badge()
        if self.preflight_badge is not None:
            right_btns.addWidget(self.preflight_badge)
        self.tts_btn = QPushButton()
        self.tts_btn.setFixedWidth(130)
        self.tts_btn.clicked.connect(self._toggle_tts)
        right_btns.addWidget(self.tts_btn)
        self.theme_btn = QPushButton()
        self.theme_btn.setFixedWidth(110)
        self.theme_btn.clicked.connect(self._toggle_theme)
        right_btns.addWidget(self.theme_btn)
        right_zone.addLayout(right_btns)
        layout.addLayout(right_zone, stretch=3)

        return header

    def _build_preflight_badge(self):
        """Return a small "LITE MODE" pill if optional deps are missing.

        Reads the cached preflight report captured during ``main.py`` boot.
        When all deps are present the method returns ``None`` and no widget
        is added to the header.
        """
        try:
            from core.bootstrap.preflight import last_report
        except Exception:
            return None
        report = last_report()
        if report is None or not report.degraded:
            return None
        badge = QLabel("LITE MODE")
        badge.setObjectName("preflight_badge")
        badge.setFixedHeight(22)
        badge.setStyleSheet(
            "background: #5a2a00;"
            "color: #ffb877;"
            f"font-family: {MONO_STACK};"
            "font-size: 10px;"
            "font-weight: 700;"
            "letter-spacing: 1.5px;"
            "padding: 2px 8px;"
            "border: 1px solid #ffb877;"
            "border-radius: 3px;"
        )
        missing = ", ".join(d.import_name for d in report.missing_degraded)
        tip_lines = [
            "Some optional dependencies are missing — FRIDAY is running in lite mode.",
            "",
            f"Missing: {missing}",
            "",
            "To restore full capability, activate your venv and run:",
            f"  {report.pip_install_command()}",
        ]
        badge.setToolTip("\n".join(tip_lines))
        return badge

    def _toggle_tts(self) -> None:
        muted = not getattr(self.app_core, "tts_muted", False)
        self.app_core.tts_muted = muted
        _save_tts_muted(muted)
        self._update_tts_btn_label()
        self.tts_btn.setStyleSheet(button_style(self.theme_mgr.theme, danger=muted))
        if muted and getattr(self.app_core, "tts", None):
            self.app_core.tts.stop()

    def _update_tts_btn_label(self) -> None:
        muted = getattr(self.app_core, "tts_muted", False)
        self.tts_btn.setText("TTS: OFF" if muted else "TTS: ON")

    def _toggle_theme(self) -> None:
        name = self.theme_mgr.toggle()
        _save_theme_pref(name)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(f"background-color: {theme.bg};")
        self.central.setStyleSheet(f"background-color: {theme.bg};")

        # Header — left zone
        self.title_label.setStyleSheet(
            f"color: {theme.accent};"
            f"font-family: {MONO_STACK};"
            "font-size: 26px;"
            "font-weight: 800;"
            "letter-spacing: 4px;"
            "border: none;"
            "background: transparent;"
        )
        self.subtitle_label.setStyleSheet(panel_title_style(theme))

        # Header — center zone
        self.center_header_label.setStyleSheet(
            f"color: {theme.glow};"
            f"font-family: {MONO_STACK};"
            "font-size: 13px;"
            "letter-spacing: 5px;"
            "border: none;"
            "background: transparent;"
        )
        self.status_label.setStyleSheet(label_style(theme, theme.text_dim, 10))

        # Header — right zone
        self._update_tts_btn_label()
        muted = getattr(self.app_core, "tts_muted", False)
        self.tts_btn.setStyleSheet(button_style(theme, danger=muted))
        self.theme_btn.setStyleSheet(button_style(theme))
        self.theme_btn.setText("◐  LIGHT" if theme.name == "dark" else "◑  DARK")

        # Input area
        self.input_field.setStyleSheet(text_box_style(theme, 14))
        self.update_send_button_state()
        if hasattr(self, "file_btn"):
            self.file_btn.setStyleSheet(
                f"QPushButton {{ background-color: {theme.surface_alt}; color: {theme.accent};"
                f"border: 1px solid {theme.panel_border}; border-radius: 2px;"
                "padding: 2px 0px; font-size: 17px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {theme.accent_soft}; }}"
            )
        if hasattr(self, "_attached_file_label"):
            self._attached_file_label.setStyleSheet(panel_title_style(theme))

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
        self.router_decision_ready.connect(self._on_router_decision)
        self.gemma_prediction_ready.connect(self._on_gemma_prediction)
        self.listening_mode_ready.connect(self._on_listening_mode_changed)
        self.voice_runtime_ready.connect(self._on_voice_runtime_state_changed)
        self.llm_chunk_ready.connect(self._on_llm_chunk)

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
        bus.subscribe("router_decision", lambda payload: self.router_decision_ready.emit(payload))
        bus.subscribe("gemma_prediction", lambda payload: self.gemma_prediction_ready.emit(payload))
        bus.subscribe("turn_completed", lambda payload: self.turn_finished_ready.emit(payload))
        bus.subscribe("turn_failed", lambda payload: self.turn_finished_ready.emit(payload))
        bus.subscribe("llm_chunk", lambda payload: self.llm_chunk_ready.emit(payload))
        bus.subscribe("listening_mode_changed", lambda payload: self.listening_mode_ready.emit(payload))
        bus.subscribe("voice_runtime_state_changed", lambda payload: self.voice_runtime_ready.emit(payload))
        bus.subscribe("system_shutdown", lambda _payload: self.shutdown_signal.emit())

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
            pass
        except Exception:
            pass
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

    def _on_llm_chunk(self, payload):
        # Drop chunks that arrive after the user cancelled
        if not getattr(self, "is_processing", False):
            return
        if not isinstance(payload, dict):
            return
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        if self.chat_view.streaming_bubble is None:
            lane = self._pending_lane
            self.chat_view.start_streaming_bubble(
                model_lane=lane, model_label=self._lane_label(lane)
            )
        self.chat_view.streaming_bubble.set_streaming_text(text + " ▋")
        QTimer.singleShot(0, lambda: self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        ))

    def _on_turn_started(self, payload):
        self.turn_state = "processing"
        self.is_processing = True
        self._turn_cancelled = False
        self.update_send_button_state()
        self.reactor.set_state("processing")
        self._pending_lane = None
        # Clear any stale streaming bubble from the previous turn
        self.chat_view.finalize_streaming_bubble()
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

    # Maps router_decision.source → ModelsPanel card key.
    _ROUTER_SOURCE_TO_LANE = {
        "deterministic": "tool",
        "embedding":     "tool",
        "workflow":      "tool",
        "qwen_tool":     "tool",
        "gemma_chat":    "chat",
    }

    def _on_router_decision(self, payload):
        """Show which router actually decided the live turn's tool."""
        if not isinstance(payload, dict):
            return
        source = payload.get("source", "?")
        tool   = payload.get("tool_name", "") or "—"
        self.event_stream.append("ROUTE", f"{source} -> {tool}")
        lane = self._ROUTER_SOURCE_TO_LANE.get(source)
        if lane and hasattr(self, "models_panel"):
            self.models_panel.set_active_lane(lane)

    def _on_gemma_prediction(self, payload):
        """Show the LoRA-tuned Gemma router's shadow prediction (does not
        affect live dispatch — purely visibility for A/B comparison)."""
        if not isinstance(payload, dict):
            return
        tool   = payload.get("tool_name", "") or "—"
        ms     = payload.get("latency_ms", 0.0) or 0.0
        self.event_stream.append("GEMMA", f"shadow -> {tool}  ({ms:.0f} ms)")
        if hasattr(self, "models_panel"):
            self.models_panel.set_active_lane("gemma")

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

    def _handle_file_attach(self):
        allowed = "Supported Files (*.txt *.pdf *.md *.py *.json *.csv *.docx);;All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Attach File", "", allowed)
        if not path:
            return
        self._attached_file_path = path
        name = os.path.basename(path)
        self._attached_file_label.setText(f"ATTACHED: {name}")
        self._attached_file_label.setVisible(True)
        self.event_stream.append("INFO", f"Loading {name}...")
        try:
            load_fn = getattr(self.app_core, "load_session_rag_file", None)
            if load_fn:
                msg = load_fn(path)
            else:
                msg = f"File noted: {name} (RAG loader not available)"
        except Exception as exc:
            msg = f"Failed to load {name}: {exc}"
        self.chat_view.add_message("system", msg)
        self.event_stream.append("INFO", str(msg)[:120])

    def handle_return_pressed(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        if self._attached_file_path:
            name = os.path.basename(self._attached_file_path)
            text = f"[Re: {name}] {text}"
            self._attached_file_path = None
            self._attached_file_label.setVisible(False)
        self.app_core.process_input(text, source="gui")

    def handle_send_button_clicked(self):
        if getattr(self, "is_processing", False):
            # Reset GUI state first so any in-flight llm_chunk signals are dropped
            self.turn_state = "idle"
            self.is_processing = False
            self._turn_cancelled = True  # tell render_message to ignore late responses
            self.update_send_button_state()
            self.chat_view.finalize_streaming_bubble()
            # Kill TTS and signal the background task — non-blocking, no join
            self.stop_speaking()
            runner = getattr(self.app_core, "task_runner", None)
            if runner and hasattr(runner, "cancel_nowait"):
                runner.cancel_nowait()
            else:
                # Fallback: still non-ideal but better than nothing
                self.app_core.cancel_current_task(announce=False)
            self.event_stream.append("INFO", "Task cancelled")
        # Always attempt to send whatever is in the input box (guarded against empty inside)
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
        if hasattr(self, "scan_overlay") and self.left_widget:
            self.scan_overlay.resize(self.left_widget.size())
            self.scan_overlay.raise_()
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
            text = str(payload).strip()
            lane = self._pending_lane
            if self.chat_view.streaming_bubble is not None:
                self.chat_view.streaming_bubble.set_streaming_text(text)
                self.chat_view.finalize_streaming_bubble(
                    model_lane=lane, model_label=self._lane_label(lane)
                )
            elif not getattr(self, "_turn_cancelled", False):
                self.chat_view.add_message("assistant", text, model_lane=lane, model_label=self._lane_label(lane))
            self.event_stream.append("ASSISTANT", text[:120])
            return
        text = str(payload.get("text") or "").strip()
        role = payload.get("role", "assistant")
        if not text:
            return
        lane = self._pending_lane if role == "assistant" else None
        if role == "assistant" and self.chat_view.streaming_bubble is not None:
            # Streaming bubble already has the live text — just finalise it
            self.chat_view.streaming_bubble.set_streaming_text(text)
            self.chat_view.finalize_streaming_bubble(
                model_lane=lane, model_label=self._lane_label(lane)
            )
        elif role == "assistant" and getattr(self, "_turn_cancelled", False):
            # STOP was clicked: streaming bubble already finalized with partial text.
            # Drop the late full response to avoid duplicating it in the chat.
            pass
        else:
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
