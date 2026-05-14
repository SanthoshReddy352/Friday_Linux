import argparse
import logging
import signal

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
    parser.add_argument("--agent-hud", action="store_true", help="Use the new Agent HUD (gui/agent_hud.py) instead of the classic HUD.")
    parser.add_argument("--verbose", action="store_true", help="Show startup and runtime logs in the terminal.")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    set_console_logging(enabled=True, level=log_level)

    # Phase 6 (v2): RuntimeKernel.boot() owns service construction.
    # The underlying FridayApp is reachable via `kernel.app` so the CLI,
    # HUD, and existing extensions need no changes.
    kernel = RuntimeKernel.boot()
    _install_signal_handlers(kernel)
    kernel.initialize()
    app = kernel.app

    import time
    time.sleep(2.5)
    greeter = app.extension_loader.get_extension("Greeter")
    if greeter:
        greeting = greeter.handle_startup()
        app.event_bus.publish("voice_response", greeting)

    if args.text:
        start_cli(app)
        return

    if args.agent_hud:
        from gui.agent_hud import start_hud
    else:
        from gui.hud import start_hud
    start_hud(app)


if __name__ == "__main__":
    main()
