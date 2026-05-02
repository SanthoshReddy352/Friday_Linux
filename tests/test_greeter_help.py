import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.capability_registry import CapabilityRegistry
from core.extensions.protocol import ExtensionContext
import modules.greeter.extension as greeter_plugin
from modules.greeter.extension import GreeterExtension


def test_greeter_help_uses_registered_capabilities():
    registry = CapabilityRegistry()
    ctx = ExtensionContext(registry=registry, events=MagicMock(), consent=MagicMock(), config=MagicMock())
    plugin = GreeterExtension()
    plugin.load(ctx)

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


def test_startup_greeting_wishes_by_time_then_reads_unfinished_tasks(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 40, 0)

    monkeypatch.setattr(greeter_plugin, "datetime", FixedDatetime)
    task_manager = MagicMock()
    task_manager.get_unfinished_task_briefing.return_value = (
        "You have 1 unfinished reminder.\nToday at 4:10 PM: purchase a gift"
    )
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: task_manager if name == "task_manager" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx

    response = plugin.handle_startup()

    assert response.startswith("Good afternoon, sir.")
    assert "FRIDAY is online and ready." in response
    assert "You have 1 unfinished reminder." in response
    assert "Today at 4:10 PM: purchase a gift" in response


def test_startup_greeting_supports_night(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 22, 30, 0)

    monkeypatch.setattr(greeter_plugin, "datetime", FixedDatetime)
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: None
    plugin = GreeterExtension()
    plugin.ctx = ctx

    response = plugin.handle_startup()

    assert response == "Good night, sir. FRIDAY is online and ready."
