import os
import re
from dataclasses import dataclass, field

from core.logger import logger
from .file_readers import read_file_preview, summarize_file_offline
from .file_search import (
    canonicalize_extension,
    choose_candidate_from_text,
    extract_extension_from_text,
    format_folder_listing,
    format_search_results,
    list_folder_contents,
    open_file,
    open_folder,
    resolve_folder_path,
    search_files_raw,
)


SPECIAL_FOLDERS = {
    "desktop": "Desktop",
    "desktops": "Desktop",
    "download": "Downloads",
    "downloads": "Downloads",
    "document": "Documents",
    "documents": "Documents",
    "picture": "Pictures",
    "pictures": "Pictures",
}


@dataclass
class FileLookupRequest:
    filename: str = ""
    folder: str = ""
    extension: str | None = None
    requested_actions: list[str] = field(default_factory=list)
    use_selected_file: bool = False
    use_current_folder: bool = False
    text_lower: str = ""


@dataclass
class FileManageRequest:
    action: str = "create"
    filename: str = ""
    folder: str = ""
    extension: str | None = None
    content: str = ""
    use_last_assistant_message: bool = False


class WorkspaceFileController:
    """
    A single workspace-oriented controller for file operations.

    The controller keeps file work deterministic and stateful:
    search first, carry forward pending selections, and only touch the
    filesystem once the target file has been resolved.
    """

    def __init__(self, app, dialog_state):
        self.app = app
        self.dialog_state = dialog_state
        self.pending_file_to_open = None

    def search(self, text, args):
        request = self.parse_lookup_request(text, args, default_actions=["open"])
        if not request.filename:
            return "Which file would you like me to find?"

        folder_path, matches, error = self.resolve_matches(request)
        if error:
            return error

        if folder_path:
            self.dialog_state.remember_folder(folder_path)
        elif len(matches) == 1:
            self.dialog_state.remember_folder(os.path.dirname(matches[0]))

        if not matches:
            return self._format_missing_file_response(request, folder_path)

        self.dialog_state.remember_listing(matches)
        self.pending_file_to_open = matches[0] if len(matches) == 1 else None
        self.dialog_state.set_pending_file_request(
            candidates=matches,
            requested_actions=request.requested_actions or ["open"],
            folder_path=folder_path,
            filename_query=request.filename,
            extension=request.extension,
        )

        response = [format_search_results(matches, request.filename)]
        if len(matches) == 1:
            response.append(f"Would you like me to open '{os.path.basename(matches[0])}'?")
        else:
            response.append("Tell me the number, exact filename, or extension to choose one.")
        return "\n".join(response)

    def open(self, text, args):
        return self._handle_file_action(text, args, fallback_actions=["open"])

    def read(self, text, args):
        return self._handle_file_action(text, args, fallback_actions=["read"])

    def summarize(self, text, args):
        return self._handle_file_action(text, args, fallback_actions=["summarize"])

    def list_folder(self, text, args):
        request = self.parse_lookup_request(text, args)
        folder_path = None

        if request.folder:
            folder_path = self.resolve_folder(request.folder)
            if not folder_path:
                return f"I couldn't find a folder named '{request.folder}'."
        elif request.use_current_folder:
            folder_path = self.dialog_state.current_folder
        else:
            folder_path = self.dialog_state.current_folder

        if not folder_path:
            return "Which folder should I inspect?"

        listing = list_folder_contents(folder_path, limit=25)
        if "other file" in request.text_lower and self.dialog_state.selected_file:
            listing = [path for path in listing if path != self.dialog_state.selected_file]

        self.dialog_state.remember_folder(folder_path)
        self.dialog_state.remember_listing(listing)
        return format_folder_listing(folder_path, listing[:15])

    def open_folder(self, text, args):
        request = self.parse_lookup_request(text, args)
        folder_query = request.folder
        if not folder_query and self.dialog_state.current_folder:
            return open_folder(self.dialog_state.current_folder)
        if not folder_query:
            return "Which folder should I open?"

        folder_path = self.resolve_folder(folder_query)
        if not folder_path:
            return f"I couldn't find a folder named '{folder_query}'."

        self.dialog_state.remember_folder(folder_path)
        return open_folder(folder_path)

    def select_candidate(self, text, args):
        pending = self.dialog_state.pending_file_request
        if not pending or not pending.candidates:
            return "I don't have any pending file choices right now."

        selected_path, error = choose_candidate_from_text(text, pending.candidates)
        if error:
            return error
        if not selected_path:
            return self._format_candidate_prompt(pending.candidates)

        return self._finalize_pending_file(selected_path, pending.requested_actions or ["open"])

    def confirm_yes(self, text, args):
        pending = self.dialog_state.pending_file_request
        if pending and pending.candidates:
            if len(pending.candidates) == 1:
                return self._finalize_pending_file(
                    pending.candidates[0],
                    pending.requested_actions or ["open"],
                )
            return self._format_candidate_prompt(pending.candidates)

        if self.pending_file_to_open:
            filepath = self.pending_file_to_open
            self.pending_file_to_open = None
            return self._execute_file_actions(filepath, ["open"])
        workflow_state = self._workflow_state()
        if workflow_state and workflow_state.get("pending_slots"):
            pending_slots = ", ".join(workflow_state.get("pending_slots") or [])
            if "filename" in workflow_state.get("pending_slots", []):
                return "What should I name the file?"
            if "content" in workflow_state.get("pending_slots", []):
                filename = workflow_state.get("target", {}).get("filename") or "the file"
                return f"What would you like me to write in {filename}?"
            return f"I'm waiting for: {pending_slots}."
        pending_clarification = getattr(self.dialog_state, "pending_clarification", None)
        if pending_clarification and pending_clarification.action_text:
            self.dialog_state.clear_pending_clarification()
            router = getattr(self.app, "router", None)
            if router:
                return router.process_text(pending_clarification.action_text)
            return "Okay."
        return "I'm not sure what you're saying 'yes' to."

    def confirm_no(self, text, args):
        if self.dialog_state.has_pending_file_request():
            self.dialog_state.clear_pending_file_request()
            self.pending_file_to_open = None
            return "Okay, I'll leave it there."
        if self.pending_file_to_open:
            self.pending_file_to_open = None
            return "Okay, I'll leave it closed."
        workflow_state = self._workflow_state()
        if workflow_state and workflow_state.get("status") in {"active", "pending"}:
            self._save_file_workflow_state({
                **workflow_state,
                "status": "completed",
                "pending_slots": [],
                "result_summary": "Okay, I'll leave the file as it is.",
            })
            return "Okay, I'll leave the file as it is."
        pending_clarification = getattr(self.dialog_state, "pending_clarification", None)
        if pending_clarification and pending_clarification.action_text:
            self.dialog_state.clear_pending_clarification()
            return pending_clarification.cancel_message or "Okay. Please tell me what you'd like instead."
        return "I'm not sure what you're saying 'no' to."

    def manage(self, text, args):
        request = self.parse_manage_request(text, args)
        workflow_state = self._workflow_state()
        active_target = dict(workflow_state.get("target") or {})
        target_path = active_target.get("path") or self.dialog_state.selected_file or ""

        if not request.filename and target_path and (
            request.action in {"write", "append", "read"} or request.use_last_assistant_message
        ):
            request.filename = os.path.basename(target_path)
            request.folder = os.path.dirname(target_path)
            request.extension = request.extension or os.path.splitext(target_path)[1]

        if not request.filename:
            self._save_file_workflow_state({
                "status": "pending",
                "pending_slots": ["filename"],
                "last_action": request.action,
                "action": request.action,
                "target": {
                    "folder": request.folder,
                    "extension": request.extension,
                },
                "result_summary": "Waiting for the file name.",
            })
            return "What should I name the file?"

        folder_path = self.resolve_manage_folder(request)
        target_path = self._build_target_path(request.filename, folder_path, request.extension)
        if not target_path:
            return "I couldn't figure out where to create that file."

        content = request.content
        if request.use_last_assistant_message and not content:
            content = self._latest_assistant_text()
            if not content:
                return "I don't have a recent assistant response to save yet."

        if request.action in {"write", "append"} and content and self._looks_like_topic_phrase(content):
            generated = self._generate_topic_content(content)
            if generated:
                content = generated

        if request.action in {"write", "append"} and not content:
            self._save_file_workflow_state({
                "status": "pending",
                "pending_slots": ["content"],
                "last_action": request.action,
                "action": request.action,
                "target": self._target_payload(target_path, request.extension),
                "result_summary": f"Waiting for content for {os.path.basename(target_path)}.",
            })
            return f"What would you like me to write in {os.path.basename(target_path)}?"

        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            if request.action == "create":
                with open(target_path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                verb = "Created"
            elif request.action == "write":
                with open(target_path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                verb = "Saved"
            elif request.action == "append":
                prefix = "\n" if os.path.exists(target_path) and os.path.getsize(target_path) > 0 else ""
                with open(target_path, "a", encoding="utf-8") as handle:
                    handle.write(prefix + content)
                verb = "Updated"
            elif request.action == "read":
                self.dialog_state.remember_file(target_path)
                return read_file_preview(target_path)
            else:
                return f"I don't support the file action '{request.action}' yet."
        except Exception as exc:
            logger.error("File write failed for '%s': %s", target_path, exc)
            return f"FAILURE: Failed to update the file: {exc}"

        self.dialog_state.remember_file(target_path)
        self._save_file_workflow_state({
            "status": "active",
            "pending_slots": [],
            "last_action": request.action,
            "action": request.action,
            "target": self._target_payload(target_path, request.extension),
            "result_summary": f"{verb} {os.path.basename(target_path)}.",
        })
        return f"SUCCESS: {verb} {os.path.basename(target_path)}."

    def parse_lookup_request(self, text, args=None, default_actions=None):
        args = dict(args or {})
        text_lower = text.lower()
        folder = (args.get("folder") or "").strip() or self._extract_folder_name(text_lower)
        extension = canonicalize_extension((args.get("extension") or "").strip()) or extract_extension_from_text(text_lower)
        filename = (args.get("filename") or args.get("query") or "").strip() or self._extract_filename_query(text_lower)

        return FileLookupRequest(
            filename=self._clean_entity(filename),
            folder=self._clean_entity(folder),
            extension=extension,
            requested_actions=self._detect_requested_actions(text_lower, default_actions),
            use_selected_file=bool(re.search(r"\b(?:it|that file|this file|selected file)\b", text_lower)),
            use_current_folder=bool(re.search(r"\b(?:that|this|same|current)\s+folder\b", text_lower)),
            text_lower=text_lower,
        )

    def parse_manage_request(self, text, args=None):
        args = dict(args or {})
        text_lower = text.lower()
        action = (args.get("action") or "").strip().lower() or self._detect_manage_action(text_lower)
        folder = (args.get("folder") or "").strip() or self._extract_folder_name(text_lower)
        extension = canonicalize_extension((args.get("extension") or "").strip()) or extract_extension_from_text(text_lower)
        filename = (args.get("filename") or "").strip() or self._extract_manage_filename(text_lower)
        content = (args.get("content") or "").strip() or self._extract_manage_content(text)
        use_last_assistant_message = self._wants_last_assistant_message(text_lower, content)

        return FileManageRequest(
            action=action,
            filename=self._clean_entity(filename),
            folder=self._clean_entity(folder),
            extension=extension,
            content=content.strip(),
            use_last_assistant_message=use_last_assistant_message,
        )

    def resolve_matches(self, request):
        folder_path = None
        if request.folder:
            folder_path = self.resolve_folder(request.folder)
            if not folder_path:
                return None, [], f"I couldn't find a folder named '{request.folder}'."
        elif request.use_current_folder:
            folder_path = self.dialog_state.current_folder

        matches = search_files_raw(
            request.filename,
            folder_path=folder_path,
            extension=request.extension,
            limit=8,
        )
        return folder_path, matches, None

    def resolve_folder(self, folder_query):
        if not folder_query:
            return None

        normalized = self._clean_entity(folder_query).lower()
        if normalized in SPECIAL_FOLDERS:
            folder_path = os.path.join(os.path.expanduser("~"), SPECIAL_FOLDERS[normalized])
            if os.path.isdir(folder_path):
                return folder_path

        return resolve_folder_path(folder_query)

    def resolve_manage_folder(self, request):
        if request.folder:
            resolved = self.resolve_folder(request.folder)
            if resolved:
                return resolved
        if self.dialog_state.current_folder:
            return self.dialog_state.current_folder

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.isdir(desktop):
            return desktop
        return os.getcwd()

    def _handle_file_action(self, text, args, fallback_actions):
        if self.dialog_state.has_pending_file_request():
            pending = self.dialog_state.pending_file_request
            request = self.parse_lookup_request(text, args, default_actions=fallback_actions)
            if request.filename or request.extension or request.use_selected_file:
                selected_path, error = choose_candidate_from_text(text, pending.candidates)
                if selected_path:
                    actions = pending.requested_actions or fallback_actions
                    return self._finalize_pending_file(selected_path, actions)
                if error and not request.filename:
                    return error

        request = self.parse_lookup_request(text, args, default_actions=fallback_actions)

        if request.use_selected_file and self.dialog_state.selected_file:
            return self._execute_file_actions(self.dialog_state.selected_file, request.requested_actions)
        if self._selected_file_matches_request(request):
            return self._execute_file_actions(self.dialog_state.selected_file, request.requested_actions)

        if not request.filename:
            pending = self.dialog_state.pending_file_request
            if pending and len(pending.candidates) == 1:
                actions = pending.requested_actions or request.requested_actions or fallback_actions
                return self._finalize_pending_file(pending.candidates[0], actions)
            if self.dialog_state.selected_file and request.requested_actions != ["open"]:
                return self._execute_file_actions(self.dialog_state.selected_file, request.requested_actions)
            return f"Which file would you like me to {fallback_actions[0]}?"

        folder_path, matches, error = self.resolve_matches(request)
        if error:
            return error

        if folder_path:
            self.dialog_state.remember_folder(folder_path)

        if not matches:
            return self._format_missing_file_response(request, folder_path)

        if len(matches) > 1:
            self.dialog_state.set_pending_file_request(
                candidates=matches,
                requested_actions=request.requested_actions or fallback_actions,
                folder_path=folder_path,
                filename_query=request.filename,
                extension=request.extension,
            )
            return self._format_candidate_prompt(matches)

        return self._execute_file_actions(matches[0], request.requested_actions or fallback_actions)

    def _build_target_path(self, filename, folder_path, extension):
        normalized = self._clean_entity(filename)
        if not normalized:
            return ""
        if extension and not os.path.splitext(normalized)[1]:
            normalized += extension
        return os.path.abspath(os.path.join(folder_path, normalized))

    def _selected_file_matches_request(self, request):
        selected_file = self.dialog_state.selected_file
        if not selected_file or not request.filename:
            return False

        basename = os.path.basename(selected_file).lower()
        stem, ext = os.path.splitext(basename)
        query = self._clean_entity(request.filename).lower()
        if request.extension and request.extension != ext:
            return False
        return query in {basename, stem}

    def _looks_like_topic_phrase(self, content):
        text = (content or "").strip()
        if not text:
            return False
        if any(ch in text for ch in ".!?\n"):
            return False
        words = text.split()
        if len(words) > 10:
            return False
        return True

    def _generate_topic_content(self, topic):
        topic_clean = re.sub(r"^(?:the|a|an|some|about|on)\s+", "", topic.strip(), flags=re.IGNORECASE)
        if not topic_clean:
            return ""
        router = getattr(self.app, "router", None)
        llm = router.get_llm() if router and hasattr(router, "get_llm") else None
        if llm is None:
            return ""
        prompt = (
            f"Write a clear, well-structured short article about {topic_clean}. "
            "Use a brief title on the first line, then 2-4 short paragraphs. "
            "Keep it under 350 words. Plain text only, no markdown."
        )
        try:
            if hasattr(llm, "create_chat_completion"):
                response = llm.create_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=600,
                    temperature=0.6,
                )
                return (response["choices"][0]["message"]["content"] or "").strip()
            response = llm(prompt, max_tokens=600, temperature=0.6)
            return (response["choices"][0].get("text") or "").strip()
        except Exception as exc:
            logger.warning("LLM topic-content generation failed for '%s': %s", topic_clean, exc)
            return ""

    def _latest_assistant_text(self):
        assistant_context = getattr(self.app, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "latest_assistant_text"):
            return assistant_context.latest_assistant_text()
        return ""

    def _memory(self):
        return getattr(self.app, "memory_service", None) or getattr(self.app, "context_store", None)

    def _workflow_state(self):
        memory = self._memory()
        session_id = getattr(self.app, "session_id", None)
        if not memory or not session_id:
            return {}
        return memory.get_active_workflow(session_id, workflow_name="file_workflow") or {}

    def _save_file_workflow_state(self, state):
        memory = self._memory()
        session_id = getattr(self.app, "session_id", None)
        if not memory or not session_id:
            return
        payload = dict(state or {})
        payload.setdefault("workflow_name", "file_workflow")
        memory.save_workflow_state(session_id, "file_workflow", payload)

    def _target_payload(self, target_path, extension):
        return {
            "path": target_path,
            "filename": os.path.basename(target_path),
            "folder": os.path.dirname(target_path),
            "extension": extension or os.path.splitext(target_path)[1],
        }

    def _extract_folder_name(self, text_lower):
        patterns = (
            r"\b(?:in|inside|from|within)\s+(?:the\s+)?([a-z0-9][a-z0-9 _\-.]+?)\s+folder\b",
            r"\bopen\s+(?:the\s+)?([a-z0-9][a-z0-9 _\-.]+?)\s+folder\b",
            r"\b(?:in|inside|from|within)\s+(desktop|downloads?|documents?|pictures?)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                folder_name = self._clean_entity(match.group(1))
                if folder_name in {"that", "this", "same", "current"}:
                    return ""
                return folder_name
        return ""

    def _extract_filename_query(self, text_lower):
        boundary = r"(?:inside\b|in\b|from\b|within\b|and then\b|then\b|also\b|after that\b|afterwards\b|plus\b|and\b)"
        patterns = (
            rf"\b(?:open|read|summarize|preview|find|search|locate)\s+(?:for\s+)?(?:the\s+)?file\s+([a-z0-9][a-z0-9 _\-.]*?)(?=\s+{boundary}|$)",
            r"\b(?:open|read|summarize|preview|find|search|locate)\s+(?:for\s+)?(?:the\s+)?([a-z0-9][a-z0-9 _\-.]*?)\s+file\b",
            rf"\b(?:file\s+named|file\s+called|named|called)\s+([a-z0-9][a-z0-9 _\-.]*?)(?=\s+{boundary}|$)",
            rf"\b(?:open|read|summarize|preview|find|search|locate)\s+(?:for\s+)?(?:the\s+)?(?:file\s+)?([a-z0-9][a-z0-9 _\-.]*?)(?=\s+{boundary}|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                candidate = self._clean_entity(match.group(1))
                if candidate not in {"it", "them", "that", "this"} and not re.match(r"^(?:it|that|this|them)\b", candidate):
                    return candidate
        return ""

    def _extract_manage_filename(self, text_lower):
        boundary = r"(?:inside\b|in\b|from\b|within\b|and then\b|then\b|also\b|after that\b|afterwards\b|plus\b|and\b)"
        det = r"(?:(?:the|a|an|new)\s+)?"
        patterns = (
            rf"\b(?:to|into|in)\s+{det}file\s+(?:named\s+|called\s+)?([a-z0-9][a-z0-9 _\-.]*?)(?=\s+{boundary}|$)",
            rf"\b(?:to|into|in)\s+{det}([a-z0-9][a-z0-9 _\-.]*?)\s+file(?=\s+{boundary}|$)",
            rf"\b(?:file|document)\s+(?:named|called)\s+([a-z0-9][a-z0-9 _\-.]*?)(?=\s+{boundary}|$)",
            rf"\b(?:create|make)\s+{det}file\s+(?:named|called)?\s*([a-z0-9][a-z0-9 _\-.]*?)(?=\s+with\s+content|\s+{boundary}|$)",
            rf"\b(?:append|add|write|save)\s+.*?\b(?:to|into|in)\s+{det}(?:file|document)\s+(?:named\s+|called\s+)?([a-z0-9][a-z0-9 _\-.]*?)(?=\s+{boundary}|$)",
            rf"\b(?:append|add|write|save)\s+.*?\b(?:to|into|in)\s+{det}([a-z0-9][a-z0-9 _\-.]*?)\s+(?:file|document)(?=\s+{boundary}|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return self._clean_entity(match.group(1))
        return ""

    def _extract_manage_content(self, text):
        det = r"(?:(?:the|a|an|new)\s+)?"
        patterns = (
            r"\bwith content\b[:\s]+(.+)$",
            r"\bthat says\b[:\s]+(.+)$",
            rf"\bwrite\b[:\s]+(.+?)\s+\b(?:to|into|in)\s+{det}(?:file|document)\b",
            rf"\bappend\b[:\s]+(.+?)\s+\b(?:to|into|in)\s+{det}(?:file|document)\b",
            rf"\badd\b[:\s]+(.+?)\s+\bto\s+{det}(?:file|document)\b",
            r"\badd\b[:\s]+(.+)$",
            r"\bappend\b[:\s]+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip(" \n\t\"'")
        return ""

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

    def _detect_manage_action(self, text_lower):
        if re.search(r"\b(?:append|add)\b", text_lower):
            return "append"
        if re.search(r"\b(?:write|save)\b", text_lower):
            return "write"
        if re.search(r"\bread\b", text_lower):
            return "read"
        return "create"

    def _wants_last_assistant_message(self, text_lower, content):
        if content:
            return False
        return bool(
            re.search(
                r"\b(?:save|write|append|add)\s+(?:that|this|it|the answer|the response|my answer|your answer)\b",
                text_lower,
            )
        )

    def _clean_entity(self, value):
        value = (value or "").strip(" .,!?:;\"'")
        value = re.sub(r"\s+", " ", value)
        return value

    def _format_missing_file_response(self, request, folder_path):
        if folder_path:
            folder_name = os.path.basename(folder_path)
            message = f"FAILURE: I couldn't find a file named '{request.filename}' in the {folder_name} folder."
            self.dialog_state.remember_folder(folder_path)
        else:
            message = f"FAILURE: I couldn't find any file named '{request.filename}'."

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
