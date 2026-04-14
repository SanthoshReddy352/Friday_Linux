import argparse
import sys
import os
import logging

# Adjust sys.path to load local dependencies from 'libs' due to NTFS execution restrictions
# (DEPRECATED: We now use a virtual environment for better dependency management)
# CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# LIBS_DIR = os.path.join(CURRENT_DIR, 'libs')
# if os.path.exists(LIBS_DIR) and LIBS_DIR not in sys.path:
#     # Insert at position 1 (after current directory) so they take precedence over system packages,
#     # but local project files still take top priority.
#     sys.path.insert(1, LIBS_DIR)

from core.app import FridayApp
from core.logger import set_console_logging
from cli import start_cli
from gui.hud import start_hud

def main():
    parser = argparse.ArgumentParser(description="Run the FRIDAY local assistant.")
    parser.add_argument("--text", action="store_true", help="Launch the text-only terminal UI instead of the desktop GUI.")
    parser.add_argument("--gui", action="store_true", help="Launch the desktop HUD explicitly.")
    parser.add_argument("--verbose", action="store_true", help="Show startup and runtime logs in the terminal.")
    args = parser.parse_args()

    # Default to INFO logs in terminal unless --verbose is used for DEBUG
    log_level = logging.DEBUG if args.verbose else logging.INFO
    set_console_logging(enabled=True, level=log_level)

    # 1. Initialize core system (config, logger, plugin manager, etc.)
    app = FridayApp()
    app.initialize()

    # Trigger startup greeting after a slight delay to let hardware settle
    import time
    time.sleep(2.5) 
    greeter = next((p for p in app.plugin_manager.plugins if p.name == "Greeter"), None)
    if greeter:
        greeting = greeter.handle_startup()
        app.event_bus.publish("voice_response", greeting)

    # 2. Start the requested interface
    if args.text:
        start_cli(app)
        return
    start_hud(app)

if __name__ == '__main__':
    main()
