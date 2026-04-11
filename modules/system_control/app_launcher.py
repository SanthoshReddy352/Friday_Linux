import platform
import difflib
import re
import subprocess
import os
import shutil
from core.logger import logger

APP_COMMANDS = {
    "calculator": "gnome-calculator",
    "calc": "gnome-calculator",
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "chromium": "chromium",
    "browser": "firefox",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
    "files": "nautilus",
    "file manager": "nautilus",
    "nautilus": "nautilus",
}


def normalize_app_name(app_name):
    return " ".join(app_name.lower().strip().split())


def canonicalize_app_name(app_name):
    app_name = normalize_app_name(app_name).strip(" .,!?")
    if not app_name:
        return ""
    if app_name in APP_COMMANDS:
        return app_name
    if app_name.endswith("s") and app_name[:-1] in APP_COMMANDS:
        return app_name[:-1]

    candidates = list(APP_COMMANDS)
    match = difflib.get_close_matches(app_name, candidates, n=1, cutoff=0.45)
    return match[0] if match else app_name


def extract_app_names(text):
    text_lower = normalize_app_name(text)
    matches = []

    for alias in sorted(APP_COMMANDS, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(alias)}\b")
        for found in pattern.finditer(text_lower):
            matches.append((found.start(), found.end(), normalize_app_name(alias)))

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
        launch_match = re.search(r'(?:open|launch|start|bring up)\s+(.+)', text_lower)
        if launch_match:
            tail = re.split(r'\b(?:then|also|after that|afterwards|plus|and tell|and what)\b', launch_match.group(1), maxsplit=1)[0]
            parts = re.split(r'\s*(?:,|and|&)\s*', tail)
            for part in parts:
                canonical = canonicalize_app_name(part)
                if canonical and canonical in APP_COMMANDS and canonical not in ordered_matches:
                    ordered_matches.append(canonical)
        return ordered_matches

    match = re.search(r'(?:open|launch|start|bring up)\s+(.+)', text_lower)
    if not match:
        return []

    tail = re.split(r'\b(?:then|also|after that|afterwards|plus|and tell|and what)\b', match.group(1), maxsplit=1)[0]
    parts = re.split(r'\s*(?:,|and|&)\s*', tail)
    resolved = []
    for part in parts:
        canonical = canonicalize_app_name(part)
        if canonical and canonical not in resolved:
            resolved.append(canonical)
    return resolved


def launch_application(app_name):
    """
    More robust application launching logic.
    Checks if command exists and captures proper execution state.
    """
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
    os_name = platform.system()
    app_name = normalize_app_name(app_name)
    
    # Map common names to executable names
    if os_name == "Linux":
        cmd_name = APP_COMMANDS.get(app_name, app_name)
    elif os_name == "Windows":
        cmd_name = "calc" if app_name in {"calculator", "calc"} else app_name
    else:
        cmd_name = app_name
    logger.info(f"Attempting to launch application: '{cmd_name}' (original: '{app_name}')")

    try:
        if os_name == "Windows":
            subprocess.Popen(f"start {cmd_name}", shell=True)
            return f"Opening {app_name}..."
            
        elif os_name == "Linux":
            # Check if the executable exists in PATH
            if shutil.which(cmd_name) is None:
                # If direct command isn't found, we can try searching for flatpaks or snaps in the future
                error_msg = f"Application '{cmd_name}' not found in system PATH."
                logger.error(error_msg)
                return error_msg
                
            # Launch with Popen, disconnecting it from the parent process
            try:
                # stderr and stdout are piped to DEVNULL so it doesn't block Friday
                subprocess.Popen([cmd_name], start_new_session=True, 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Successfully started process for {cmd_name}")
                return f"Opening {app_name}..."
            except Exception as e:
                logger.error(f"Failed to execute '{cmd_name}': {e}")
                return f"Failed to open {app_name}: Execution error."
                
        else:
            return f"Unsupported OS for app launching: {os_name}"
            
    except Exception as e:
        logger.error(f"Unexpected error when launching '{app_name}': {e}")
        return f"Failed to open {app_name}: {str(e)}"
