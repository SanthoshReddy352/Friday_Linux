"""Register the Porcupine wake-word detector to start at login.

On Linux, installs a systemd --user service.
On Windows, drops a .bat shortcut into the per-user Startup folder.
On macOS, installs a LaunchAgent plist.

Run directly (`python -m modules.voice_io.register_wake`) after setup.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys


def _project_paths():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    wake_py = os.path.join(script_dir, "wake_porcupine.py")
    return script_dir, project_root, wake_py


def _venv_python(project_root: str) -> str:
    if platform.system() == "Windows":
        candidate = os.path.join(project_root, ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(project_root, ".venv", "bin", "python3")
    return candidate


def _windows_startup_dir() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def register() -> bool:
    _, project_root, wake_py = _project_paths()
    venv_python = _venv_python(project_root)
    os_name = platform.system()

    if not os.path.exists(venv_python):
        print(f"Error: Friday venv python not found at {venv_python}")
        return False

    if os_name == "Linux":
        return _register_linux(project_root, venv_python, wake_py)
    if os_name == "Windows":
        return _register_windows(project_root, venv_python, wake_py)
    if os_name == "Darwin":
        return _register_macos(project_root, venv_python, wake_py)

    print(f"Unsupported OS for wake registration: {os_name}")
    return False


def _register_linux(project_root: str, venv_python: str, wake_py: str) -> bool:
    systemd_dir = os.path.expanduser("~/.config/systemd/user")
    service_file = os.path.join(systemd_dir, "friday-wake.service")
    clap_service_file = os.path.join(systemd_dir, "friday-clap.service")
    os.makedirs(systemd_dir, exist_ok=True)

    # Replace any older clap-based service from previous installs.
    try:
        print("Checking for existing friday-clap service...")
        subprocess.run(["systemctl", "--user", "stop", "friday-clap.service"], check=False, stderr=subprocess.DEVNULL)
        subprocess.run(["systemctl", "--user", "disable", "friday-clap.service"], check=False, stderr=subprocess.DEVNULL)
        if os.path.exists(clap_service_file):
            os.remove(clap_service_file)
            print(f"Removed old clap service file: {clap_service_file}")
    except Exception as e:
        print(f"Warning: Failed to fully unregister clap service: {e}")

    content = f"""[Unit]
Description=Friday Wake Word Detector (Porcupine)
After=network.target

[Service]
Type=simple
Environment=FRIDAY_PORCUPINE_KEY=
ExecStart={venv_python} {wake_py}
WorkingDirectory={project_root}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""
    try:
        with open(service_file, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"Created systemd service at: {service_file}")
        print("NOTE: Edit the unit and set FRIDAY_PORCUPINE_KEY=<your-key> before enabling.")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "friday-wake.service"], check=True)
        subprocess.run(["systemctl", "--user", "start", "friday-wake.service"], check=True)
        print("Enabled and started friday-wake.service.")
        return True
    except Exception as e:
        print(f"Failed to register wake service: {e}")
        return False


def _register_windows(project_root: str, venv_python: str, wake_py: str) -> bool:
    startup_dir = _windows_startup_dir()
    if not startup_dir:
        print("Error: %APPDATA% not set; cannot locate Windows Startup folder.")
        return False
    os.makedirs(startup_dir, exist_ok=True)
    bat_path = os.path.join(startup_dir, "friday_wake.bat")
    # `start "" /B` detaches the process so the user is not blocked at logon.
    # FRIDAY_PORCUPINE_KEY must be set in the user's environment for the
    # detector to start — print a reminder.
    content = (
        '@echo off\r\n'
        f'cd /d "{project_root}"\r\n'
        f'start "" /B "{venv_python}" "{wake_py}"\r\n'
    )
    try:
        with open(bat_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"Registered Windows autostart at: {bat_path}")
        print("Set FRIDAY_PORCUPINE_KEY in your user environment variables before "
              "the next login (System Properties → Environment Variables).")
        return True
    except Exception as e:
        print(f"Failed to register Windows autostart: {e}")
        return False


def _register_macos(project_root: str, venv_python: str, wake_py: str) -> bool:
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(plist_dir, "app.friday.wake.plist")
    os.makedirs(plist_dir, exist_ok=True)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>app.friday.wake</string>
  <key>ProgramArguments</key>
  <array>
    <string>{venv_python}</string>
    <string>{wake_py}</string>
  </array>
  <key>WorkingDirectory</key><string>{project_root}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
"""
    try:
        with open(plist_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        subprocess.run(["launchctl", "load", "-w", plist_path], check=False)
        print(f"Installed launchd agent at: {plist_path}")
        print("Set FRIDAY_PORCUPINE_KEY in your shell rc before relogin.")
        return True
    except Exception as e:
        print(f"Failed to register macOS launch agent: {e}")
        return False


if __name__ == "__main__":
    sys.exit(0 if register() else 1)
