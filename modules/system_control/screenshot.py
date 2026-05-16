import glob
import io
import os
import shutil
import time
import subprocess
from urllib.parse import unquote, urlparse
from core.logger import logger


def _is_mostly_black(filepath: str) -> bool:
    """Return True if the saved PNG is essentially solid black (e.g. XWayland empty framebuffer)."""
    if os.name == "nt":
        return False
    try:
        from PIL import Image, ImageStat
        with Image.open(filepath) as img:
            return ImageStat.Stat(img.convert("L")).mean[0] < 10.0
    except Exception:
        return False


def _ensure_xwayland_env() -> bool:
    """
    On GNOME Wayland, Mutter runs an embedded XWayland server with a private
    auth cookie at /run/user/<uid>/.mutter-Xwaylandauth.*.  Set DISPLAY and
    XAUTHORITY so X11-based capture tools (mss, ImageGrab) can connect.
    Returns True if DISPLAY is usable after the call.
    """
    if os.environ.get("DISPLAY"):
        return True  # already set (X11 native or already patched)
    uid = os.getuid()
    pattern = f"/run/user/{uid}/.mutter-Xwaylandauth.*"
    matches = glob.glob(pattern)
    if matches:
        os.environ.setdefault("DISPLAY", ":0")
        os.environ.setdefault("XAUTHORITY", matches[0])
        return True
    return False


def take_screenshot():
    """
    Takes a full-screen screenshot on Linux (Wayland or X11) or Windows.

    Priority:
      0. mss via XWayland   (fastest — works on GNOME Wayland via embedded XWayland)
      1. Mutter ScreenCast + PipeWire  (GNOME Wayland native, no dialog)
      1b. GNOME Shell D-Bus via gdbus CLI (no gi dependency)
      2. xdg-desktop-portal  (interactive=False — no dialog)
      3. GNOME Shell D-Bus via PyGObject
      4. gnome-screenshot adapter  (watches ~/Pictures/Screenshots/)
      5. grim                (wlroots compositors: sway, Hyprland)
      6. spectacle           (KDE Plasma)
      7. generic X11 tools   (xfce4-screenshooter, maim, scrot, import)
      8. pyautogui           (X11/Windows fallback)
    """
    save_dir = os.path.expanduser("~/Pictures/FRIDAY_Screenshots")
    os.makedirs(save_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(save_dir, f"screenshot_{timestamp}.png")

    errors = []

    if os.name != "nt":
        is_wayland = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
            os.environ.get("WAYLAND_DISPLAY")
        )

        # 0. mss via XWayland — instant, X11 only (Wayland framebuffer is black)
        if not is_wayland:
            _ensure_xwayland_env()
            try:
                import mss
                import mss.tools
                with mss.MSS() as sct:
                    monitor = sct.monitors[1]
                    raw = sct.grab(monitor)
                    png_bytes = mss.tools.to_png(raw.rgb, raw.size)
                    with open(filepath, "wb") as f:
                        f.write(png_bytes)
                if (os.path.exists(filepath) and os.path.getsize(filepath) > 0
                        and not _is_mostly_black(filepath)):
                    logger.info(f"Screenshot taken via mss/XWayland: {filepath}")
                    return f"Screenshot saved successfully at: {filepath}"
            except Exception as e:
                errors.append(f"mss: {e}")

        if is_wayland:
            # 1. Mutter ScreenCast + PipeWire — confirmed working on GNOME Wayland, no dialog
            err = _take_screenshot_via_mutter_screencast(filepath)
            if err is None:
                logger.info(f"Screenshot taken via Mutter ScreenCast: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"mutter-screencast: {err}")

            # 1b. GNOME Shell D-Bus via gdbus CLI — no gi/PyGObject dependency
            err = _take_screenshot_via_gdbus_shell(filepath)
            if err is None:
                logger.info(f"Screenshot taken via gdbus GNOME Shell: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"gdbus-shell: {err}")

            # 2. xdg-desktop-portal (non-interactive full-screen)
            err = _take_screenshot_via_portal(filepath, interactive=False)
            if err is None:
                logger.info(f"Screenshot taken via xdg-desktop-portal: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"xdg-desktop-portal: {err}")

            # 3. GNOME Shell D-Bus via PyGObject (if gi is available)
            err = _take_screenshot_via_gnome_shell(filepath)
            if err is None:
                logger.info(f"Screenshot taken via GNOME Shell D-Bus: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
            errors.append(f"gnome-shell-dbus: {err}")

            # 4. gnome-screenshot adapter (GNOME 43+ ignores -f; watch for new file)
            if shutil.which("gnome-screenshot"):
                err = _take_screenshot_via_gnome_adapter(filepath)
                if err is None:
                    logger.info(f"Screenshot taken via gnome-screenshot adapter: {filepath}")
                    return f"Screenshot saved successfully at: {filepath}"
                errors.append(f"gnome-screenshot-adapter: {err}")

            # 4. grim (wlroots Wayland: sway, Hyprland)
            if shutil.which("grim"):
                try:
                    result = subprocess.run(["grim", filepath], capture_output=True)
                    if result.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        logger.info(f"Screenshot taken via grim: {filepath}")
                        return f"Screenshot saved successfully at: {filepath}"
                    errors.append(f"grim: {result.stderr.decode(errors='ignore').strip()}")
                except Exception as e:
                    errors.append(f"grim: {e}")

            # 5. spectacle (KDE Plasma)
            if shutil.which("spectacle"):
                try:
                    result = subprocess.run(["spectacle", "-b", "-n", "-o", filepath], capture_output=True)
                    if result.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        logger.info(f"Screenshot taken via spectacle: {filepath}")
                        return f"Screenshot saved successfully at: {filepath}"
                    errors.append(f"spectacle: {result.stderr.decode(errors='ignore').strip()}")
                except Exception as e:
                    errors.append(f"spectacle: {e}")

        # 6. Generic X11 tools (also tried on non-Wayland)
        for command in (
            ["xfce4-screenshooter", "-f", "-s", filepath],
            ["maim", filepath],
            ["scrot", filepath],
            ["import", "-window", "root", filepath],
        ):
            executable = command[0]
            if not shutil.which(executable):
                continue
            try:
                result = subprocess.run(command, capture_output=True)
                if result.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    logger.info(f"Screenshot taken via {executable}: {filepath}")
                    return f"Screenshot saved successfully at: {filepath}"
                errors.append(f"{executable}: {result.stderr.decode(errors='ignore').strip()}")
            except Exception as e:
                errors.append(f"{executable}: {e}")

    # 7. pyautogui (X11 / Windows)
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        logger.info(f"Screenshot taken via pyautogui: {filepath}")
        return f"Screenshot saved successfully at: {filepath}"
    except Exception as e:
        errors.append(f"pyautogui: {e}")

    details = "; ".join(err for err in errors if err)
    err_msg = (
        "Failed to take screenshot. "
        f"Details: {details}. "
        "On GNOME Wayland, ensure xdg-desktop-portal-gnome is running."
    )
    logger.error(err_msg)
    return err_msg


def _take_screenshot_via_mutter_screencast(filepath):
    """
    Uses org.gnome.Mutter.ScreenCast + PipeWire + GStreamer to take a
    full-screen screenshot on GNOME Wayland without any permission dialog.
    Works on GNOME Shell 43+ (any Mutter-based compositor).
    Returns None on success, error string on failure.
    """
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gio, GLib, Gst
        Gst.init(None)
    except Exception as exc:
        return f"GStreamer unavailable: {exc}"

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        connector = 'eDP-1'
        try:
            dc = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None,
                'org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                'org.gnome.Mutter.DisplayConfig', None)
            _, monitors, _, _ = dc.call_sync('GetCurrentState', None,
                Gio.DBusCallFlags.NONE, 5000, None).unpack()
            if monitors:
                connector = monitors[0][0][0]
        except Exception:
            pass

        sc = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast', '/org/gnome/Mutter/ScreenCast',
            'org.gnome.Mutter.ScreenCast', None)
        sess_path = sc.call_sync('CreateSession',
            GLib.Variant('(a{sv})', ({},)),
            Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        sess = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast', sess_path,
            'org.gnome.Mutter.ScreenCast.Session', None)
        stream_path = sess.call_sync('RecordMonitor',
            GLib.Variant('(sa{sv})', (connector, {})),
            Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        stream_proxy = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast', stream_path,
            'org.gnome.Mutter.ScreenCast.Stream', None)

        result = {'error': 'PipeWireStreamAdded signal not received'}
        loop = GLib.MainLoop()

        def on_signal(_proxy, _sender, signal_name, params):
            if signal_name != 'PipeWireStreamAdded':
                return
            node_id = params.unpack()[0]
            try:
                pipeline = Gst.parse_launch(
                    f'pipewiresrc path={node_id} num-buffers=1 ! '
                    f'videoconvert ! pngenc ! filesink location={filepath}'
                )

                def on_msg(_bus, msg):
                    t = msg.type
                    if t == Gst.MessageType.ERROR:
                        err, _ = msg.parse_error()
                        result['error'] = f'GStreamer: {err}'
                        pipeline.set_state(Gst.State.NULL)
                        loop.quit()
                    elif t == Gst.MessageType.EOS:
                        result['error'] = None
                        pipeline.set_state(Gst.State.NULL)
                        loop.quit()

                gst_bus = pipeline.get_bus()
                gst_bus.add_signal_watch()
                gst_bus.connect('message', on_msg)
                pipeline.set_state(Gst.State.PLAYING)
            except Exception as exc:
                result['error'] = str(exc)
                loop.quit()

        stream_proxy.connect('g-signal', on_signal)
        sess.call_sync('Start', None, Gio.DBusCallFlags.NONE, 5000, None)
        GLib.timeout_add(15000, lambda: (loop.quit(), False)[1])
        loop.run()

        try:
            sess.call_sync('Stop', None, Gio.DBusCallFlags.NONE, 3000, None)
        except Exception:
            pass

        if result['error']:
            return result['error']
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return 'output file missing after capture'
        return None
    except Exception as exc:
        return str(exc)


def _take_screenshot_via_gdbus_shell(filepath):
    """
    Call org.gnome.Shell.Screenshot via gdbus CLI — no gi/PyGObject required.
    Works from within a running GNOME session (same as the gi variant).
    Returns None on success, error string on failure.
    """
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return "gdbus not found"
    try:
        result = subprocess.run(
            [
                gdbus, "call", "--session",
                "--dest", "org.gnome.Shell.Screenshot",
                "--object-path", "/org/gnome/Shell/Screenshot",
                "--method", "org.gnome.Shell.Screenshot.Screenshot",
                "false", "false", filepath,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return None
        stderr = (result.stderr or result.stdout or "").strip()
        return stderr or "gdbus: screenshot file not created"
    except subprocess.TimeoutExpired:
        return "gdbus: timed out"
    except Exception as exc:
        return str(exc)


def _take_screenshot_via_gnome_shell(filepath):
    """
    Call org.gnome.Shell.Screenshot D-Bus method directly.
    Works only when called from within a running GNOME session process.
    Returns None on success, error string on failure.
    """
    try:
        from gi.repository import Gio, GLib
    except Exception as exc:
        return f"PyGObject unavailable: {exc}"
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            "org.gnome.Shell.Screenshot",
            "/org/gnome/Shell/Screenshot",
            "org.gnome.Shell.Screenshot",
            None,
        )
        result = proxy.call_sync(
            "Screenshot",
            GLib.Variant("(bbs)", (False, False, filepath)),
            Gio.DBusCallFlags.NONE,
            10000,
            None,
        )
        success, used_path = result.unpack()
        if not success:
            return "GNOME Shell Screenshot returned failure"
        if used_path and used_path != filepath:
            shutil.copyfile(used_path, filepath)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return None
        return "GNOME Shell Screenshot: file missing after call"
    except Exception as exc:
        return str(exc)


def _take_screenshot_via_gnome_adapter(filepath, timeout=25.0):
    """
    Workaround for GNOME 43+ where gnome-screenshot ignores the -f flag and
    always saves to ~/Pictures/Screenshots/.  We watch that directory for the
    new file and copy it to the requested filepath.
    Returns None on success, error string on failure.
    """
    screenshots_dir = os.path.expanduser("~/Pictures/Screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    existing = set(glob.glob(os.path.join(screenshots_dir, "*.png")))

    # Inherit the session environment and fix locale to avoid Gtk warnings that
    # slow down gnome-screenshot on some GNOME setups.
    env = os.environ.copy()
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")

    try:
        proc = subprocess.Popen(
            ["gnome-screenshot"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except Exception as exc:
        return str(exc)

    deadline = time.monotonic() + timeout
    new_file = None
    while time.monotonic() < deadline:
        current = set(glob.glob(os.path.join(screenshots_dir, "*.png")))
        new_files = current - existing
        if new_files:
            time.sleep(0.3)  # let the write finish
            new_file = max(new_files, key=os.path.getmtime)
            break
        time.sleep(0.3)

    try:
        proc.wait(timeout=1)
    except Exception:
        proc.kill()

    if not new_file or not os.path.exists(new_file) or os.path.getsize(new_file) == 0:
        return "gnome-screenshot: no new file appeared in ~/Pictures/Screenshots/"

    shutil.copy2(new_file, filepath)
    return None


def _take_screenshot_via_portal(filepath, timeout_seconds=15, interactive=False):
    """
    Capture through xdg-desktop-portal.
    Returns None on success, otherwise a short error string.
    """
    try:
        from gi.repository import Gio, GLib
    except Exception as exc:
        return f"PyGObject unavailable: {exc}"

    response = {"done": False, "error": "portal did not respond", "uri": ""}
    timeout_ref = {"id": None}

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            None,
        )
        token = f"friday_{os.getpid()}_{int(time.time() * 1000)}"
        handle_path = _portal_request_path(bus.get_unique_name(), token)
        loop = GLib.MainLoop()

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
            None, None,
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

        timeout_ref["id"] = GLib.timeout_add_seconds(timeout_seconds, on_timeout)
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
