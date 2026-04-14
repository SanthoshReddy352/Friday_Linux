import importlib.util
import os
import platform
import re
import shlex
import shutil
from dataclasses import dataclass, field

from core.logger import logger


KNOWN_PYTHON_MODULES = (
    "cv2",
    "torch",
    "ultralytics",
    "selenium",
    "webdriver_manager",
    "google.genai",
    "dotenv",
    "llama_cpp",
    "sounddevice",
    "PyQt6",
    "PyQt5",
)

KNOWN_BINARIES = (
    "firefox",
    "firefox-esr",
    "google-chrome",
    "google-chrome-stable",
    "brave-browser",
    "brave-browser-stable",
    "chromium",
    "nautilus",
    "thunar",
    "gnome-calculator",
    "mate-calc",
    "gnome-terminal",
    "qterminal",
    "x-terminal-emulator",
    "mpv",
    "vlc",
    "wpctl",
    "pactl",
    "amixer",
    "xdg-open",
)


@dataclass
class DesktopApp:
    name: str
    command: str
    desktop_id: str = ""
    exec_line: str = ""
    aliases: set[str] = field(default_factory=set)


class SystemCapabilities:
    def __init__(self, config=None):
        self.config = config
        self.platform = platform.system()
        self.python_modules = {}
        self.binaries = {}
        self.desktop_apps = {}
        self.audio_backends = []
        self.skill_status = {}

    def probe(self):
        self.python_modules = {
            module_name: self._module_available(module_name)
            for module_name in KNOWN_PYTHON_MODULES
        }
        self.binaries = {
            binary: shutil.which(binary)
            for binary in KNOWN_BINARIES
        }
        self.desktop_apps = self._discover_desktop_apps()
        self.audio_backends = [
            backend for backend in ("wpctl", "pactl", "amixer")
            if self.binaries.get(backend)
        ]
        logger.info(
            "Capability probe complete: platform=%s, audio_backends=%s, desktop_apps=%s",
            self.platform,
            ", ".join(self.audio_backends) or "none",
            len(self.desktop_apps),
        )
        return self

    def register_skill_status(self, skill_name, available, reason="", tools=None):
        self.skill_status[skill_name] = {
            "available": bool(available),
            "reason": (reason or "").strip(),
            "tools": list(tools or []),
        }

    def missing_python_modules(self, required):
        return [name for name in (required or []) if not self.python_modules.get(name)]

    def missing_binaries(self, required):
        return [name for name in (required or []) if not self.binaries.get(name)]

    def disabled_skills(self):
        return {
            name: info["reason"] or "Unavailable on this system."
            for name, info in self.skill_status.items()
            if not info.get("available")
        }

    def summary_lines(self):
        disabled = self.disabled_skills()
        lines = [
            f"Platform: {self.platform}",
            f"Audio backends: {', '.join(self.audio_backends) if self.audio_backends else 'none'}",
            f"Desktop apps: {len(self.desktop_apps)} discovered",
        ]
        if disabled:
            lines.append(f"Disabled skills: {len(disabled)}")
        return lines

    def _module_available(self, module_name):
        try:
            return importlib.util.find_spec(module_name) is not None
        except ModuleNotFoundError:
            return False
        except Exception:
            return False

    def _discover_desktop_apps(self):
        apps = {}
        seen = set()

        for binary, resolved in self.binaries.items():
            if not resolved:
                continue
            alias = self._normalize_alias(os.path.basename(binary))
            apps[alias] = DesktopApp(
                name=self._prettify_name(alias),
                command=binary,
                aliases={alias},
            )
            seen.add(binary)

        for applications_dir in self._application_dirs():
            if not os.path.isdir(applications_dir):
                continue

            for entry_name in sorted(os.listdir(applications_dir)):
                if not entry_name.endswith(".desktop"):
                    continue
                entry_path = os.path.join(applications_dir, entry_name)
                app = self._parse_desktop_file(entry_path)
                if not app or not app.command:
                    continue

                key = self._normalize_alias(app.name or app.desktop_id or app.command)
                existing = apps.get(key)
                if existing:
                    existing.aliases.update(app.aliases)
                    if not existing.exec_line:
                        existing.exec_line = app.exec_line
                    continue

                apps[key] = app
                seen.add(app.command)

        return apps

    def _application_dirs(self):
        return (
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        )

    def _parse_desktop_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except OSError:
            return None

        fields = {}
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key not in fields:
                fields[key] = value.strip()

        if fields.get("NoDisplay", "").lower() == "true":
            return None

        exec_line = fields.get("Exec", "")
        command = self._extract_exec_command(exec_line)
        if not command:
            return None

        name = fields.get("Name", "")
        desktop_id = os.path.basename(path)
        aliases = {
            self._normalize_alias(name),
            self._normalize_alias(os.path.splitext(desktop_id)[0]),
            self._normalize_alias(command),
        }
        aliases.discard("")

        return DesktopApp(
            name=name or self._prettify_name(command),
            command=command,
            desktop_id=desktop_id,
            exec_line=exec_line,
            aliases=aliases,
        )

    def _extract_exec_command(self, exec_line):
        if not exec_line:
            return ""
        try:
            parts = shlex.split(exec_line)
        except ValueError:
            parts = exec_line.split()
        if not parts:
            return ""
        command = os.path.basename(parts[0])
        command = re.sub(r"%[fFuUdDnNickvm]", "", command).strip()
        return command

    def _normalize_alias(self, value):
        cleaned = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
        return " ".join(cleaned.split())

    def _prettify_name(self, value):
        return " ".join(part.capitalize() for part in self._normalize_alias(value).split())
