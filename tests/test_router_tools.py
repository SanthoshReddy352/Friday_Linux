"""
tests/test_router_tools.py
Tests for the upgraded tool-calling CommandRouter.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock
from core.dialog_state import DialogState
from core.router import CommandRouter
from modules.llm_chat.plugin import LLMChatPlugin


@pytest.fixture
def router():
    """Router with no LLM loaded (keyword/fallback path)."""
    event_bus = MagicMock()
    r = CommandRouter(event_bus)
    r.llm = None  # force fallback path
    return r


def test_register_tool_and_invoke(router):
    """Tool registered with register_tool should be callable via keyword fallback."""
    called_with = {}

    def my_handler(text, args):
        called_with['text'] = text
        called_with['args'] = args
        return "tool_ok"

    router.register_tool({
        "name": "my_tool",
        "description": "A test tool.",
        "parameters": {"param": "string"}
    }, my_handler)

    result = router.process_text("my tool do something")
    assert result == "tool_ok"
    assert called_with['text'] == "my tool do something"


def test_legacy_register_handler(router):
    """Legacy register_handler should still work."""
    def legacy(text):
        return "legacy_ok"

    router.register_handler(["oldcmd", "oldcommand"], legacy)
    result = router.process_text("oldcmd now")
    assert result == "legacy_ok"


def test_no_match_returns_fallback(router):
    """Unrecognised input should return the fallback message."""
    result = router.process_text("xyzzy teleport")
    assert "didn't understand" in result.lower()


def test_router_starts_without_loading_llm(router):
    """Router startup should remain cold until chat/LLM routing actually needs the model."""
    assert router.llm is None
    assert router._llm_load_failed is False


def test_llm_json_parsing(router):
    """Simulate a Gemma response and verify the router dispatches correctly."""
    captured = {}

    def handler(text, args):
        captured['args'] = args
        return "dispatched"

    router.register_tool({
        "name": "launch_app",
        "description": "Launch an app.",
        "parameters": {"app_name": "string"}
    }, handler)

    # Mock LLM to return a well-formed tool-call JSON
    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"tool": "launch_app", "args": {"app_name": "firefox"}}'}}]
    }
    router.llm = mock_llm
    router.enable_llm_tool_routing = True

    result = router.process_text("could you run the web browser for me")
    assert result == "dispatched"
    assert captured['args'].get("app_name") == "firefox"


def test_llm_bad_json_falls_back(router):
    """If LLM returns malformed JSON, keyword fallback should still work."""
    def handler(text, args):
        return "fallback_hit"

    router.register_tool({
        "name": "greet",
        "description": "Greet user.",
        "parameters": {}
    }, handler)

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {"choices": [{"message": {"content": "NOT JSON AT ALL"}}]}
    router.llm = mock_llm
    router.enable_llm_tool_routing = True

    result = router.process_text("greet me")
    assert result == "fallback_hit"


def test_llm_can_return_chat_reply(router):
    router.register_tool(
        {"name": "llm_chat", "description": "Chat.", "parameters": {"query": "string"}},
        lambda t, a: "fallback chat",
    )
    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"mode":"chat","reply":"I can help with that."}'}}]
    }
    router.llm = mock_llm
    router.enable_llm_tool_routing = True

    result = router.process_text("tell me something interesting")

    assert result == "I can help with that."


def test_multiple_tools_correct_dispatch(router):
    """
    With multiple tools registered and LLM active, the router must dispatch
    to the exact tool Gemma specifies by name — not first-registered-wins.
    """
    results = {}

    router.register_tool({"name": "alpha_action", "description": "Alpha tool.", "parameters": {}},
                         lambda t, a: results.update({"hit": "alpha"}) or "alpha")
    router.register_tool({"name": "beta_action", "description": "Beta tool.", "parameters": {}},
                         lambda t, a: results.update({"hit": "beta"}) or "beta")

    # Gemma explicitly picks beta_action — router must honour that exact name
    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"tool": "beta_action", "args": {}}'}}]
    }
    router.llm = mock_llm
    router.enable_llm_tool_routing = True

    router.process_text("execute the second option")
    assert results.get("hit") == "beta"


def test_llm_chat_uses_router_lazy_loader():
    """Chat plugin should obtain the model through router.get_llm() instead of assuming eager load."""
    app = MagicMock()
    app.router.register_tool = MagicMock()

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "chat_ok"}}]
    }
    app.router.get_llm.return_value = mock_llm

    plugin = LLMChatPlugin(app)
    result = plugin.handle_chat("hello there", {})

    assert result == "chat_ok"
    app.router.get_llm.assert_called_once()


def test_multi_action_plan_executes_multiple_tools(router):
    calls = []

    router.register_tool(
        {"name": "launch_app", "description": "Launch app.", "parameters": {}},
        lambda t, a: calls.append(("launch_app", t)) or "Opening app",
    )
    router.register_tool(
        {"name": "get_time", "description": "Get time.", "parameters": {}},
        lambda t, a: calls.append(("get_time", t)) or "It is noon",
    )

    result = router.process_text("open firefox and tell me the time")

    assert calls == [("launch_app", "open firefox"), ("get_time", "tell me the time")]
    assert result == "Opening app\nIt is noon"


def test_system_info_maps_to_system_status(router):
    router.register_tool(
        {"name": "get_system_status", "description": "System status.", "parameters": {}},
        lambda t, a: "system_ok",
    )

    result = router.process_text("what is the system info")
    assert result == "system_ok"


def test_cpu_usage_maps_to_cpu_ram(router):
    router.register_tool(
        {"name": "get_cpu_ram", "description": "CPU RAM.", "parameters": {}},
        lambda t, a: "cpu_ok",
    )

    result = router.process_text("what is the cpu usage")
    assert result == "cpu_ok"


def test_volume_steps_are_extracted(router):
    captured = {}

    def handler(text, args):
        captured.update(args)
        return "volume_ok"

    router.register_tool(
        {"name": "set_volume", "description": "Volume.", "parameters": {}},
        handler,
    )

    result = router.process_text("increase the volume 5 times")
    assert result == "volume_ok"
    assert captured == {"direction": "up", "steps": 5}


def test_volume_absolute_percent_is_extracted(router):
    captured = {}

    def handler(text, args):
        captured.update(args)
        return "volume_ok"

    router.register_tool(
        {"name": "set_volume", "description": "Volume.", "parameters": {}},
        handler,
    )

    result = router.process_text("set the volume to 50 percent")

    assert result == "volume_ok"
    assert captured == {"percent": 50}


def test_volume_follow_up_to_percent_uses_volume_context(router):
    captured = {}

    def handler(text, args):
        captured.update(args)
        return "volume_ok"

    router.register_tool(
        {"name": "set_volume", "description": "Volume.", "parameters": {}},
        handler,
    )
    router._last_context = {"tool": "set_volume", "domain": "volume", "args": {"direction": "up"}}

    result = router.process_text("to 35")

    assert result == "volume_ok"
    assert captured == {"percent": 35}


def test_router_carries_remaining_file_actions_into_pending_request(router):
    router.dialog_state = DialogState()
    captured = {"actions": None}

    def open_handler(text, args):
        router.dialog_state.set_pending_file_request(
            candidates=["/tmp/prep.md", "/tmp/prep.pdf"],
            requested_actions=["open"],
            folder_path="/tmp",
            filename_query="prep",
        )
        return "Which one?"

    def summarize_handler(text, args):
        captured["actions"] = "ran"
        return "summary"

    router.register_tool({"name": "open_file", "description": "Open file.", "parameters": {}}, open_handler)
    router.register_tool({"name": "summarize_file", "description": "Summarize file.", "parameters": {}}, summarize_handler)

    result = router.process_text("open the file and summarize it")

    assert result == "Which one?"
    assert router.dialog_state.pending_file_request.requested_actions == ["open", "summarize"]
    assert captured["actions"] is None


def test_create_file_command_routes_to_manage_file_when_available(router):
    captured = {}

    def manage_file_handler(text, args):
        captured.update(args)
        return f"created {args['filename']}"

    router.register_tool(
        {"name": "manage_file", "description": "Manage file.", "parameters": {}},
        manage_file_handler,
    )

    result = router.process_text("create a file named ironman")

    assert result == "created ironman"
    assert captured == {"action": "create", "filename": "ironman"}
    assert router.current_route_source == "deterministic"


def test_open_it_prefers_pending_file_request_over_app_launch(router):
    router.dialog_state = DialogState()
    router.dialog_state.set_pending_file_request(
        candidates=["/tmp/report.pdf"],
        requested_actions=["open"],
        folder_path="/tmp",
        filename_query="report",
    )
    hits = []

    router.register_tool(
        {"name": "launch_app", "description": "Launch app.", "parameters": {}},
        lambda t, a: hits.append("launch_app") or "launch",
    )
    router.register_tool(
        {"name": "open_file", "description": "Open file.", "parameters": {}},
        lambda t, a: hits.append("open_file") or "open",
    )

    result = router.process_text("open it")

    assert result == "open"
    assert hits == ["open_file"]


def test_router_records_pending_clarification_from_chat_reply(router):
    router.dialog_state = DialogState()
    router.register_tool(
        {"name": "llm_chat", "description": "Chat.", "parameters": {"query": "string"}},
        lambda t, a: 'You\'re looking for "file design build final report". Is that what you meant?',
    )

    result = router.process_text("file design build final report")

    assert "Is that what you meant?" in result
    assert router.dialog_state.pending_clarification.action_text == "file design build final report"


def test_select_file_candidate_pattern_does_not_match_general_sentence(router):
    router.dialog_state = DialogState()
    router.dialog_state.set_pending_file_request(
        candidates=["/tmp/report.pdf", "/tmp/report.txt"],
        requested_actions=["open"],
        folder_path="/tmp",
        filename_query="report",
    )

    router.register_tool(
        {"name": "select_file_candidate", "description": "Choose file.", "parameters": {}},
        lambda t, a: "selected",
    )

    result = router.process_text("that file is not present in the desktop folder")

    assert result != "selected"
