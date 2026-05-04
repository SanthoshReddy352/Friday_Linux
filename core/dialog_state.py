import os
from dataclasses import dataclass, field


@dataclass
class PendingFileRequest:
    candidates: list[str] = field(default_factory=list)
    requested_actions: list[str] = field(default_factory=list)
    folder_path: str | None = None
    filename_query: str = ""
    extension: str | None = None


@dataclass
class PendingClarification:
    action_text: str = ""
    prompt: str = ""
    cancel_message: str = ""


@dataclass
class DialogState:
    current_folder: str | None = None
    current_folder_name: str | None = None
    selected_file: str | None = None
    last_listing: list[str] = field(default_factory=list)
    last_error: str | None = None
    pending_file_request: PendingFileRequest | None = None
    pending_clarification: PendingClarification | None = None

    def remember_folder(self, folder_path):
        self.current_folder = folder_path
        self.current_folder_name = os.path.basename(folder_path) if folder_path else None

    def remember_file(self, filepath):
        self.selected_file = filepath
        if filepath:
            self.remember_folder(os.path.dirname(filepath))

    def remember_listing(self, listing):
        self.last_listing = list(listing or [])

    def remember_error(self, message):
        self.last_error = message

    def set_pending_file_request(
        self,
        candidates,
        requested_actions=None,
        folder_path=None,
        filename_query="",
        extension=None,
    ):
        self.pending_file_request = PendingFileRequest(
            candidates=list(candidates or []),
            requested_actions=list(requested_actions or []),
            folder_path=folder_path,
            filename_query=filename_query,
            extension=extension,
        )
        if folder_path:
            self.remember_folder(folder_path)

    def clear_pending_file_request(self):
        self.pending_file_request = None

    def has_pending_file_request(self):
        return bool(self.pending_file_request and self.pending_file_request.candidates)

    def set_pending_clarification(self, action_text, prompt="", cancel_message=""):
        cleaned_action = (action_text or "").strip()
        if not cleaned_action:
            self.pending_clarification = None
            return
        self.pending_clarification = PendingClarification(
            action_text=cleaned_action,
            prompt=(prompt or "").strip(),
            cancel_message=(cancel_message or "").strip(),
        )

    def clear_pending_clarification(self):
        self.pending_clarification = None

    def has_pending_clarification(self):
        return bool(self.pending_clarification and self.pending_clarification.action_text)
