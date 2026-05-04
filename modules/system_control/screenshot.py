import os
import time
import subprocess
import shutil
from urllib.parse import unquote, urlparse
from core.logger import logger

def take_screenshot():
    """
    Takes a screenshot of the primary display.
    Includes fallbacks for Wayland (gnome-screenshot) where pyautogui fails.
    """
    save_dir = os.path.expanduser("~/Pictures/FRIDAY_Screenshots")
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    filepath = os.path.join(save_dir, filename)
    
    errors = []

    if os.name != 'nt' and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        portal_error = _take_screenshot_via_portal(filepath, interactive=True)
        if portal_error is None:
            logger.info(f"Screenshot taken via xdg-desktop-portal: {filepath}")
            return f"Screenshot saved successfully at: {filepath}"
        errors.append(f"xdg-desktop-portal: {portal_error}")

    # Try GNOME screenshot first on Linux if available (best for Wayland compatibility)
    if os.name != 'nt' and shutil.which("gnome-screenshot"):
        try:
            result = subprocess.run(["gnome-screenshot", "-f", filepath], capture_output=True)
            if result.returncode == 0:
                logger.info(f"Screenshot taken via gnome-screenshot: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"gnome-screenshot: {result.stderr.decode(errors='ignore').strip()}")
        except Exception as e:
            logger.warning(f"gnome-screenshot failed: {e}")
            errors.append(f"gnome-screenshot: {e}")
            
    # Try grim (common on non-GNOME Wayland like Sway/Hyperland)
    if os.name != 'nt' and shutil.which("grim"):
        try:
            result = subprocess.run(["grim", filepath], capture_output=True)
            if result.returncode == 0:
                logger.info(f"Screenshot taken via grim: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"grim: {result.stderr.decode(errors='ignore').strip()}")
        except Exception as e:
            logger.warning(f"grim failed: {e}")
            errors.append(f"grim: {e}")

    # KDE Plasma's native tool. Works better than pyautogui on many Wayland desktops.
    if os.name != 'nt' and shutil.which("spectacle"):
        try:
            result = subprocess.run(["spectacle", "-b", "-n", "-o", filepath], capture_output=True)
            if result.returncode == 0 and os.path.exists(filepath):
                logger.info(f"Screenshot taken via spectacle: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"spectacle: {result.stderr.decode(errors='ignore').strip()}")
        except Exception as e:
            logger.warning(f"spectacle failed: {e}")
            errors.append(f"spectacle: {e}")

    for command in (
        ["xfce4-screenshooter", "-f", "-s", filepath],
        ["maim", filepath],
        ["scrot", filepath],
        ["import", "-window", "root", filepath],
    ):
        executable = command[0]
        if os.name == 'nt' or not shutil.which(executable):
            continue
        try:
            result = subprocess.run(command, capture_output=True)
            if result.returncode == 0 and os.path.exists(filepath):
                logger.info(f"Screenshot taken via {executable}: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"{executable}: {result.stderr.decode(errors='ignore').strip()}")
        except Exception as e:
            logger.warning(f"{executable} failed: {e}")
            errors.append(f"{executable}: {e}")

    # Fallback to pyautogui for X11/Windows
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        logger.info(f"Screenshot taken via pyautogui: {filepath}")
        return f"Screenshot saved successfully at: {filepath}"
    except Exception as e:
        errors.append(f"pyautogui: {e}")
        details = "; ".join(part for part in errors if part and not part.endswith(": ")) or str(e)
        err_msg = (
            "Failed to take screenshot with all methods. "
            f"Details: {details}. "
            "On Linux Wayland, install gnome-screenshot, spectacle, grim, or grant screenshot portal permission."
        )
        logger.error(err_msg)
        return err_msg


def _take_screenshot_via_portal(filepath, timeout_seconds=15, interactive=True):
    """
    Capture through xdg-desktop-portal. This is the safest Wayland fallback when
    the compositor blocks direct screencopy protocols used by tools like grim.
    Returns None on success, otherwise a short error string.
    """
    try:
        from gi.repository import Gio, GLib
    except Exception as exc:
        return f"PyGObject unavailable: {exc}"

    loop = None
    subscription_id = None
    timeout_id = None
    response = {"done": False, "error": "portal did not respond", "uri": ""}

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            None,
        )
        token = f"friday_{os.getpid()}_{int(time.time() * 1000)}"
        handle_path = _portal_request_path(bus.get_unique_name(), token)
        loop = GLib.MainLoop()
        timeout_ref = {"id": None}

        def on_response(_connection, _sender, object_path, _interface, _signal, parameters):
            if object_path != handle_path:
                return
            code, results = parameters.unpack()
            if code != 0:
                response["error"] = f"portal request cancelled or denied (code {code})"
            else:
                uri_value = results.get("uri", "")
                if hasattr(uri_value, "unpack"):
                    uri_value = uri_value.unpack()
                response["uri"] = str(uri_value or "")
                response["error"] = "" if response["uri"] else "portal returned no image URI"
            response["done"] = True
            loop.quit()

        subscription_id = bus.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Request",
            "Response",
            None,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
        )

        def on_timeout():
            timeout_ref["id"] = None
            response["done"] = True
            response["error"] = "portal request timed out"
            loop.quit()
            return False

        options = {
            "handle_token": GLib.Variant("s", token),
            "interactive": GLib.Variant("b", bool(interactive)),
        }
        result = proxy.call_sync(
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            Gio.DBusCallFlags.NONE,
            timeout_seconds * 1000,
            None,
        )
        returned_handle = result.unpack()[0]
        if returned_handle != handle_path:
            handle_path = returned_handle

        timeout_id = GLib.timeout_add_seconds(timeout_seconds, on_timeout)
        timeout_ref["id"] = timeout_id
        loop.run()
        if response["error"]:
            return response["error"]
        return _copy_portal_uri(response["uri"], filepath)
    except Exception as exc:
        return str(exc)
    finally:
        try:
            if timeout_ref.get("id") is not None:
                GLib.source_remove(timeout_ref["id"])
        except Exception:
            pass
        try:
            if subscription_id is not None:
                bus.signal_unsubscribe(subscription_id)
        except Exception:
            pass


def _portal_request_path(unique_name, token):
    sender = str(unique_name or "").lstrip(":").replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"


def _copy_portal_uri(uri, filepath):
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return f"unsupported portal URI: {uri}"
    source_path = unquote(parsed.path)
    if not os.path.exists(source_path):
        return f"portal image not found: {source_path}"
    if os.path.abspath(source_path) != os.path.abspath(filepath):
        shutil.copyfile(source_path, filepath)
    return None
