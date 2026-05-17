# Project-venv auto-bootstrap — must run BEFORE any heavy import so it
# can re-exec under the venv interpreter without first importing modules
# that need pip dependencies. Keep this block stdlib-only.
def _relaunch_under_project_venv() -> None:
    """If a project `.venv/` exists and we aren't running inside it,
    re-execute the script under the venv's interpreter.

    Detection compares ``sys.prefix`` (the active interpreter's prefix
    root, set by Python's venv machinery on launch) against the project
    ``.venv`` path — *not* ``sys.executable``, because venv pythons are
    often symlinks back to the system Python and the executable paths
    match while the import path doesn't.

    Saves the user from "I forgot to ``source .venv/bin/activate``"
    boot failures — they can launch FRIDAY with ``python main.py`` from
    any shell and the venv's packages will be used automatically.

    Set ``FRIDAY_SKIP_VENV_AUTOEXEC=1`` to opt out (e.g. when running
    under an alternate venv on purpose).
    """
    import os
    import sys

    if os.environ.get("FRIDAY_SKIP_VENV_AUTOEXEC") == "1":
        return
    here = os.path.dirname(os.path.abspath(__file__))
    venv_root = os.path.join(here, ".venv")
    if os.name == "nt":
        candidate = os.path.join(venv_root, "Scripts", "python.exe")
    else:
        candidate = os.path.join(venv_root, "bin", "python3")
        if not os.path.exists(candidate):
            candidate = os.path.join(venv_root, "bin", "python")
    if not os.path.exists(candidate):
        return
    # Compare on ``sys.prefix``: when Python is launched via the venv's
    # interpreter, ``sys.prefix`` points at the venv root. When launched
    # via the system interpreter, it points at the system install — even
    # if ``sys.executable`` happens to be the same file via a symlink.
    try:
        already_in_venv = (
            os.path.realpath(sys.prefix) == os.path.realpath(venv_root)
        )
    except OSError:
        already_in_venv = False
    if already_in_venv:
        return
    # Break any infinite loop if the exec target somehow doesn't actually
    # set sys.prefix to the venv (broken venv, weird symlink, etc.).
    if os.environ.get("_FRIDAY_VENV_RELAUNCHED") == "1":
        return
    os.environ["_FRIDAY_VENV_RELAUNCHED"] = "1"
    os.execv(candidate, [candidate, *sys.argv])


_relaunch_under_project_venv()

# Load .env before any module that reads os.environ (tokens, API keys, etc.)
try:
    import os as _os
    from dotenv import load_dotenv as _load_dotenv
    _dot_env = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
    if _os.path.exists(_dot_env):
        _load_dotenv(_dot_env, override=False)  # shell env takes precedence over .env
except ImportError:
    pass

import argparse
import logging
import signal

from core.bootstrap.preflight import ensure_runnable
from core.kernel import RuntimeKernel
from core.logger import set_console_logging
from cli import start_cli


def _install_signal_handlers(kernel: RuntimeKernel) -> None:
    """Route SIGINT / SIGTERM to kernel.shutdown() for clean exit.

    On SIGINT (Ctrl-C) Python normally raises KeyboardInterrupt in the main
    thread. For GUI mode Qt swallows it, so the signal handler is the only
    reliable hook. For CLI mode it gives a clean "goodbye" instead of a
    traceback.
    """

    def _handler(signum, frame):
        sig_name = signal.Signals(signum).name
        print(f"\n[main] Received {sig_name} — shutting down…", flush=True)
        kernel.shutdown()

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (AttributeError, OSError):
        # SIGTERM not available on all platforms (e.g. Windows)
        pass


def main():
    parser = argparse.ArgumentParser(description="Run the FRIDAY local assistant.")
    parser.add_argument("--text", action="store_true", help="Launch the text-only terminal UI instead of the desktop GUI.")
    parser.add_argument("--gui", action="store_true", help="Launch the desktop HUD explicitly.")
    parser.add_argument("--verbose", action="store_true", help="Show startup and runtime logs in the terminal.")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    set_console_logging(enabled=True, level=log_level)

    # Fail fast on missing critical deps; surface degraded warnings before
    # we sink any time into model load. The returned report is cached on
    # the preflight module so the HUD can query it later.
    ensure_runnable()

    # Phase 6 (v2): RuntimeKernel.boot() owns service construction.
    # The underlying FridayApp is reachable via `kernel.app` so the CLI,
    # HUD, and existing extensions need no changes.
    kernel = RuntimeKernel.boot()
    _install_signal_handlers(kernel)
    kernel.initialize()
    app = kernel.app

    # Restore persisted TTS mute preference before the greeter speaks so
    # that "TTS: OFF" at shutdown is honoured on the very first utterance.
    import json as _json, os as _os
    _gui_state_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "gui_state.json")
    try:
        with open(_gui_state_path, "r", encoding="utf-8") as _fh:
            app.tts_muted = bool((_json.load(_fh) or {}).get("tts_muted", False))
    except Exception:
        app.tts_muted = False

    import time
    time.sleep(2.5)
    greeter = app.extension_loader.get_extension("Greeter")
    if greeter:
        greeting = greeter.handle_startup()
        app.event_bus.publish("voice_response", greeting)

    if args.text:
        start_cli(app)
        return

    from gui.hud import start_hud
    start_hud(app)


if __name__ == "__main__":
    main()
