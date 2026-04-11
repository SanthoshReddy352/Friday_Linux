import sys
import os

# Adjust sys.path to load local dependencies from 'libs' due to NTFS execution restrictions
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LIBS_DIR = os.path.join(CURRENT_DIR, 'libs')
if os.path.exists(LIBS_DIR) and LIBS_DIR not in sys.path:
    # Insert at position 1 (after current directory) so they take precedence over system packages,
    # but local project files still take top priority.
    sys.path.insert(1, LIBS_DIR)

from core.app import FridayApp
from gui.main_window import start_gui

def main():
    # 1. Initialize core system (config, logger, plugin manager, etc.)
    app = FridayApp()
    app.initialize()

    # 2. Start the GUI event loop
    start_gui(app)

if __name__ == '__main__':
    main()
