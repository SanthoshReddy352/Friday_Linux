import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.capability_registry import CapabilityRegistry
from modules.greeter.plugin import GreeterPlugin


def test_greeter_help_uses_registered_capabilities():
    registry = CapabilityRegistry()
    app = SimpleNamespace(router=MagicMock(), capability_registry=registry)
    plugin = GreeterPlugin(app)

    registry.register_tool(
        {"name": "launch_app", "description": "Launch apps.", "parameters": {}},
        lambda text, args: "ok",
    )
    registry.register_tool(
        {"name": "search_file", "description": "Find files.", "parameters": {}},
        lambda text, args: "ok",
    )
    registry.register_tool(
        {"name": "get_weather", "description": "Check weather.", "parameters": {}},
        lambda text, args: "ok",
        metadata={"connectivity": "online", "permission_mode": "ask_first"},
    )
    registry.register_tool(
        {"name": "llm_chat", "description": "Answer questions.", "parameters": {}},
        lambda text, args: "ok",
    )
    registry.register_tool(
        {"name": "enable_voice", "description": "Enable voice.", "parameters": {}},
        lambda text, args: "ok",
    )

    response = plugin.handle_help()

    assert "Apps and system - launch apps" in response
    assert "Files - find files" in response
    assert "Online services - check weather" in response
    assert "General Q and A - answer open-ended questions" in response
    assert "Online actions stay opt-in" in response
    assert "Interrupt me anytime" in response
    assert "shutdown_assistant" not in response
