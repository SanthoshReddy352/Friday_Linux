import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.system_capabilities import SystemCapabilities
from core.router import CommandRouter
from modules.jarvis_skills.plugin import JarvisSkillsPlugin
from modules.system_control.app_launcher import configure_app_registry, canonicalize_app_name, extract_app_names


def test_system_capabilities_parse_desktop_entry_and_build_registry(tmp_path, monkeypatch):
    applications_dir = tmp_path / "applications"
    applications_dir.mkdir()
    desktop_file = applications_dir / "org.gnome.Terminal.desktop"
    desktop_file.write_text(
        "[Desktop Entry]\n"
        "Name=Terminal\n"
        "Exec=gnome-terminal --wait %U\n",
        encoding="utf-8",
    )

    capabilities = SystemCapabilities()
    monkeypatch.setattr(capabilities, "_application_dirs", lambda: (str(applications_dir),))
    monkeypatch.setattr(
        capabilities,
        "binaries",
        {"gnome-terminal": "/usr/bin/gnome-terminal", "firefox": "/usr/bin/firefox"},
    )

    discovered = capabilities._discover_desktop_apps()
    capabilities.desktop_apps = discovered

    assert "terminal" in discovered
    assert discovered["terminal"].command == "gnome-terminal"

    registry = configure_app_registry(capabilities)
    assert canonicalize_app_name("terminal") == "terminal"
    assert "terminal" in registry


def test_app_extraction_uses_dynamic_registry():
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "firefox": "/usr/bin/firefox",
        "google-chrome": "/usr/bin/google-chrome",
        "brave-browser": "/usr/bin/brave-browser",
        "gnome-calculator": "/usr/bin/gnome-calculator",
    }
    configure_app_registry(capabilities)

    assert extract_app_names("open firefox and chrome and calculator") == [
        "firefox",
        "chrome",
        "calculator",
    ]


def test_unknown_app_name_does_not_fuzzy_match_random_desktop_entry():
    capabilities = SystemCapabilities()
    capabilities.binaries = {
        "firefox": "/usr/bin/firefox",
        "brave-browser": "/usr/bin/brave-browser",
    }
    capabilities.desktop_apps = {
        "reaver": type("DesktopAppStub", (), {
            "command": "exec-in-shell",
            "aliases": {"reaver"},
        })()
    }
    configure_app_registry(capabilities)

    assert canonicalize_app_name("brave") == "brave"
    assert extract_app_names("open brave") == ["brave"]


def test_jarvis_skills_plugin_disables_missing_optional_skills():
    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.config = MagicMock()
    app.capabilities = SystemCapabilities()
    app.capabilities.platform = "Linux"
    app.capabilities.python_modules = {
        "cv2": False,
        "torch": False,
        "ultralytics": False,
        "selenium": False,
        "webdriver_manager": False,
        "google.genai": False,
    }
    app.capabilities.binaries = {}
    app.capabilities.skill_status = {}

    plugin = JarvisSkillsPlugin(app)

    disabled = app.capabilities.disabled_skills()
    assert "camera_skill" in disabled
    assert "detection_skill" in disabled
    assert "Missing Python modules" in disabled["camera_skill"]
    assert "Missing Python modules" in disabled["detection_skill"]
    assert plugin.skills


def test_simple_commands_do_not_invoke_tool_model():
    router = CommandRouter(MagicMock())
    router.tool_llm = MagicMock()
    router.register_tool(
        {"name": "launch_app", "description": "Launch app.", "parameters": {}},
        lambda t, a: "opened",
    )

    result = router.process_text("open firefox")

    assert result == "opened"
    router.tool_llm.create_chat_completion.assert_not_called()
    assert router.current_route_source == "deterministic"


def test_file_search_plan_routes_deterministically_without_tool_model():
    router = CommandRouter(MagicMock())
    router.tool_llm = MagicMock()
    router.register_tool(
        {"name": "search_file", "description": "Search files.", "parameters": {}},
        lambda t, a: "found",
    )

    result = router.process_text("find file applications")

    assert result == "found"
    router.tool_llm.create_chat_completion.assert_not_called()
    assert router.current_route_source == "deterministic"


def test_chat_queries_do_not_invoke_tool_model():
    router = CommandRouter(MagicMock())
    router.tool_llm = MagicMock()
    router.register_tool(
        {"name": "llm_chat", "description": "Chat.", "parameters": {"query": "string"}},
        lambda t, a: "chat_ok",
    )

    result = router.process_text("what is your name")

    assert result == "chat_ok"
    router.tool_llm.create_chat_completion.assert_not_called()
    assert router.current_route_source == "gemma_chat"


def test_ambiguous_tool_queries_invoke_tool_model():
    router = CommandRouter(MagicMock())
    router.register_tool(
        {"name": "launch_app", "description": "Launch app.", "parameters": {"app_name": "string"}},
        lambda t, a: f"opening {a['app_name']}",
    )
    router.tool_llm = MagicMock()
    router.tool_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"tool":"launch_app","args":{"app_name":"firefox"}}'}}]
    }

    result = router.process_text("could you run the browser for me")

    assert result == "opening firefox"
    router.tool_llm.create_chat_completion.assert_called_once()
    assert router.current_route_source == "qwen_tool"


def test_tool_model_timeout_falls_back_to_clarify():
    class SlowLLM:
        def create_chat_completion(self, **kwargs):
            time.sleep(0.2)
            return {"choices": [{"message": {"content": '{"tool":"launch_app","args":{"app_name":"firefox"}}'}}]}

    router = CommandRouter(MagicMock())
    router.tool_llm = SlowLLM()
    router.tool_timeout_ms = 50
    router.register_tool(
        {"name": "launch_app", "description": "Launch app.", "parameters": {"app_name": "string"}},
        lambda t, a: f"opening {a['app_name']}",
    )

    result = router.process_text("could you run the browser for me")

    assert "need a bit more detail" in result.lower()
    assert router.current_route_source == "fallback_clarify"
