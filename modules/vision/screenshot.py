"""Screen capture and clipboard image utilities.

Capture priority on Wayland:
  1. mss              — X11 / Xwayland (fast, cross-platform)
  2. xdg-desktop-portal — non-interactive full-screen (GNOME, KDE, …)
  3. GNOME Shell D-Bus  — org.gnome.Shell.Screenshot (works from GUI apps)
  4. gnome-screenshot adapter — watches ~/Pictures/Screenshots/ for new file
  5. PIL.ImageGrab     — X11 last resort
"""
from __future__ import annotations

import glob
import io
import os

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _ensure_xwayland_env() -> None:
    """Set DISPLAY + XAUTHORITY for Mutter's embedded XWayland if not already set."""
    if os.environ.get("DISPLAY"):
        return
    uid = os.getuid()
    matches = glob.glob(f"/run/user/{uid}/.mutter-Xwaylandauth.*")
    if matches:
        os.environ.setdefault("DISPLAY", ":0")
        os.environ.setdefault("XAUTHORITY", matches[0])


def take_screenshot() -> "Image.Image":
    """Capture the primary monitor and return a PIL RGB Image."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is not installed. Run: pip install Pillow")

    # 1. mss via XWayland — instant, works on GNOME Wayland
    if _MSS_AVAILABLE:
        _ensure_xwayland_env()
        try:
            with mss.MSS() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                png_bytes = mss.tools.to_png(raw.rgb, raw.size)
                return Image.open(io.BytesIO(png_bytes)).convert("RGB")
        except Exception:
            pass

    is_wayland = (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )

    if is_wayland:
        import tempfile
        from modules.system_control.screenshot import (
            _take_screenshot_via_mutter_screencast,
            _take_screenshot_via_gdbus_shell,
            _take_screenshot_via_portal,
            _take_screenshot_via_gnome_shell,
            _take_screenshot_via_gnome_adapter,
        )

        def _try_method(fn, *args):
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            try:
                err = fn(tmp.name, *args)
                if err is None and os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
                    return Image.open(tmp.name).convert("RGB")
            except Exception:
                pass
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            return None

        # 2. Mutter ScreenCast + PipeWire — no dialog, confirmed on GNOME Wayland
        img = _try_method(_take_screenshot_via_mutter_screencast)
        if img is not None:
            return img

        # 2b. GNOME Shell D-Bus via gdbus CLI — no gi/PyGObject required
        img = _try_method(_take_screenshot_via_gdbus_shell)
        if img is not None:
            return img

        # 3. xdg-desktop-portal (non-interactive)
        img = _try_method(lambda p: _take_screenshot_via_portal(p, interactive=False))
        if img is not None:
            return img

        # 4. GNOME Shell D-Bus via PyGObject
        img = _try_method(_take_screenshot_via_gnome_shell)
        if img is not None:
            return img

        # 5. gnome-screenshot adapter
        import shutil
        if shutil.which("gnome-screenshot"):
            img = _try_method(_take_screenshot_via_gnome_adapter)
            if img is not None:
                return img

    # 5. PIL.ImageGrab — X11 last resort
    try:
        img = ImageGrab.grab()
        if img is not None:
            return img.convert("RGB")
    except Exception:
        pass

    raise RuntimeError(
        "Screenshot failed on Wayland. "
        "Ensure xdg-desktop-portal-gnome is installed and running, "
        "or install grim for wlroots compositors."
    )


def get_clipboard_image() -> "Image.Image | None":
    """Return the image currently on the clipboard, or None if no image is copied."""
    if not _PIL_AVAILABLE:
        return None
    try:
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            return img.convert("RGB")
    except Exception:
        pass
    return None
