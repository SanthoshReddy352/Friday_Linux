import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.dialog_state import DialogState
from unittest.mock import MagicMock

import modules.system_control.plugin as system_plugin
from modules.system_control import screenshot as screenshot_module
import modules.system_control.file_workspace as file_workspace
from modules.system_control.app_launcher import extract_app_names, canonicalize_app_name, configure_app_registry
from modules.system_control.file_search import search_files_raw
from core.system_capabilities import SystemCapabilities
from modules.system_control.plugin import SystemControlPlugin
from core.assistant_context import AssistantContext


def test_extract_app_names_multiple_apps():
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "firefox": "/usr/bin/firefox",
        "google-chrome": "/usr/bin/google-chrome",
        "gnome-calculator": "/usr/bin/gnome-calculator",
    }
    configure_app_registry(capabilities)
    result = extract_app_names("open firefox and chrome and calculator")
    assert result == ["firefox", "chrome", "calculator"]


def test_handle_launch_app_passes_multiple_apps(monkeypatch):
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "firefox": "/usr/bin/firefox",
        "google-chrome": "/usr/bin/google-chrome",
        "gnome-calculator": "/usr/bin/gnome-calculator",
    }
    configure_app_registry(capabilities)

    app = MagicMock()
    app.router.register_tool = MagicMock()
    plugin = SystemControlPlugin(app)

    captured = {}

    def fake_launch(names):
        captured["names"] = names
        return "ok"

    monkeypatch.setattr(system_plugin, "launch_application", fake_launch)
    result = plugin.handle_launch_app("open firefox and chrome and calculator", {})

    assert result == "ok"
    assert captured["names"] == ["firefox", "chrome", "calculator"]


def test_take_screenshot_tool_is_registered_and_routable(monkeypatch):
    app = MagicMock()
    app.router.register_tool = MagicMock()
    plugin = SystemControlPlugin(app)
    monkeypatch.setattr(system_plugin, "take_screenshot", lambda: "Screenshot saved successfully at: /tmp/shot.png")
    screenshot_callback = None
    for call in app.router.register_tool.call_args_list:
        spec, callback = call.args[:2]
        if spec["name"] == "take_screenshot":
            screenshot_callback = callback
            break

    assert screenshot_callback is not None
    assert screenshot_callback("take a screenshot", {}) == "Screenshot saved successfully at: /tmp/shot.png"


def test_copy_portal_screenshot_uri(tmp_path):
    source = tmp_path / "portal shot.png"
    target = tmp_path / "saved.png"
    source.write_bytes(b"png-data")

    error = screenshot_module._copy_portal_uri(f"file://{str(source).replace(' ', '%20')}", str(target))

    assert error is None
    assert target.read_bytes() == b"png-data"


def test_portal_request_path_matches_xdg_desktop_portal_shape():
    path = screenshot_module._portal_request_path(":1.6112", "friday_token")

    assert path == "/org/freedesktop/portal/desktop/request/1_6112/friday_token"


def test_extract_app_names_fuzzy_spoken_calculator():
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "firefox": "/usr/bin/firefox",
        "google-chrome": "/usr/bin/google-chrome",
        "gnome-calculator": "/usr/bin/gnome-calculator",
    }
    configure_app_registry(capabilities)
    result = extract_app_names("open firefox and calipoliters")
    assert result == ["firefox", "calculator"]


def test_extract_app_names_brave_resolves_cleanly():
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "brave-browser": "/usr/bin/brave-browser",
    }
    configure_app_registry(capabilities)
    result = extract_app_names("open brave")
    assert result == ["brave"]


def test_canonicalize_plural_app_name():
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "gnome-calculator": "/usr/bin/gnome-calculator",
    }
    configure_app_registry(capabilities)
    assert canonicalize_app_name("calculators") == "calculator"


def test_extract_app_names_does_not_add_extra_fuzzy_duplicate():
    capabilities = SystemCapabilities()
    capabilities.desktop_apps = {}
    capabilities.binaries = {
        "firefox": "/usr/bin/firefox",
        "google-chrome": "/usr/bin/google-chrome",
        "gnome-calculator": "/usr/bin/gnome-calculator",
    }
    configure_app_registry(capabilities)
    result = extract_app_names("open chrome firefox calculator")
    assert result == ["chrome", "firefox", "calculator"]


def test_canonicalize_app_name_does_not_map_coffee_to_chrome():
    assert canonicalize_app_name("coffee") == "coffee"
    assert extract_app_names("open coffee") == []


def test_handle_set_volume_parses_unmute_and_steps(monkeypatch):
    app = MagicMock()
    app.router.register_tool = MagicMock()
    plugin = SystemControlPlugin(app)

    captured = {}

    def fake_set_volume(direction, steps=1):
        captured["direction"] = direction
        captured["steps"] = steps
        return "ok"

    monkeypatch.setattr(system_plugin, "set_volume", fake_set_volume)
    result = plugin.handle_set_volume("increase the volume 5 times", {})
    assert result == "ok"
    assert captured == {"direction": "up", "steps": 5}

    result = plugin.handle_set_volume("unmute the volume", {})
    assert result == "ok"
    assert captured["direction"] == "unmute"


def test_handle_set_volume_parses_absolute_percent(monkeypatch):
    app = MagicMock()
    app.router.register_tool = MagicMock()
    plugin = SystemControlPlugin(app)

    captured = {}

    def fake_set_volume(direction, steps=1, percent=None):
        captured["direction"] = direction
        captured["steps"] = steps
        captured["percent"] = percent
        return "ok"

    monkeypatch.setattr(system_plugin, "set_volume", fake_set_volume)

    result = plugin.handle_set_volume("set the volume to 50 percent", {})

    assert result == "ok"
    assert captured == {"direction": "absolute", "steps": 1, "percent": 50}


def test_open_file_with_multiple_extensions_requests_clarification(monkeypatch, tmp_path):
    coffee = tmp_path / "coffee"
    coffee.mkdir()
    (coffee / "prep.md").write_text("Markdown prep", encoding="utf-8")
    (coffee / "prep.txt").write_text("Text prep", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    response = plugin.handle_open_file("open prep in the coffee folder", {})

    assert "multiple matching files" in response.lower()
    assert "prep.md" in response
    assert "prep.txt" in response
    assert plugin.dialog_state.has_pending_file_request()


def test_missing_file_in_folder_then_list_other_files(monkeypatch, tmp_path):
    coffee = tmp_path / "coffee"
    coffee.mkdir()
    (coffee / "beans.txt").write_text("beans", encoding="utf-8")
    (coffee / "recipe.md").write_text("recipe", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    response = plugin.handle_open_file("open prepp in the coffee folder", {})
    assert "couldn't find a file named 'prepp' in the coffee folder" in response.lower()

    listing = plugin.handle_list_folder_contents("what are the other files in that folder?", {})
    assert "files in coffee" in listing.lower()
    assert "beans.txt" in listing
    assert "recipe.md" in listing


def test_file_search_does_not_stick_to_previous_folder_scope(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "coffee.txt").write_text("coffee", encoding="utf-8")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    report = desktop / "report.txt"
    report.write_text("report", encoding="utf-8")

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    first = plugin.handle_search_file("find the file coffee in the archive folder", {})
    second = plugin.handle_search_file("find the file report", {})

    assert "coffee.txt" in first
    assert "report.txt" in second
    assert "in the archive folder" not in second.lower()
    assert plugin.dialog_state.current_folder == str(desktop)


def test_file_search_ignores_tmp_plan_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    expected = desktop / "coffee.txt"
    expected.write_text("desktop coffee", encoding="utf-8")

    tmp_plan = tmp_path / "tmp_plan_folder_ctx2"
    tmp_plan.mkdir()
    (tmp_plan / "coffee.txt").write_text("temp coffee", encoding="utf-8")

    matches = search_files_raw("coffee", limit=10)

    assert str(expected) in matches
    assert all("tmp_plan_folder_ctx" not in match for match in matches)


def test_explicit_folder_override_beats_previous_folder_context(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "coffee.txt").write_text("coffee", encoding="utf-8")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target = desktop / "report.txt"
    target.write_text("report", encoding="utf-8")

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    monkeypatch.setattr(file_workspace, "open_file", lambda path: f"Opening {os.path.basename(path)}...")

    plugin.handle_search_file("find the file coffee in the archive folder", {})
    response = plugin.handle_open_file("open the file report in the desktop folder", {})

    assert response == "Opening report.txt..."
    assert plugin.dialog_state.current_folder == str(desktop)


def test_select_file_candidate_can_open_and_summarize(monkeypatch, tmp_path):
    coffee = tmp_path / "coffee"
    coffee.mkdir()
    pdf_path = coffee / "prep.pdf"
    md_path = coffee / "prep.md"
    pdf_path.write_text("Pretend PDF text", encoding="utf-8")
    md_path.write_text("Markdown notes", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    monkeypatch.setattr(file_workspace, "open_file", lambda path: f"Opening {os.path.basename(path)}...")
    monkeypatch.setattr(
        file_workspace,
        "summarize_file_offline",
        lambda path, llm=None: f"Summary of {os.path.basename(path)}:\n- short summary",
    )

    plugin.dialog_state.set_pending_file_request(
        candidates=[str(md_path), str(pdf_path)],
        requested_actions=["open", "summarize"],
        folder_path=str(coffee),
        filename_query="prep",
    )

    response = plugin.handle_select_file_candidate("the pdf one", {})

    assert "Opening prep.pdf..." in response
    assert "Summary of prep.pdf" in response
    assert plugin.dialog_state.selected_file == str(pdf_path)
    assert not plugin.dialog_state.has_pending_file_request()


def test_manage_file_saves_last_assistant_response(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    app.assistant_context = AssistantContext()
    app.assistant_context.record_message("assistant", "Programming is giving instructions to a computer.")
    plugin = SystemControlPlugin(app)

    response = plugin.handle_manage_file("save that to file friday_notes.md", {})

    saved_path = desktop / "friday_notes.md"
    assert "Saved friday_notes.md" in response
    assert saved_path.read_text(encoding="utf-8") == "Programming is giving instructions to a computer."


def test_open_file_in_downloads_folder_extracts_filename_correctly(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    target = downloads / "Registrations.xlsx"
    target.write_text("sheet", encoding="utf-8")

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    monkeypatch.setattr(file_workspace, "open_file", lambda path: f"Opening {os.path.basename(path)}...")

    response = plugin.handle_open_file("open the registrations file in the downloads folder", {})

    assert response == "Opening Registrations.xlsx..."


def test_strip_shutdown_tail_removes_goodbye():
    from modules.system_control.plugin import _strip_shutdown_tail
    summary = (
        "user: what are programming languages\n"
        "assistant: Programming languages are tools...\n"
        "user: goodbye\n"
        "assistant: Goodbye sir, see you later."
    )
    result = _strip_shutdown_tail(summary)
    assert "goodbye" not in result.lower()
    assert "programming languages" in result.lower()


def test_strip_shutdown_tail_preserves_normal_content():
    from modules.system_control.plugin import _strip_shutdown_tail
    summary = (
        "user: can you explain Python\n"
        "assistant: Python is a high-level language.\n"
        "user: what about machine learning\n"
        "assistant: Machine learning is a subset of AI."
    )
    result = _strip_shutdown_tail(summary)
    assert "machine learning" in result.lower()
    assert result == summary


def test_handle_yes_skips_goodbye_topic():
    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    plugin = SystemControlPlugin(app)

    store = MagicMock()
    store.get_facts_by_namespace.return_value = [
        {"key": "has_pending_session", "value": "true"},
        {"key": "last_session_summary", "value": (
            "user: what are programming languages\n"
            "assistant: Programming languages are tools we use...\n"
            "user: thanks\n"
            "assistant: You're welcome!\n"
            "user: goodbye\n"
            "assistant: Goodbye sir."
        )},
    ]
    app.context_store = store

    response = plugin.handle_yes("yes", {})

    assert "goodbye" not in response.lower()
    assert "programming languages" in response.lower() or "thanks" in response.lower() or "left off" in response.lower()


def test_manage_file_appends_content(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    existing = desktop / "notes.txt"
    existing.write_text("alpha", encoding="utf-8")

    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    response = plugin.handle_manage_file("append beta to file notes.txt", {})

    assert "Updated notes.txt" in response
    assert existing.read_text(encoding="utf-8") == "alpha\nbeta"
