import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.dialog_state import DialogState
from unittest.mock import MagicMock

import modules.system_control.plugin as system_plugin
from modules.system_control.app_launcher import extract_app_names, canonicalize_app_name
from modules.system_control.plugin import SystemControlPlugin


def test_extract_app_names_multiple_apps():
    result = extract_app_names("open firefox and chrome and calculator")
    assert result == ["firefox", "chrome", "calculator"]


def test_handle_launch_app_passes_multiple_apps(monkeypatch):
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


def test_extract_app_names_fuzzy_spoken_calculator():
    result = extract_app_names("open firefox and calipoliters")
    assert result == ["firefox", "calculator"]


def test_canonicalize_plural_app_name():
    assert canonicalize_app_name("calculators") == "calculator"


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

    monkeypatch.setattr(system_plugin, "open_file", lambda path: f"Opening {os.path.basename(path)}...")
    monkeypatch.setattr(
        system_plugin,
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
