import os
import sys


def register():
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
    clap_detector = os.path.join(SCRIPT_DIR, "clap_detector.py")
    venv_python = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")

    AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
    DESKTOP_FILE = os.path.join(AUTOSTART_DIR, "friday_clap.desktop")

    if not os.path.exists(venv_python):
        print(f"Error: Virtual environment not found at {venv_python}")
        return False

    os.makedirs(AUTOSTART_DIR, exist_ok=True)

    content = f"""[Desktop Entry]
Type=Application
Path={PROJECT_ROOT}
TryExec={venv_python}
Exec={venv_python} {clap_detector} --start
Hidden=false
NoDisplay=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
X-GNOME-Autostart-Phase=Application
Name=Friday Clap Detector
Comment=Starts Friday on double clap
Icon=utilities-terminal
Terminal=false
Categories=Utility;
"""

    try:
        with open(DESKTOP_FILE, "w") as f:
            f.write(content)
        os.chmod(DESKTOP_FILE, 0o755)
        print(f"Successfully registered autostart at: {DESKTOP_FILE}")
        return True
    except Exception as e:
        print(f"Failed to register autostart: {e}")
        return False

def unregister():
    AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
    DESKTOP_FILE = os.path.join(AUTOSTART_DIR, "friday_clap.desktop")
    
    if os.path.exists(DESKTOP_FILE):
        try:
            os.remove(DESKTOP_FILE)
            print(f"Successfully removed autostart: {DESKTOP_FILE}")
            return True
        except Exception as e:
            print(f"Failed to remove autostart: {e}")
            return False
    else:
        print("Autostart file not found.")
        return True


if __name__ == "__main__":
    register()
