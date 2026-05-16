import sys
import os
import pytest
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
    assert screenshot_callback("take a screenshot", {}) == "Screenshot taken."


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


# ── Wayland black-screenshot regression tests ────────────────────────────────

def test_take_screenshot_skips_mss_on_wayland(monkeypatch):
    """mss must never be called when XDG_SESSION_TYPE is wayland."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    import modules.system_control.screenshot as sc
    monkeypatch.setattr(sc, "_take_screenshot_via_mutter_screencast", lambda p: "err")
    monkeypatch.setattr(sc, "_take_screenshot_via_gdbus_shell", lambda p: "err")
    monkeypatch.setattr(sc, "_take_screenshot_via_portal", lambda p, **kw: "err")
    monkeypatch.setattr(sc, "_take_screenshot_via_gnome_shell", lambda p: "err")
    monkeypatch.setattr(sc, "_take_screenshot_via_gnome_adapter", lambda p, **kw: "err")

    called = []
    fake_mss_mod = type(sys)("mss")
    class _FakeMSS:
        def __enter__(self): called.append(True); return self
        def __exit__(self, *a): pass
    fake_mss_mod.MSS = _FakeMSS
    fake_mss_mod.tools = MagicMock()
    monkeypatch.setitem(sys.modules, "mss", fake_mss_mod)
    monkeypatch.setitem(sys.modules, "mss.tools", fake_mss_mod.tools)

    sc.take_screenshot()
    assert called == [], "mss.MSS() must not be called on a Wayland session"


def test_is_mostly_black_rejects_black_png(tmp_path):
    """_is_mostly_black must return True for a solid-black PNG."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    import modules.system_control.screenshot as sc

    f = tmp_path / "black.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(str(f))
    assert sc._is_mostly_black(str(f)) is True


def test_is_mostly_black_passes_real_content(tmp_path):
    """_is_mostly_black must return False for a non-black image."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    import modules.system_control.screenshot as sc

    f = tmp_path / "grey.png"
    Image.new("RGB", (100, 100), (128, 128, 128)).save(str(f))
    assert sc._is_mostly_black(str(f)) is False


def test_is_mostly_black_image_rejects_black():
    """_is_mostly_black_image must correctly classify PIL images."""
    pytest.importorskip("PIL")
    from PIL import Image
    from modules.vision.screenshot import _is_mostly_black_image

    assert _is_mostly_black_image(Image.new("RGB", (50, 50), (0, 0, 0))) is True
    assert _is_mostly_black_image(Image.new("RGB", (50, 50), (200, 200, 200))) is False


# ── Pending file-name clarification ──────────────────────────────────────────

def test_open_file_without_context_sets_pending_file_name_request(tmp_path, monkeypatch):
    """'open it' with no active file must ask 'Which file?' AND set pending_file_name_request."""
    monkeypatch.setenv("HOME", str(tmp_path))
    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    response = plugin.handle_open_file("open it", {})

    assert "which file" in response.lower()
    assert app.dialog_state.pending_file_name_request == "open"


def test_search_file_without_name_sets_pending_file_name_request(tmp_path, monkeypatch):
    """'search file' with no filename sets pending_file_name_request = 'find'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    app = MagicMock()
    app.router.register_tool = MagicMock()
    app.router.get_llm.return_value = None
    app.dialog_state = DialogState()
    plugin = SystemControlPlugin(app)

    response = plugin.handle_search_file("find", {})

    assert "which file" in response.lower()
    assert app.dialog_state.pending_file_name_request == "find"


def _make_intent_recognizer_with_pending_file(action, monkeypatch):
    """Build a minimal IntentRecognizer wired to a DialogState with pending_file_name_request set."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    ds = DialogState()
    ds.pending_file_name_request = action
    router.dialog_state = ds
    router._tools_by_name = {}
    router.context_store = None
    router.session_id = None
    return IntentRecognizer(router), ds


def test_pending_file_name_routes_screenshot_to_open_file_not_take_screenshot():
    """After 'Which file?', saying 'screenshot' must route to open_file, NOT take_screenshot."""
    recognizer, ds = _make_intent_recognizer_with_pending_file("open", None)

    plans = recognizer.plan("screenshot")

    assert plans, "Expected a non-empty plan"
    assert plans[0]["tool"] == "open_file"
    assert ds.pending_file_name_request is None  # consumed


def test_pending_file_name_routes_bare_word_with_filename_arg():
    """The plan produced by pending_file_name_request must carry the user's word as filename arg."""
    recognizer, ds = _make_intent_recognizer_with_pending_file("read", None)

    plans = recognizer.plan("notes")

    assert plans[0]["tool"] == "read_file"
    assert plans[0]["args"].get("filename") == "notes"


def test_pending_file_name_strips_leading_article():
    """'the screenshot' → filename arg should be 'screenshot', not 'the screenshot'."""
    recognizer, ds = _make_intent_recognizer_with_pending_file("open", None)

    plans = recognizer.plan("the screenshot")

    assert plans[0]["args"]["filename"] == "screenshot"


def test_pending_file_name_cancel_clears_state():
    """Saying 'cancel' while pending_file_name_request is set must clear the state."""
    recognizer, ds = _make_intent_recognizer_with_pending_file("open", None)

    plans = recognizer.plan("cancel")

    assert ds.pending_file_name_request is None
    # 'cancel' falls through to _parse_confirmation → confirm_no
    # (or no plan if confirm_no isn't in tools_by_name) — just verify state cleared


def test_pending_candidate_prefix_match_routes_to_select():
    """'screenshot' should select 'screenshot_20260515_123456.png' from a candidate list."""
    from core.intent_recognizer import IntentRecognizer
    from core.dialog_state import DialogState, PendingFileRequest
    router = MagicMock()
    ds = DialogState()
    ds.set_pending_file_request(
        candidates=["/home/user/Pictures/screenshot_20260515_123456.png"],
        requested_actions=["open"],
    )
    router.dialog_state = ds
    router._tools_by_name = {}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    plans = recognizer.plan("screenshot")

    assert plans[0]["tool"] == "select_file_candidate"


# ── _parse_notes coverage ─────────────────────────────────────────────────────

def test_make_a_note_routes_to_save_note():
    """'make a note' must route to save_note, not manage_file."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"save_note": object(), "manage_file": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    for phrase in ("make a note: buy milk", "jot this down", "note that I prefer tea"):
        plans = recognizer.plan(phrase)
        assert plans and plans[0]["tool"] == "save_note", f"Expected save_note for: {phrase!r}"


def test_add_to_notes_routes_to_save_note():
    """'add to my notes' must route to save_note."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"save_note": object(), "manage_file": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    plans = recognizer.plan("add to my notes: meeting at 3pm")
    assert plans and plans[0]["tool"] == "save_note"


# ── _parse_friday_status tests ────────────────────────────────────────────────

def test_friday_status_routes_to_get_friday_status():
    """'friday status' and variants must route to get_friday_status deterministically."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"get_friday_status": object(), "get_system_status": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    for phrase in (
        "friday status",
        "friday, are you ready",
        "are you ready friday",
        "how are you doing friday",
        "assistant status",
        "runtime status",
        "check friday",
        "your status",
    ):
        plans = recognizer.plan(phrase)
        assert plans and plans[0]["tool"] == "get_friday_status", (
            f"Expected get_friday_status for: {phrase!r}, got {plans}"
        )


def test_friday_status_not_intercepted_by_knowledge_question():
    """'how does friday work' is a knowledge question, not a status request."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"get_friday_status": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    plans = recognizer.plan("how does friday work")
    assert not plans or plans[0]["tool"] != "get_friday_status", (
        "Knowledge question must not route to get_friday_status"
    )


# ── _parse_query_document tests ───────────────────────────────────────────────

def test_query_document_fires_when_active_document_present():
    """A WH-question with [active_document=...] prefix routes to query_document."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"query_document": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    # Simulate _resolve_references injecting the active_document prefix
    clause = "[active_document=/home/user/report.pdf] what does it say about the budget?"
    plans = recognizer.plan(clause)
    assert plans and plans[0]["tool"] == "query_document", (
        f"Expected query_document, got {plans}"
    )


def test_query_document_does_not_fire_without_active_document():
    """A plain WH-question without [active_document=...] must NOT route to query_document."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"query_document": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    plans = recognizer.plan("what is the capital of France")
    assert not plans or plans[0]["tool"] != "query_document", (
        "Plain question without active_document must not route to query_document"
    )


# ── _parse_help expansion tests ───────────────────────────────────────────────

def test_help_expanded_phrases_route_to_show_capabilities():
    """Expanded help phrases must route to show_capabilities."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {"show_capabilities": object()}
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    for phrase in (
        "what tools do you have",
        "what features do you have",
        "what can I ask you",
        "list your tools",
        "tell me what you can do",
    ):
        plans = recognizer.plan(phrase)
        assert plans and plans[0]["tool"] == "show_capabilities", (
            f"Expected show_capabilities for: {phrase!r}, got {plans}"
        )


# ── Integration routing tests ─────────────────────────────────────────────────

def test_calendar_event_routes_to_create_calendar_event():
    """'add a calendar event Lunch' must reach create_calendar_event, never a file tool."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    router.dialog_state = DialogState()
    router._tools_by_name = {
        "create_calendar_event": object(),
        "manage_file": object(),
        "save_note": object(),
    }
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    plans = recognizer.plan("add a calendar event Lunch")
    assert plans and plans[0]["tool"] == "create_calendar_event", (
        f"Expected create_calendar_event, got {plans}"
    )


def test_reminder_after_screenshot_context_routes_to_set_reminder():
    """'remind me at 3pm' after a screenshot is in dialog_state must route to set_reminder."""
    from core.intent_recognizer import IntentRecognizer
    router = MagicMock()
    ds = DialogState()
    ds.selected_file = "/home/user/Pictures/FRIDAY_Screenshots/screenshot_20260515_120000.png"
    router.dialog_state = ds
    router._tools_by_name = {
        "set_reminder": object(),
        "manage_file": object(),
    }
    router.context_store = None
    router.session_id = None
    recognizer = IntentRecognizer(router)

    plans = recognizer.plan("remind me at 3pm")
    assert plans and plans[0]["tool"] == "set_reminder", (
        f"Expected set_reminder, got {plans}"
    )
