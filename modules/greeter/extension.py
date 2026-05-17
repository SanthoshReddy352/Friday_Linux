import random
from datetime import datetime

from core.extensions.protocol import Extension, ExtensionContext
from core.extensions.decorators import capability
from core.logger import logger

from modules.onboarding.extension import (
    is_completed as onboarding_is_completed,
    read_profile as read_user_profile,
)
from modules.onboarding.workflow import (
    WORKFLOW_NAME as ONBOARDING_WORKFLOW_NAME,
    first_question as onboarding_first_question,
    initial_state as onboarding_initial_state,
)

_SHUTDOWN_PHRASES = frozenset({
    "goodbye", "bye", "good bye", "goobye", "goodby", "exit", "quit",
    "exit program", "close assistant", "switch off", "see you", "see ya",
    "later", "farewell", "close", "shutdown", "shut down", "stop",
})


INTERNAL_HELP_TOOL_NAMES = {
    "greet",
    "show_capabilities",
    "confirm_yes",
    "confirm_no",
    "select_file_candidate",
    "shutdown_assistant",
    "resume_session",
    "start_fresh_session",
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
        term = self._address_term()
        jarvis_flair = [
            f"{time_greeting}, {term}. How can I assist you today?",
            f"At your service, {term}. What's on the agenda?",
            f"Always a pleasure to see you, {term}. Ready for commands.",
            f"Online and ready, {term}. What can I do for you?",
            f"Systems are green. How may I help you today, {term}?",
        ]
        return random.choice(jarvis_flair)

    @capability(
        name="resume_session",
        description=(
            "Resume the previous session. Use ONLY when FRIDAY asked at startup whether to continue "
            "from the last session and the user agrees — says yes, sure, continue, absolutely, yep, "
            "pick up where we left off, or similar affirmations."
        ),
    )
    def handle_resume_session(self):
        context_store = self.ctx.get_service("context_store")
        term = self._address_term()
        if not context_store:
            return f"Back in action, {term}. What can I do for you?"

        facts = {f["key"]: f["value"] for f in context_store.get_facts_by_namespace("system")}
        if facts.get("has_pending_session") != "true":
            return f"Ready for anything, {term}. What can I do for you today?"

        summary = facts.get("last_session_summary", "")
        context_store.store_fact("has_pending_session", "", namespace="system")
        context_store.store_fact("last_session_summary", "", namespace="system")

        if summary:
            # Store the resumed context so subsequent follow-ups ("answer it", "continue")
            # have immediate access to what was discussed — avoids re-injecting into history.
            context_store.store_fact("resumed_session_context", summary, namespace="system")

            lines = [l.strip() for l in summary.split("\n") if l.strip()]
            last_user = ""
            for line in reversed(lines):
                if line.lower().startswith("user:"):
                    candidate = line[5:].strip()
                    if candidate.lower() not in _SHUTDOWN_PHRASES:
                        last_user = candidate
                        break
            if last_user:
                topic = (last_user[:70] + "…") if len(last_user) > 70 else last_user
                return f"Picking up where we left off, {term}. You were asking: \"{topic}\". Go ahead."

        return f"Back on track, {term}. What would you like to do?"

    @capability(
        name="start_fresh_session",
        description=(
            "Start a new session and discard the previous one. Use ONLY when FRIDAY asked at startup "
            "whether to continue from the last session and the user declines — says no, fresh start, "
            "new session, never mind, start over, different topic, or similar."
        ),
    )
    def handle_fresh_session(self):
        context_store = self.ctx.get_service("context_store")
        if context_store:
            facts = {f["key"]: f["value"] for f in context_store.get_facts_by_namespace("system")}
            if facts.get("has_pending_session") == "true":
                context_store.store_fact("has_pending_session", "", namespace="system")
                context_store.store_fact("last_session_summary", "", namespace="system")
            context_store.store_fact("resumed_session_context", "", namespace="system")

        term = self._address_term()
        fresh_phrases = [
            f"Of course, {term}. Fresh start — how can I help you today?",
            f"Understood, {term}. Starting clean. What's on your mind?",
            f"Sure thing, {term}. New session. What can I do for you?",
            f"Right, {term}. Clean slate. Go ahead.",
        ]
        return random.choice(fresh_phrases)

    @capability(
        name="show_capabilities",
        description=(
            "List everything FRIDAY can do. Use ONLY when the user explicitly asks "
            "'what can you do', 'show your capabilities', 'list your tools', "
            "'show commands', or says a bare 'help' with nothing else. "
            "Do NOT use for 'help me write X', 'help me fix Y', or any task request."
        ),
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
        lines = [f"Here's what I can do right now, {self._address_term()}:"]

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
        """Vocal greeting when the app first loads.

        First-run path: if no `user_profile.name` is stored and onboarding
        hasn't been marked completed, kick off the OnboardingWorkflow by
        writing its initial state and returning the first question as the
        spoken greeting. The next user turn lands in `OnboardingWorkflow`
        via `WorkflowOrchestrator.continue_active`.
        """
        context_store = self.ctx.get_service("context_store")

        # First-run onboarding takes priority over any other startup path.
        if self._should_start_onboarding(context_store):
            if self._begin_onboarding():
                question = onboarding_first_question()
                logger.info("[greeter] First-run onboarding triggered: %s", question)
                return question
            # If we couldn't begin (no memory/session), fall through to the
            # normal greeting — at worst the user sees "sir" and can answer
            # questions later via update_user_profile.

        term = self._address_term()
        greeting = f"{self._get_time_of_day_greeting()}, {term}. FRIDAY is online and ready."

        if context_store:
            try:
                facts = {f["key"]: f["value"] for f in context_store.get_facts_by_namespace("system")}
                next_greeting = facts.get("next_startup_greeting", "")
                has_pending = facts.get("has_pending_session") == "true"
                summary = facts.get("last_session_summary", "")

                # Validate: only show a continuation greeting if there is real session content.
                # This clears stale flags left over from previous runs.
                summary_is_valid = bool(summary) and len(
                    [l for l in summary.split("\n") if l.lower().startswith(("user:", "assistant:"))]
                ) >= 4

                if next_greeting and has_pending and summary_is_valid:
                    greeting = next_greeting.replace("{time_greeting}", self._get_time_of_day_greeting())
                    # Replace any literal "sir" in stored greetings with the user's name.
                    if term != "sir":
                        greeting = greeting.replace(", sir.", f", {term}.").replace(", sir,", f", {term},")
                    context_store.store_fact("next_startup_greeting", "", namespace="system")
                elif has_pending and summary_is_valid:
                    # LLM greeting didn't finish in time — use plain fallback
                    greeting = f"{self._get_time_of_day_greeting()}, {term}. Want to pick up where we left off?"
                    context_store.store_fact("next_startup_greeting", "", namespace="system")
                else:
                    # No valid pending session — clear any stale flags
                    if has_pending:
                        context_store.store_fact("has_pending_session", "", namespace="system")
                        context_store.store_fact("last_session_summary", "", namespace="system")
                        context_store.store_fact("next_startup_greeting", "", namespace="system")
                    # Always clear any resumed context from a previous session at startup
                    context_store.store_fact("resumed_session_context", "", namespace="system")
            except Exception as e:
                logger.error(f"Failed to fetch next startup greeting: {e}")

        task_briefing = self._get_unfinished_task_briefing()
        if task_briefing:
            greeting = f"{greeting}\n{task_briefing}"
        logger.info(f"[greeter] Startup greeting: {greeting}")
        return greeting

    def get_pause_phrase(self):
        """Vocal feedback when pausing (reactor click)."""
        term = self._address_term()
        pause_phrases = [
            f"I am going offline, {term}.",
            "Suspending current protocols.",
            f"Standing by, {term}.",
            "Going into hibernation mode.",
            "Powering down interaction layers.",
        ]
        return random.choice(pause_phrases)

    def get_unpause_phrase(self):
        """Vocal feedback when unpausing (reactor click)."""
        term = self._address_term()
        unpause_phrases = [
            f"Back online, {term}.",
            "At your service once again.",
            "Systems reactivated.",
            f"Ready and waiting, {term}.",
            "Protocols restored. How can I help?",
        ]
        return random.choice(unpause_phrases)

    # --- Internal Helpers ---

    def _fallback_help(self):
        return (
            f"Here's what I can do, {self._address_term()}:\n"
            "• Launch apps and control the system.\n"
            "• Search, open, read, and summarize files.\n"
            "• Set reminders, save notes, and answer general questions.\n"
            "• Interrupt me by saying 'Friday stop' or asking your next question while I'm speaking."
        )

    # --- Onboarding / profile helpers ---

    def _address_term(self) -> str:
        """How FRIDAY should address the user — name when known, else 'sir'."""
        store = self.ctx.get_service("context_store")
        if store is None:
            return "sir"
        profile = read_user_profile(store)
        name = (profile.get("name") or "").strip()
        return name or "sir"

    def _should_start_onboarding(self, context_store) -> bool:
        """First-run trigger: no name on file AND onboarding never completed."""
        if context_store is None:
            return False
        if onboarding_is_completed(context_store):
            return False
        profile = read_user_profile(context_store)
        return not (profile.get("name") or "").strip()

    def _begin_onboarding(self) -> bool:
        """Persist the initial OnboardingWorkflow state so the next user turn
        is routed to it by `WorkflowOrchestrator.continue_active`. Returns
        True on success.
        """
        memory = self.ctx.get_service("memory_service") or self.ctx.get_service("context_store")
        session_id = self.ctx.get_service("session_id")
        if memory is None or not session_id:
            logger.warning(
                "[greeter] Cannot start onboarding — memory=%s session_id=%s",
                bool(memory), bool(session_id),
            )
            return False
        try:
            memory.save_workflow_state(
                session_id, ONBOARDING_WORKFLOW_NAME, onboarding_initial_state(),
            )
            return True
        except Exception as exc:
            logger.warning("[greeter] Failed to seed onboarding workflow: %s", exc)
            return False

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
