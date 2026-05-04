import random
from datetime import datetime

from core.extensions.protocol import Extension, ExtensionContext
from core.extensions.decorators import capability
from core.logger import logger


INTERNAL_HELP_TOOL_NAMES = {
    "greet",
    "show_help",
    "confirm_yes",
    "confirm_no",
    "select_file_candidate",
    "shutdown_assistant",
}


HELP_CATEGORY_SPECS = (
    {
        "title": "Apps and system",
        "items": (
            {"tools": {"launch_app"}, "phrase": "launch apps", "example": "open firefox"},
            {"tools": {"get_system_status", "get_friday_status"}, "phrase": "check system status", "example": "system status"},
            {"tools": {"get_battery"}, "phrase": "check battery", "example": "battery"},
            {"tools": {"get_cpu_ram"}, "phrase": "show CPU and RAM usage", "example": "cpu usage"},
            {"tools": {"set_volume"}, "phrase": "control volume", "example": "volume up"},
            {"tools": {"take_screenshot"}, "phrase": "take screenshots", "example": "take a screenshot"},
        ),
    },
    {
        "title": "Files",
        "items": (
            {"tools": {"search_file"}, "phrase": "find files", "example": "find file report.pdf"},
            {"tools": {"open_file"}, "phrase": "open files", "example": "open file notes.md"},
            {"tools": {"read_file", "read_file_content"}, "phrase": "read file contents", "example": "read file todo.txt"},
            {"tools": {"summarize_file"}, "phrase": "summarize documents", "example": "summarize file prd.md"},
            {"tools": {"manage_file"}, "phrase": "create or update text files", "example": "save this as meeting_notes.md"},
            {"tools": {"list_folder_contents", "open_folder"}, "phrase": "browse folders", "example": "open the downloads folder"},
        ),
    },
    {
        "title": "Reminders and notes",
        "items": (
            {"tools": {"set_reminder"}, "phrase": "set reminders", "example": "remind me to call John in 5 minutes"},
            {"tools": {"save_note"}, "phrase": "save notes", "example": "save note buy milk"},
            {"tools": {"read_notes"}, "phrase": "read back saved notes", "example": "read my notes"},
            {
                "tools": {"get_time", "get_date", "get_current_time", "get_current_date", "get_current_datetime"},
                "phrase": "tell the date and time",
                "example": "what time is it",
            },
        ),
    },
    {
        "title": "Browser and web",
        "items": (
            {"tools": {"open_browser_url"}, "phrase": "open websites", "example": "open youtube.com"},
            {"tools": {"google_search"}, "phrase": "search the web", "example": "search Google for Linux audio fixes"},
            {"tools": {"play_youtube"}, "phrase": "play YouTube videos", "example": "play lo-fi beats on YouTube"},
            {"tools": {"play_youtube_music"}, "phrase": "play YouTube Music", "example": "play Numb on YouTube Music"},
            {"tools": {"browser_media_control"}, "phrase": "control browser playback", "example": "pause the music"},
        ),
    },
    {
        "title": "Online services",
        "items": (
            {"tools": {"get_weather", "get_current_location_weather"}, "phrase": "check weather", "example": "what's the weather in Mumbai"},
            {"tools": {"check_unread_emails", "get_recent_emails"}, "phrase": "check email", "example": "check unread emails"},
        ),
    },
    {
        "title": "Memory and preferences",
        "items": (
            {"tools": {"remember_fact"}, "phrase": "remember facts", "example": "remember that my favorite editor is VS Code"},
            {"tools": {"retrieve_memory", "list_all_memories", "forget_fact"}, "phrase": "recall or forget stored memories", "example": "what do you remember about me"},
            {"tools": {"toggle_clap_trigger"}, "phrase": "toggle the clap trigger", "example": "turn off the clap trigger"},
        ),
    },
    {
        "title": "Voice and live tools",
        "items": (
            {"tools": {"enable_voice", "disable_voice"}, "phrase": "control voice listening", "example": "disable voice listening"},
            {"tools": {"start_live_vision"}, "phrase": "start live vision", "example": "start live vision"},
        ),
    },
    {
        "title": "General Q and A",
        "items": (
            {"tools": {"llm_chat"}, "phrase": "answer open-ended questions", "example": "just ask me anything"},
        ),
    },
)


class GreeterExtension(Extension):
    name = "Greeter"

    def load(self, ctx: ExtensionContext) -> None:
        self.ctx = ctx
        
        # Register capabilities declared with @capability
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, "__capability_spec__"):
                spec = attr.__capability_spec__
                meta = getattr(attr, "__capability_meta__", {})
                
                # Create a wrapper that takes (text, args) to match expected handler signature
                # But since our tools don't use args, we just ignore them.
                def make_handler(func):
                    return lambda t, a: func()
                
                ctx.register_capability(spec, make_handler(attr), metadata=meta)
                
        logger.info("GreeterExtension loaded.")

    def unload(self) -> None:
        pass

    @capability(
        name="greet",
        description="Respond to a greeting. Use when the user says hello, hi, hey, or greets FRIDAY.",
    )
    def handle_greeting(self):
        """Pick a natural, varied greeting."""
        time_greeting = self._get_time_of_day_greeting()
        jarvis_flair = [
            f"{time_greeting}, sir. How can I assist you today?",
            "At your service, sir. What's on the agenda?",
            "Always a pleasure to see you, sir. Ready for commands.",
            "Online and ready, sir. What can I do for you?",
            "Systems are green. How may I help you today, sir?"
        ]
        return random.choice(jarvis_flair)

    @capability(
        name="show_help",
        description="Show a list of things FRIDAY can do. Use when the user asks for help or what you can do.",
    )
    def handle_help(self):
        registry = self.ctx.registry
        
        descriptors = [
            descriptor
            for descriptor in registry.list_capabilities()
            if descriptor.name not in INTERNAL_HELP_TOOL_NAMES
        ]
        if not descriptors:
            return self._fallback_help()

        names = {descriptor.name for descriptor in descriptors}
        lines = ["Here's what I can do right now, sir:"]

        for category in HELP_CATEGORY_SPECS:
            phrases = []
            examples = []
            for item in category["items"]:
                if not (names & item["tools"]):
                    continue
                phrases.append(item["phrase"])
                examples.append(item["example"])
            if not phrases:
                continue
            summary = self._join_human(phrases)
            example_text = self._format_examples(examples[:2])
            line = f"• {category['title']} - {summary}"
            if example_text:
                line += f". Try {example_text}"
            lines.append(line)

        online_tools = [
            descriptor for descriptor in descriptors
            if getattr(descriptor, "connectivity", "local") == "online" or getattr(descriptor, "permission_mode", "always_ok") == "ask_first"
        ]
        if online_tools:
            lines.append("• Online actions stay opt-in. If a task needs the web or browser automation, I'll ask first.")

        if names & {"enable_voice", "disable_voice"}:
            lines.append("• Interrupt me anytime by saying 'Friday stop', 'wait', or by asking your next question while I'm speaking.")

        return "\n".join(lines) if len(lines) > 1 else self._fallback_help()

    # --- Standard Optional Extension Hooks ---

    def handle_startup(self):
        """Vocal greeting when the app first loads."""
        greeting = f"{self._get_time_of_day_greeting()}, sir. FRIDAY is online and ready."
        task_briefing = self._get_unfinished_task_briefing()
        if task_briefing:
            return f"{greeting}\n{task_briefing}"
        return greeting

    def get_pause_phrase(self):
        """Vocal feedback when pausing (reactor click)."""
        pause_phrases = [
            "I am going offline, sir.",
            "Suspending current protocols.",
            "Standing by, sir.",
            "Going into hibernation mode.",
            "Powering down interaction layers."
        ]
        return random.choice(pause_phrases)

    def get_unpause_phrase(self):
        """Vocal feedback when unpausing (reactor click)."""
        unpause_phrases = [
            "Back online, sir.",
            "At your service once again.",
            "Systems reactivated.",
            "Ready and waiting, sir.",
            "Protocols restored. How can I help?"
        ]
        return random.choice(unpause_phrases)

    # --- Internal Helpers ---

    def _fallback_help(self):
        return (
            "Here's what I can do, sir:\n"
            "• Launch apps and control the system.\n"
            "• Search, open, read, and summarize files.\n"
            "• Set reminders, save notes, and answer general questions.\n"
            "• Interrupt me by saying 'Friday stop' or asking your next question while I'm speaking."
        )

    def _format_examples(self, examples):
        cleaned = [f"'{example}'" for example in examples if example]
        if not cleaned:
            return ""
        return self._join_human(cleaned)

    def _join_human(self, items):
        unique_items = []
        seen = set()
        for item in items:
            if item in seen:
                continue
            unique_items.append(item)
            seen.add(item)
        if not unique_items:
            return ""
        if len(unique_items) == 1:
            return unique_items[0]
        if len(unique_items) == 2:
            return f"{unique_items[0]} and {unique_items[1]}"
        return f"{', '.join(unique_items[:-1])}, and {unique_items[-1]}"

    def _get_time_of_day_greeting(self):
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Good morning"
        elif 12 <= hour < 17:
            return "Good afternoon"
        elif 17 <= hour < 21:
            return "Good evening"
        return "Good night"

    def _get_unfinished_task_briefing(self):
        manager = self.ctx.get_service("task_manager")
        if manager and hasattr(manager, "get_unfinished_task_briefing"):
            return manager.get_unfinished_task_briefing()
        return ""
