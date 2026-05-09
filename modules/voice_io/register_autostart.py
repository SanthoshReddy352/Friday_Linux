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
        import subprocess
        venv_python = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
        if not os.path.exists(venv_python):
            print(f"Error: Virtual environment not found at {venv_python}")
            return False

        SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
        SERVICE_FILE = os.path.join(SYSTEMD_DIR, "friday-clap.service")
        os.makedirs(SYSTEMD_DIR, exist_ok=True)

        content = f"""[Unit]
Description=Friday Clap Detector
After=network.target

[Service]
Type=simple
ExecStart={venv_python} {clap_detector} --start
WorkingDirectory={PROJECT_ROOT}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""
        try:
            with open(SERVICE_FILE, "w") as f:
                f.write(content)
            print(f"Successfully created systemd service at: {SERVICE_FILE}")
            
            # Enable and start the service
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "friday-clap.service"], check=True)
            subprocess.run(["systemctl", "--user", "start", "friday-clap.service"], check=True)
            print("Successfully started and enabled friday-clap.service")
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
        import subprocess
        SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
        SERVICE_FILE = os.path.join(SYSTEMD_DIR, "friday-clap.service")
        
        # Try to stop and disable first
        try:
            subprocess.run(["systemctl", "--user", "stop", "friday-clap.service"], check=False, stderr=subprocess.DEVNULL)
            subprocess.run(["systemctl", "--user", "disable", "friday-clap.service"], check=False, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        if os.path.exists(SERVICE_FILE):
            try:
                os.remove(SERVICE_FILE)
                print(f"Successfully removed systemd service file: {SERVICE_FILE}")
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
                return True
            except Exception as e:
                print(f"Failed to remove systemd service: {e}")
                return False
        else:
            print("Systemd service file not found.")
            return True


if __name__ == "__main__":
    register()
