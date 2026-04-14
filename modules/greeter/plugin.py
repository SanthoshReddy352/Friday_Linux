import random
from datetime import datetime
from core.plugin_manager import FridayPlugin
from core.logger import logger

class GreeterPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "Greeter"
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "greet",
            "description": "Respond to a greeting. Use when the user says hello, hi, hey, or greets FRIDAY.",
            "parameters": {}
        }, lambda t, a: self.handle_greeting())

        self.app.router.register_tool({
            "name": "show_help",
            "description": "Show a list of things FRIDAY can do. Use when the user asks for help or what you can do.",
            "parameters": {}
        }, lambda t, a: self.handle_help())

        logger.info("GreeterPlugin loaded.")

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

    def handle_startup(self):
        """Vocal greeting when the app first loads."""
        startup_phrases = [
            "Online and ready, sir.",
            "At your service, sir. All protocols are active.",
            "Welcome back, sir. Systems are at one hundred percent.",
            "Hello sir. I am ready to assist you."
        ]
        return random.choice(startup_phrases)

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

    def handle_help(self):
        return (
            "Here's what I can do, sir:\n"
            "• Launch apps — 'open firefox', 'launch calculator'\n"
            "• System info — 'system status', 'battery', 'cpu usage'\n"
            "• Volume control — 'volume up', 'volume down', 'mute'\n"
            "• Screenshot — 'take a screenshot'\n"
            "• File search — 'find file report.pdf'\n"
            "• Reminders — 'remind me to call John in 5 minutes'\n"
            "• Notes — 'save note: buy milk'\n"
            "• General Q&A — just ask me anything!"
        )

    def _get_time_of_day_greeting(self):
        hour = datetime.now().hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

def setup(app):
    return GreeterPlugin(app)
