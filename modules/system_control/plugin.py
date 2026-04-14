import os
import re

from core.dialog_state import DialogState
from core.logger import logger
from core.plugin_manager import FridayPlugin
from .app_launcher import extract_app_names, launch_application
from .file_readers import read_file_preview, summarize_file_offline
from .file_search import (
    choose_candidate_from_text,
    extract_extension_from_text,
    format_folder_listing,
    format_search_results,
    list_folder_contents,
    open_file,
    open_folder,
    resolve_folder_path,
    search_files_raw,
    canonicalize_extension,
)
from .file_workspace import WorkspaceFileController
from .media_control import set_volume
from .screenshot import take_screenshot
from .sys_info import get_battery_status, get_cpu_ram_status, get_system_status


class SystemControlPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "SystemControl"
        self.dialog_state = getattr(app, "dialog_state", DialogState())
        self.pending_file_to_open = None
        self.file_controller = WorkspaceFileController(app, self.dialog_state)
        self.app.file_controller = self.file_controller
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "get_system_status",
            "description": "Report overall system health: CPU usage, RAM usage, and battery level.",
            "parameters": {},
            "context_terms": ["system info", "system information", "system details", "system status"],
        }, lambda t, a: get_system_status())

        self.app.router.register_tool({
            "name": "get_friday_status",
            "description": "Report FRIDAY runtime status, including model readiness and disabled optional skills.",
            "parameters": {},
            "context_terms": ["friday status", "assistant status", "runtime status", "model status"],
        }, self.handle_friday_status)

        self.app.router.register_tool({
            "name": "get_battery",
            "description": "Check the current battery percentage and whether it is charging.",
            "parameters": {},
            "context_terms": ["battery", "charge", "power"],
        }, lambda t, a: get_battery_status())

        self.app.router.register_tool({
            "name": "get_cpu_ram",
            "description": "Show current CPU and RAM usage statistics.",
            "parameters": {},
            "context_terms": ["cpu usage", "ram usage", "memory usage", "performance", "resource usage"],
        }, lambda t, a: get_cpu_ram_status())

        self.app.router.register_tool({
            "name": "launch_app",
            "description": "Open or launch a desktop application by name (e.g. firefox, chrome, calculator, nautilus).",
            "parameters": {
                "app_name": "string – name of the application to open",
                "app_names": "array[string] – one or more application names to open in order"
            },
            "context_terms": ["browser", "calculator", "chrome", "firefox", "files", "nautilus"],
        }, self.handle_launch_app)

        self.app.router.register_tool({
            "name": "set_volume",
            "description": "Control system audio volume.",
            "parameters": {
                "direction": "string – one of: 'up', 'down', 'mute', 'unmute'",
                "steps": "integer – number of volume steps to change",
                "percent": "integer – absolute target volume percentage from 0 to 100",
            },
            "context_terms": ["volume", "audio", "sound", "mute", "unmute", "louder", "quieter"],
        }, self.handle_set_volume)

        self.app.router.register_tool({
            "name": "take_screenshot",
            "description": "Capture the current screen and save it as an image file.",
            "parameters": {}
        }, lambda t, a: take_screenshot())

        self.app.router.register_tool({
            "name": "search_file",
            "description": "Search for a file by name on the filesystem.",
            "parameters": {
                "filename": "string – the filename or partial name to search for",
                "folder": "string – optional folder name to limit the search",
                "extension": "string – optional extension such as .pdf or .md",
            }
        }, self.handle_search_file)

        self.app.router.register_tool({
            "name": "manage_file",
            "description": "Create, write, append, or read a text file. You can also save the last assistant answer into a file.",
            "parameters": {
                "action": "string - one of: create, write, append, read",
                "filename": "string - the target filename",
                "folder": "string - optional folder name to place or find the file",
                "content": "string - optional text content to write",
                "extension": "string - optional extension such as .txt or .md",
            }
        }, self.handle_manage_file)

        self.app.router.register_tool({
            "name": "open_file",
            "description": "Open a specific file using the default application.",
            "parameters": {
                "filename": "string – the filename or partial name to find and open",
                "folder": "string – optional folder name to limit the search",
                "extension": "string – optional extension such as .pdf or .md",
            }
        }, self.handle_open_file)

        self.app.router.register_tool({
            "name": "read_file",
            "description": "Read or preview the contents of a file.",
            "parameters": {
                "filename": "string – the filename or partial name to read",
                "folder": "string – optional folder name to limit the search",
                "extension": "string – optional extension such as .pdf or .md",
            }
        }, self.handle_read_file)

        self.app.router.register_tool({
            "name": "summarize_file",
            "description": "Summarize the contents of a file offline.",
            "parameters": {
                "filename": "string – the filename or partial name to summarize",
                "folder": "string – optional folder name to limit the search",
                "extension": "string – optional extension such as .pdf or .md",
            }
        }, self.handle_summarize_file)

        self.app.router.register_tool({
            "name": "list_folder_contents",
            "description": "List the visible files inside a folder.",
            "parameters": {
                "folder": "string – the folder to inspect"
            }
        }, self.handle_list_folder_contents)

        self.app.router.register_tool({
            "name": "open_folder",
            "description": "Open a folder in the system file manager.",
            "parameters": {
                "folder": "string – the folder to open"
            }
        }, self.handle_open_folder)

        self.app.router.register_tool({
            "name": "select_file_candidate",
            "description": "Choose one file from a pending list of candidates.",
            "parameters": {}
        }, self.handle_select_file_candidate)

        self.app.router.register_tool({
            "name": "confirm_yes",
            "description": "User confirms a pending action (yes, sure, ok, open it).",
            "parameters": {}
        }, self.handle_yes)

        self.app.router.register_tool({
            "name": "confirm_no",
            "description": "User declines or cancels a pending action (no, nope, cancel).",
            "parameters": {}
        }, self.handle_no)
        
        self.app.router.register_tool({
            "name": "shutdown_assistant",
            "description": "Close the application and say goodbye.",
            "parameters": {},
            "aliases": ["bye", "goodbye", "exit program", "close assistant", "switch off"]
        }, self.handle_shutdown)

        logger.info("SystemControlPlugin loaded.")

    def handle_launch_app(self, text, args):
        app_names = args.get("app_names", [])
        if isinstance(app_names, str):
            app_names = [app_names]

        app_name = args.get("app_name", "")
        # The LLM sometimes returns app_name as a list instead of a string
        if isinstance(app_name, list):
            app_names.extend(app_name)
        elif isinstance(app_name, str) and app_name.strip():
            app_names.append(app_name.strip())

        normalized_names = [name.strip() for name in app_names if isinstance(name, str) and name.strip()]
        if not normalized_names:
            normalized_names = extract_app_names(text)

        if not normalized_names:
            match = re.search(r'(?:open|launch|start|bring up)\s+([a-zA-Z0-9\-\s,]+)', text.lower())
            if match:
                normalized_names = [match.group(1).strip()]
            else:
                return "Which application would you like me to open?"

        return launch_application(normalized_names)

    def handle_set_volume(self, text, args):
        direction = args.get("direction", "").strip().lower()
        steps = args.get("steps", 1)
        percent = args.get("percent")
        try:
            steps = max(1, int(steps))
        except Exception:
            steps = 1
        try:
            percent = None if percent is None else max(0, min(100, int(percent)))
        except Exception:
            percent = None

        text_lower = text.lower()
        if percent is None:
            percent = self._extract_absolute_volume_percent(text_lower)
        if percent is not None:
            return set_volume("absolute", percent=percent)

        if direction not in ("up", "down", "mute", "unmute"):
            step_match = re.search(r'(\d+)\s+(?:times?|steps?|levels?)', text_lower)
            if step_match:
                steps = max(1, int(step_match.group(1)))

            if "unmute" in text_lower:
                direction = "unmute"
            elif "up" in text_lower or "increase" in text_lower or "louder" in text_lower or "raise" in text_lower:
                direction = "up"
            elif "down" in text_lower or "decrease" in text_lower or "quieter" in text_lower or "lower" in text_lower:
                direction = "down"
            elif "mute" in text_lower:
                direction = "mute"
            else:
                return "What volume percentage would you like, or should I turn it up, down, mute, or unmute it?"
        return set_volume(direction, steps=steps)

    def _extract_absolute_volume_percent(self, text_lower):
        patterns = (
            r"\b(?:set|change|make|turn)\s+(?:the\s+)?volume\s+(?:to|at)\s+(\d{1,3})(?:\s*(?:percent|%))?\b",
            r"\bvolume\s+(?:to|at)\s+(\d{1,3})(?:\s*(?:percent|%))?\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return max(0, min(100, int(match.group(1))))
        return None

    def handle_search_file(self, text, args):
        return self.file_controller.search(text, args)

    def handle_manage_file(self, text, args):
        return self.file_controller.manage(text, args)

    def handle_open_file(self, text, args):
        return self.file_controller.open(text, args)

    def handle_read_file(self, text, args):
        return self.file_controller.read(text, args)

    def handle_summarize_file(self, text, args):
        return self.file_controller.summarize(text, args)

    def handle_list_folder_contents(self, text, args):
        return self.file_controller.list_folder(text, args)

    def handle_open_folder(self, text, args):
        return self.file_controller.open_folder(text, args)

    def handle_select_file_candidate(self, text, args):
        return self.file_controller.select_candidate(text, args)

    def handle_yes(self, text, args):
        return self.file_controller.confirm_yes(text, args)

    def handle_no(self, text, args):
        return self.file_controller.confirm_no(text, args)

    def handle_shutdown(self, text, args):
        """Signal the system to perform a clean shutdown."""
        import threading
        import time
        
        def _trigger_shutdown():
            time.sleep(3.5) # Wait for 'Bye' TTS
            self.app.event_bus.publish("system_shutdown", {})
            
        threading.Thread(target=_trigger_shutdown, daemon=True).start()
        return "Bye sir, see you soon."

    def handle_friday_status(self, text, args):
        capabilities = getattr(self.app, "capabilities", None)
        router = getattr(self.app, "router", None)
        lines = ["FRIDAY status:"]
        if capabilities:
            lines.extend(f"- {line}" for line in capabilities.summary_lines())
            disabled = capabilities.disabled_skills()
            if disabled:
                for skill_name, reason in sorted(disabled.items()):
                    lines.append(f"- {skill_name}: {reason}")
        if router and hasattr(router, "model_manager"):
            for role in ("chat", "tool"):
                status = router.model_manager.status(role)
                state = "loaded" if status["loaded"] else "available" if status["exists"] else "missing"
                lines.append(f"- {role} model: {os.path.basename(status['path'])} ({state})")
        return "\n".join(lines)

    def _handle_file_action(self, text, args, fallback_actions):
        if self.dialog_state.has_pending_file_request():
            pending = self.dialog_state.pending_file_request
            request = self._parse_file_request(text, args, default_actions=fallback_actions)
            if request["filename"] or request["extension"] or request["use_selected_file"]:
                selected_path, error = choose_candidate_from_text(text, pending.candidates)
                if selected_path:
                    actions = pending.requested_actions or fallback_actions
                    return self._finalize_pending_file(selected_path, actions)
                if error and not request["filename"]:
                    return error

        request = self._parse_file_request(text, args, default_actions=fallback_actions)

        if request["use_selected_file"] and self.dialog_state.selected_file:
            return self._execute_file_actions(self.dialog_state.selected_file, request["requested_actions"])

        if not request["filename"]:
            pending = self.dialog_state.pending_file_request
            if pending and len(pending.candidates) == 1:
                actions = pending.requested_actions or request["requested_actions"] or fallback_actions
                return self._finalize_pending_file(pending.candidates[0], actions)
            if self.dialog_state.selected_file and request["requested_actions"] != ["open"]:
                return self._execute_file_actions(self.dialog_state.selected_file, request["requested_actions"])
            return f"Which file would you like me to {fallback_actions[0]}?"

        folder_path, matches, error = self._resolve_file_matches(request)
        if error:
            return error

        if folder_path:
            self.dialog_state.remember_folder(folder_path)

        if not matches:
            return self._format_missing_file_response(request, folder_path)

        if len(matches) > 1:
            self.dialog_state.set_pending_file_request(
                candidates=matches,
                requested_actions=request["requested_actions"] or fallback_actions,
                folder_path=folder_path,
                filename_query=request["filename"],
                extension=request["extension"],
            )
            return self._format_candidate_prompt(matches)

        return self._execute_file_actions(matches[0], request["requested_actions"] or fallback_actions)

    def _parse_file_request(self, text, args=None, default_actions=None):
        args = dict(args or {})
        text_lower = text.lower()
        folder = (args.get("folder") or "").strip() or self._extract_folder_name(text_lower)
        extension = canonicalize_extension((args.get("extension") or "").strip()) or extract_extension_from_text(text_lower)
        filename = (args.get("filename") or args.get("query") or "").strip() or self._extract_filename_query(text_lower)
        filename = self._clean_entity(filename)
        folder = self._clean_entity(folder)

        return {
            "filename": filename,
            "folder": folder,
            "extension": extension,
            "requested_actions": self._detect_requested_actions(text_lower, default_actions),
            "use_selected_file": bool(re.search(r"\b(?:it|that file|this file|selected file)\b", text_lower)),
            "use_current_folder": bool(re.search(r"\b(?:that|this)\s+folder\b", text_lower)),
            "text_lower": text_lower,
        }

    def _resolve_file_matches(self, request):
        folder_path = None
        if request["folder"]:
            folder_path = resolve_folder_path(request["folder"])
            if not folder_path:
                return None, [], f"I couldn't find a folder named '{request['folder']}'."
        elif request["use_current_folder"]:
            folder_path = self.dialog_state.current_folder
        elif self.dialog_state.current_folder and request["text_lower"].count("folder") <= 1:
            folder_path = self.dialog_state.current_folder

        matches = search_files_raw(
            request["filename"],
            folder_path=folder_path,
            extension=request["extension"],
            limit=8,
        )
        return folder_path, matches, None

    def _extract_folder_name(self, text_lower):
        patterns = (
            r"\b(?:in|inside|from|within)\s+(?:the\s+)?([a-z0-9][a-z0-9 _\-.]+?)\s+folder\b",
            r"\bopen\s+(?:the\s+)?([a-z0-9][a-z0-9 _\-.]+?)\s+folder\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                folder_name = self._clean_entity(match.group(1))
                if folder_name in {"that", "this"}:
                    return ""
                return folder_name
        return ""

    def _extract_filename_query(self, text_lower):
        patterns = (
            r"\bfile\s+([a-z0-9][a-z0-9 _\-.]*?)(?=\s+(?:open|read|summarize|preview|inside|in|from|within|and)\b|$)",
            r"\b(?:named|called)\s+([a-z0-9][a-z0-9 _\-.]*?)(?=\s+(?:open|read|summarize|preview|inside|in|from|within|and)\b|$)",
            r"\b(?:open|read|summarize|preview|find|search|locate)\s+(?:the\s+)?(?:file\s+)?([a-z0-9][a-z0-9 _\-.]*?)(?=\s+(?:inside|in|from|within|folder|and)\b|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                candidate = self._clean_entity(match.group(1))
                if candidate not in {"it", "them", "that", "this"}:
                    return candidate
        return ""

    def _clean_entity(self, value):
        value = (value or "").strip(" .,!?:;\"'")
        value = re.sub(r"\s+", " ", value)
        return value

    def _detect_requested_actions(self, text_lower, default_actions):
        actions = []
        if re.search(r"\bopen\b", text_lower):
            actions.append("open")
        if re.search(r"\b(?:read|preview|show contents)\b", text_lower):
            actions.append("read")
        if re.search(r"\b(?:summarize|summary of|sum up)\b", text_lower):
            actions.append("summarize")

        if not actions:
            actions = list(default_actions or [])

        ordered = []
        for action in ("open", "read", "summarize"):
            if action in actions and action not in ordered:
                ordered.append(action)
        return ordered

    def _format_missing_file_response(self, request, folder_path):
        if folder_path:
            folder_name = os.path.basename(folder_path)
            message = f"FAILURE: I couldn't find a file named '{request['filename']}' in the {folder_name} folder."
            self.dialog_state.remember_folder(folder_path)
        else:
            message = f"FAILURE: I couldn't find any file named '{request['filename']}'."

        self.dialog_state.remember_error(message)
        if folder_path:
            return message + " You can ask me what other files are in that folder."
        return message

    def _format_candidate_prompt(self, matches):
        lines = ["I found multiple matching files. Which one should I use?"]
        for index, match in enumerate(matches[:8], 1):
            lines.append(f"{index}. {os.path.basename(match)}")
        lines.append("Reply with the number, the exact filename, or something like 'the pdf one'.")
        return "\n".join(lines)

    def _finalize_pending_file(self, filepath, actions):
        self.dialog_state.clear_pending_file_request()
        self.pending_file_to_open = None
        return self._execute_file_actions(filepath, actions)

    def _execute_file_actions(self, filepath, actions):
        actions = list(actions or ["open"])
        responses = []

        self.dialog_state.remember_file(filepath)
        self.dialog_state.remember_error(None)

        for action in actions:
            if action == "open":
                responses.append(open_file(filepath))
            elif action == "read":
                responses.append(read_file_preview(filepath))
            elif action == "summarize":
                llm = self.app.router.get_llm()
                responses.append(summarize_file_offline(filepath, llm=llm))

        deduped = []
        seen = set()
        for response in responses:
            key = response.strip()
            if key and key not in seen:
                deduped.append(key)
                seen.add(key)
        return "\n".join(deduped)


def setup(app):
    return SystemControlPlugin(app)
