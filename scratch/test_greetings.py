import os
import sys
import time

sys.path.append("/home/tricky/Friday_Linux")

from core.context_store import ContextStore
from modules.system_control.plugin import SystemControlPlugin
from modules.greeter.extension import GreeterExtension
from core.extensions.protocol import ExtensionContext

class MockRouter:
    def __init__(self):
        self.session_id = "test_session"
    def get_llm(self):
        class MockLLM:
            def create_chat_completion(self, messages, max_tokens, temperature):
                return {"choices": [{"message": {"content": "This is a mock LLM response."}}]}
        return MockLLM()
    def register_tool(self, tool_def, handler):
        pass

class MockEventBus:
    def publish(self, topic, data):
        print(f"Event published: {topic} {data}")

class MockApp:
    def __init__(self):
        self.router = MockRouter()
        self.context_store = ContextStore(db_path="/tmp/test_friday_context.db")
        self.event_bus = MockEventBus()
        self.file_controller = None

class MockRegistry:
    def list_capabilities(self):
        return []

class MockCtx(ExtensionContext):
    def __init__(self, app):
        self.app = app
        self._registry = MockRegistry()
    @property
    def registry(self):
        return self._registry
    def get_service(self, name):
        if name == "context_store":
            return self.app.context_store
        return None
    def register_capability(self, spec, handler, metadata=None):
        pass

def main():
    if os.path.exists("/tmp/test_friday_context.db"):
        os.remove("/tmp/test_friday_context.db")

    app = MockApp()
    app.context_store.start_session()
    app.context_store.append_turn("test_session", "user", "Hello Friday, can you explain quantum mechanics?")
    app.context_store.append_turn("test_session", "assistant", "Sure, quantum mechanics is the study of...")

    sys_plugin = SystemControlPlugin(app)
    greeter = GreeterExtension()
    ctx = MockCtx(app)
    greeter.load(ctx)

    # 1. Test Shutdown
    print("Testing shutdown...")
    farewell = sys_plugin.handle_shutdown("bye", {})
    print(f"Farewell generated: {farewell}")

    print("Waiting 6 seconds for async next greeting to generate...")
    time.sleep(6)

    # 2. Test Startup
    print("Testing startup...")
    startup = greeter.handle_startup()
    print(f"Startup generated: {startup}")

if __name__ == "__main__":
    main()
