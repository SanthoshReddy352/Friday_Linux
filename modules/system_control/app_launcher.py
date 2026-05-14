import difflib
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from core.logger import logger


@dataclass
class AppLaunchTarget:
    canonical_name: str
    command: str
    aliases: set[str] = field(default_factory=set)


# Command lists are scanned in order; the first one that resolves via
# shutil.which is used. Mixing Linux and Windows commands in the same tuple
# is intentional so the registry survives unchanged on both OSes — `which`
# is the only filter.
APP_PREFERENCES = (
    {
        "canonical": "calculator",
        "aliases": {"calculator", "calc"},
        "commands": ("gnome-calculator", "mate-calc", "qalculate-gtk", "calc.exe", "calc"),
    },
    {
        "canonical": "chrome",
        "aliases": {"chrome", "google chrome"},
        "commands": ("google-chrome", "google-chrome-stable", "chrome.exe", "chrome"),
    },
    {
        "canonical": "brave",
        "aliases": {"brave", "brave browser", "brave web browser"},
        "commands": ("brave-browser", "brave-browser-stable", "brave.exe", "brave"),
    },
    {
        "canonical": "edge",
        "aliases": {"edge", "microsoft edge", "ms edge"},
        "commands": ("msedge", "msedge.exe", "microsoft-edge", "microsoft-edge-stable"),
    },
    {
        "canonical": "chromium",
        "aliases": {"chromium"},
        "commands": ("chromium", "chromium-browser", "chromium.exe"),
    },
    {
        "canonical": "browser",
        "aliases": {"browser", "web browser"},
        "commands": (
            "firefox", "firefox-esr", "google-chrome", "google-chrome-stable", "chromium",
            "msedge", "msedge.exe", "chrome.exe", "firefox.exe",
        ),
    },
    {
        "canonical": "firefox",
        "aliases": {"firefox", "mozilla firefox", "firefox esr"},
        "commands": ("firefox", "firefox-esr", "firefox.exe"),
    },
    {
        "canonical": "files",
        "aliases": {"files", "file manager", "nautilus", "thunar", "file explorer", "explorer"},
        "commands": ("nautilus", "thunar", "dolphin", "pcmanfm", "explorer.exe"),
    },
    {
        "canonical": "terminal",
        "aliases": {"terminal", "gnome terminal", "qterminal", "command prompt", "powershell"},
        "commands": (
            "gnome-terminal", "qterminal", "konsole", "x-terminal-emulator", "alacritty",
            "wt.exe", "powershell.exe", "pwsh.exe", "cmd.exe",
        ),
    },
    {
        "canonical": "notepad",
        "aliases": {"notepad", "text editor", "editor"},
        "commands": ("notepad.exe", "gedit", "kate", "mousepad", "xed"),
    },
    {
        "canonical": "mpv",
        "aliases": {"mpv", "media player", "vlc"},
        "commands": ("mpv", "vlc", "mpv.exe", "vlc.exe"),
    },
)


_APP_REGISTRY = {}
GENERIC_ALIAS_WORDS = {
    "app", "application", "browser", "web", "desktop", "player", "editor",
    "viewer", "client", "community", "stable",
}
FUZZY_ALLOWED_CANONICALS = {spec["canonical"] for spec in APP_PREFERENCES}


def configure_app_registry(capabilities=None):
    global _APP_REGISTRY
    _APP_REGISTRY = _build_registry(capabilities)
    return _APP_REGISTRY


def get_app_registry():
    if not _APP_REGISTRY:
        configure_app_registry()
    return _APP_REGISTRY


def normalize_app_name(app_name):
    cleaned = re.sub(r"[^a-z0-9]+", " ", (app_name or "").lower()).strip()
    return " ".join(cleaned.split())


def canonicalize_app_name(app_name):
    normalized = normalize_app_name(app_name).strip(" .,!?")
    if not normalized:
        return ""

    registry = get_app_registry()
    if normalized in registry:
        return normalized
    if normalized.endswith("s") and normalized[:-1] in registry:
        return normalized[:-1]

    # Keep fuzzy matching narrow so unknown app names do not drift into
    # unrelated desktop entries discovered from the system.
    fuzzy_candidates = [
        alias for alias, target in registry.items()
        if target.canonical_name in FUZZY_ALLOWED_CANONICALS
    ]
    match = _best_fuzzy_app_match(normalized, fuzzy_candidates)
    return match if match else normalized


def extract_app_names(text):
    text_lower = normalize_app_name(text)
    registry = get_app_registry()
    matches = []

    for alias in sorted(registry, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(alias)}\b")
        for found in pattern.finditer(text_lower):
            matches.append((found.start(), found.end(), alias))

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    ordered_matches = []
    consumed_ranges = []
    for start, end, canonical in matches:
        overlaps = any(not (end <= used_start or start >= used_end) for used_start, used_end in consumed_ranges)
        if overlaps or canonical in ordered_matches:
            continue
        consumed_ranges.append((start, end))
        ordered_matches.append(canonical)

    if ordered_matches:
        launch_match = re.search(r"(?:open|launch|start|bring up)\s+(.+)", text_lower)
        if launch_match:
            tail = re.split(r"\b(?:then|also|after that|afterwards|plus|and tell|and what)\b", launch_match.group(1), maxsplit=1)[0]
            parts = re.split(r"\s*(?:,|and|&)\s*", tail)
            for part in parts:
                normalized_part = normalize_app_name(part)
                if not normalized_part:
                    continue
                if len(_exact_alias_hits(normalized_part, registry)) > 1:
                    continue
                canonical = canonicalize_app_name(part)
                if canonical and canonical in registry and canonical not in ordered_matches:
                    ordered_matches.append(canonical)
        return ordered_matches

    match = re.search(r"(?:open|launch|start|bring up)\s+(.+)", text_lower)
    if not match:
        return []

    tail = re.split(r"\b(?:then|also|after that|afterwards|plus|and tell|and what)\b", match.group(1), maxsplit=1)[0]
    parts = re.split(r"\s*(?:,|and|&)\s*", tail)
    resolved = []
    for part in parts:
        canonical = canonicalize_app_name(part)
        if canonical and canonical in registry and canonical not in resolved:
            resolved.append(canonical)
    return resolved


def launch_application(app_name):
    if isinstance(app_name, (list, tuple, set)):
        app_names = [canonicalize_app_name(name) for name in app_name if canonicalize_app_name(name)]
        if not app_names:
            return "Which application would you like me to open?"
        responses = []
        for name in app_names:
            responses.append(_launch_single_application(name))
        return "\n".join(responses)

    return _launch_single_application(app_name)


def _launch_single_application(app_name):
    registry = get_app_registry()
    os_name = platform.system()
    canonical = canonicalize_app_name(app_name)
    target = registry.get(canonical)
    command = target.command if target else canonical
    logger.info("Attempting to launch application: '%s' (canonical: '%s')", command, canonical)

    try:
        if os_name == "Windows":
            resolved = shutil.which(command)
            if resolved is None and not command.lower().endswith(".exe"):
                # Try with .exe suffix — Windows PATH search via shutil.which
                # only adds suffixes from PATHEXT, but explicit user input like
                # "chrome" should still resolve to chrome.exe.
                resolved = shutil.which(command + ".exe")
            target = resolved or command
            try:
                # os.startfile honors file associations and start menu links.
                os.startfile(target)
            except (AttributeError, OSError):
                creation_flags = 0
                detached = getattr(subprocess, "DETACHED_PROCESS", 0)
                new_pg = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                creation_flags = detached | new_pg
                subprocess.Popen(
                    [target],
                    creationflags=creation_flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            logger.info("Successfully started process for %s", target)
            return f"Opening {canonical or app_name}..."

        if os_name == "Linux":
            resolved = shutil.which(command)
            if resolved is None:
                error_msg = f"Application '{command}' not found in system PATH."
                logger.error(error_msg)
                return error_msg

            subprocess.Popen(
                [command],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Successfully started process for %s", command)
            return f"Opening {canonical or app_name}..."

        if os_name == "Darwin":
            subprocess.Popen(["open", "-a", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening {canonical or app_name}..."

        return f"Unsupported OS for app launching: {os_name}"
    except Exception as exc:
        logger.error("Unexpected error when launching '%s': %s", app_name, exc)
        return f"Failed to open {canonical or app_name}: {exc}"


def _build_registry(capabilities=None):
    command_map = {}
    if capabilities is not None:
        for binary, resolved in getattr(capabilities, "binaries", {}).items():
            if resolved:
                command_map[binary] = resolved
        for app in getattr(capabilities, "desktop_apps", {}).values():
            if getattr(app, "command", ""):
                command_map.setdefault(app.command, shutil.which(app.command) or app.command)

    registry = {}
    for spec in APP_PREFERENCES:
        command = _pick_available_command(spec["commands"], command_map)
        if not command:
            continue

        alias_set = {normalize_app_name(alias) for alias in spec["aliases"]}
        alias_set.add(normalize_app_name(spec["canonical"]))
        if spec["canonical"] == "files":
            alias_set.update({"file explorer", "folder browser"})
        if spec["canonical"] == "browser":
            alias_set.update({"internet", "internet browser"})

        target = AppLaunchTarget(
            canonical_name=spec["canonical"],
            command=command,
            aliases=alias_set,
        )
        for alias in target.aliases:
            registry[alias] = target

    if capabilities is not None:
        for app in getattr(capabilities, "desktop_apps", {}).values():
            command = getattr(app, "command", "")
            if not command:
                continue
            aliases = {normalize_app_name(alias) for alias in getattr(app, "aliases", set()) if normalize_app_name(alias)}
            aliases.update(_derived_aliases(aliases))
            if not aliases:
                continue
            canonical = min(aliases, key=len)
            if canonical in registry:
                continue
            target = AppLaunchTarget(canonical_name=canonical, command=command, aliases=aliases)
            for alias in aliases:
                registry.setdefault(alias, target)

    return registry


def _pick_available_command(commands, command_map):
    for command in commands:
        if command in command_map or shutil.which(command):
            return command
    return ""


def _derived_aliases(aliases):
    derived = set()
    for alias in aliases:
        words = alias.split()
        if len(words) > 1:
            trimmed = [word for word in words if word not in GENERIC_ALIAS_WORDS]
            if trimmed:
                derived.add(" ".join(trimmed))
                derived.add(trimmed[0])
    return {alias for alias in derived if alias}


def _exact_alias_hits(text, registry):
    hits = []
    for alias in registry:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            hits.append(alias)
    return hits


def _best_fuzzy_app_match(normalized, candidates):
    best_alias = ""
    best_ratio = 0.0
    for alias in candidates:
        ratio = difflib.SequenceMatcher(None, normalized, alias).ratio()
        prefix_length = len(os.path.commonprefix([normalized, alias]))
        if ratio > best_ratio:
            best_ratio = ratio
            best_alias = alias
        if ratio >= 0.76:
            return alias
        if prefix_length >= 3 and ratio >= 0.42:
            return alias
    return best_alias if best_ratio >= 0.82 else ""


configure_app_registry()
