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
        return "Hello there! I am FRIDAY. How can I help you today?"

    def handle_help(self):
        return (
            "Here's what I can do:\n"
            "• Launch apps — 'open firefox', 'launch calculator'\n"
            "• System info — 'system status', 'battery', 'cpu usage'\n"
            "• Volume control — 'volume up', 'volume down', 'mute'\n"
            "• Screenshot — 'take a screenshot'\n"
            "• File search — 'find file report.pdf'\n"
            "• Reminders — 'remind me to call John in 5 minutes'\n"
            "• Notes — 'save note: buy milk'\n"
            "• General Q&A — just ask me anything!"
        )


def setup(app):
    return GreeterPlugin(app)
