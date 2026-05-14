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


def _make_context_store_with_facts(facts_dict):
    """Helper: returns a mock context_store whose get_facts_by_namespace returns facts_dict."""
    store = MagicMock()
    store.get_facts_by_namespace.return_value = [
        {"key": k, "value": v} for k, v in facts_dict.items()
    ]
    return store


_VALID_SUMMARY = (
    "user: can you help me debug this Python script\n"
    "assistant: Sure, let me take a look.\n"
    "user: the error is on line 42\n"
    "assistant: Got it, that's a TypeError."
)


def test_startup_uses_pending_session_greeting(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 14, 0, 0)

    monkeypatch.setattr(greeter_plugin, "datetime", FixedDatetime)
    store = _make_context_store_with_facts({
        "next_startup_greeting": "{time_greeting}, sir. We were fixing a bug — want to continue?",
        "has_pending_session": "true",
        "last_session_summary": _VALID_SUMMARY,
    })
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: store if name == "context_store" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx

    response = plugin.handle_startup()

    assert "Good afternoon" in response
    assert "fixing a bug" in response
    assert "want to continue" in response
    store.store_fact.assert_called_with("next_startup_greeting", "", namespace="system")


def test_startup_fallback_greeting_when_no_llm_greeting(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 9, 0, 0)

    monkeypatch.setattr(greeter_plugin, "datetime", FixedDatetime)
    store = _make_context_store_with_facts({
        "has_pending_session": "true",
        "last_session_summary": _VALID_SUMMARY,
    })
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: store if name == "context_store" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx

    response = plugin.handle_startup()

    assert "Good morning" in response
    assert "pick up where we left off" in response.lower()


def test_resume_session_skips_goodbye_as_topic():
    store = _make_context_store_with_facts({
        "has_pending_session": "true",
        "last_session_summary": (
            "user: what are programming languages\n"
            "assistant: Programming languages are tools we use to tell computers what to do.\n"
            "user: can you give me an example\n"
            "assistant: Sure — Python is great for beginners.\n"
            "user: goodbye\n"
            "assistant: Goodbye sir, talk to you later."
        ),
    })
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: store if name == "context_store" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx
    plugin.load(ctx)

    response = plugin.handle_resume_session()

    assert "goodbye" not in response.lower()
    assert "programming languages" in response.lower() or "example" in response.lower() or "left off" in response.lower()


def test_resume_session_with_pending_session():
    store = _make_context_store_with_facts({
        "has_pending_session": "true",
        "last_session_summary": "user: can you help me write a Python script\nassistant: Sure, here's how…",
    })
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: store if name == "context_store" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx
    plugin.load(ctx)

    response = plugin.handle_resume_session()

    assert "left off" in response.lower() or "picking up" in response.lower()
    assert "Python script" in response or "asking" in response.lower()
    store.store_fact.assert_any_call("has_pending_session", "", namespace="system")


def test_resume_session_no_pending_session():
    store = _make_context_store_with_facts({})
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: store if name == "context_store" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx
    plugin.load(ctx)

    response = plugin.handle_resume_session()

    assert "Ready" in response or "today" in response.lower()


def test_fresh_session_clears_pending_flags():
    store = _make_context_store_with_facts({
        "has_pending_session": "true",
        "last_session_summary": "user: hello\nassistant: hi",
    })
    ctx = ExtensionContext(registry=MagicMock(), events=MagicMock(), consent=MagicMock(), config=MagicMock())
    ctx.get_service = lambda name: store if name == "context_store" else None
    plugin = GreeterExtension()
    plugin.ctx = ctx
    plugin.load(ctx)

    response = plugin.handle_fresh_session()

    assert any(word in response.lower() for word in ["fresh", "clean", "new", "start"])
    store.store_fact.assert_any_call("has_pending_session", "", namespace="system")
    store.store_fact.assert_any_call("last_session_summary", "", namespace="system")


def test_resume_and_fresh_session_not_in_help():
    registry = CapabilityRegistry()
    ctx = ExtensionContext(registry=registry, events=MagicMock(), consent=MagicMock(), config=MagicMock())
    plugin = GreeterExtension()
    plugin.load(ctx)

    registry.register_tool(
        {"name": "launch_app", "description": "Launch apps.", "parameters": {}},
        lambda text, args: "ok",
    )
    response = plugin.handle_help()

    assert "resume_session" not in response
    assert "start_fresh_session" not in response
