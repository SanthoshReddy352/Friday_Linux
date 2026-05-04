import os
import platform
import sys


def _windows_startup_dir():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def register():
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
    clap_detector = os.path.join(SCRIPT_DIR, "clap_detector.py")

    os_name = platform.system()

    if os_name == "Windows":
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
        if not os.path.exists(venv_python):
            print(f"Error: Virtual environment not found at {venv_python}")
            return False

        startup_dir = _windows_startup_dir()
        os.makedirs(startup_dir, exist_ok=True)
        bat_path = os.path.join(startup_dir, "friday_clap.bat")

        content = f'@echo off\nstart "" /B "{venv_python}" "{clap_detector}" --start\n'
        try:
            with open(bat_path, "w") as f:
                f.write(content)
            print(f"Successfully registered autostart at: {bat_path}")
            return True
        except Exception as e:
            print(f"Failed to register autostart: {e}")
            return False

    else:
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
        if not os.path.exists(venv_python):
            print(f"Error: Virtual environment not found at {venv_python}")
            return False

        AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
        DESKTOP_FILE = os.path.join(AUTOSTART_DIR, "friday_clap.desktop")
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
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
    os_name = platform.system()

    if os_name == "Windows":
        startup_dir = _windows_startup_dir()
        bat_path = os.path.join(startup_dir, "friday_clap.bat")
        if os.path.exists(bat_path):
            try:
                os.remove(bat_path)
                print(f"Successfully removed autostart: {bat_path}")
                return True
            except Exception as e:
                print(f"Failed to remove autostart: {e}")
                return False
        else:
            print("Autostart file not found.")
            return True
    else:
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
