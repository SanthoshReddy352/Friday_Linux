"""AwarenessService — background screen capture + OCR loop.

Mirrors jarvis src/awareness/service.ts.

The service runs a daemon thread that:
  1. Takes a screenshot every capture_interval_s seconds.
  2. Runs OCR (pytesseract) on the captured image.
  3. Queries StruggleDetector with the OCR text.
  4. If struggle detected: publishes 'awareness_struggle' to EventBus.

The capture loop uses FRIDAY's existing screenshot.py so Wayland/X11 fallbacks
work without duplication.

Config keys (config.yaml):
  awareness:
    enabled: false          # MUST be explicitly enabled — off by default
    capture_interval_s: 10  # seconds between captures
    ocr_enabled: true
    retention_minutes: 60   # how long captures stay in memory

Privacy note: no captures are sent to any network. OCR runs fully locally
via pytesseract + Tesseract. Screen data is ephemeral (not persisted to disk).
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from dataclasses import dataclass, field

from core.logger import logger
from .struggle_detector import StruggleDetector


@dataclass
class CaptureRecord:
    ts: float
    ocr_text: str
    window_title: str
    struggle_score: float = 0.0


class AwarenessService:
    def __init__(self, event_bus, config=None):
        self._bus = event_bus
        self._config = config
        self._running = False
        self._thread: threading.Thread | None = None
        self._detector = StruggleDetector(event_bus)
        self._captures: list[CaptureRecord] = []
        self._lock = threading.RLock()

        self._enabled = self._cfg("awareness.enabled", False)
        self._interval_s = float(self._cfg("awareness.capture_interval_s", 10))
        self._ocr_enabled = bool(self._cfg("awareness.ocr_enabled", True))
        self._retention_s = float(self._cfg("awareness.retention_minutes", 60)) * 60

    def _cfg(self, key: str, default):
        if self._config and hasattr(self._config, "get"):
            val = self._config.get(key, None)
            if val is not None:
                return val
        return default

    def start(self) -> bool:
        if not self._enabled:
            logger.info("[Awareness] disabled — set awareness.enabled=true in config to opt in")
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="awareness-capture"
        )
        self._thread.start()
        logger.info(
            "[Awareness] started (interval=%.0fs, ocr=%s)",
            self._interval_s, self._ocr_enabled,
        )
        return True

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.debug("[Awareness] tick error: %s", exc)
            time.sleep(self._interval_s)

    def _tick(self) -> None:
        ocr_text = ""
        window_title = ""

        # Get active window title via platform adapter (best-effort)
        try:
            from modules.system_control.adapters import get_adapter
            app_name, window_title = get_adapter().get_active_window()
        except Exception:
            pass

        # Take screenshot
        tmp_path = None
        if self._ocr_enabled:
            try:
                from modules.system_control.screenshot import take_screenshot
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False, prefix="friday_awareness_"
                ) as f:
                    tmp_path = f.name
                take_screenshot(output_path=tmp_path)
                ocr_text = self._run_ocr(tmp_path)
            except Exception as exc:
                logger.debug("[Awareness] screenshot/OCR failed: %s", exc)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        record = CaptureRecord(
            ts=time.monotonic(),
            ocr_text=ocr_text,
            window_title=window_title,
        )

        struggle = self._detector.push(ocr_text, window_title)
        if struggle:
            record.struggle_score = struggle["score"]
            logger.info("[Awareness] struggle detected (score=%.2f) in '%s'",
                        struggle["score"], window_title[:60])
            self._bus.publish("awareness_struggle", {
                "score": struggle["score"],
                "signals": struggle["signals"],
                "window_title": window_title,
                "suggestion": self._build_suggestion(window_title),
            })

        with self._lock:
            self._captures.append(record)
            # Prune old captures
            cutoff = time.monotonic() - self._retention_s
            self._captures = [c for c in self._captures if c.ts >= cutoff]

    def _run_ocr(self, image_path: str) -> str:
        try:
            import pytesseract
            from PIL import Image
            with Image.open(image_path) as img:
                text = pytesseract.image_to_string(img, timeout=5)
            return (text or "").strip()
        except ImportError:
            logger.debug(
                "[Awareness] pytesseract not installed — OCR disabled. "
                "Install: pip install pytesseract && sudo apt install tesseract-ocr"
            )
            return ""
        except Exception as exc:
            logger.debug("[Awareness] OCR error: %s", exc)
            return ""

    def _build_suggestion(self, window_title: str) -> str:
        if window_title:
            return (
                f"You've been in '{window_title}' for a while and seem stuck. "
                "Want me to help?"
            )
        return "You seem to be struggling. Want me to help?"

    def recent_captures(self, limit: int = 10) -> list[dict]:
        with self._lock:
            return [
                {
                    "window_title": c.window_title,
                    "has_ocr": bool(c.ocr_text),
                    "struggle_score": c.struggle_score,
                }
                for c in self._captures[-limit:]
            ]
