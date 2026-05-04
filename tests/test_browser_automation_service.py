import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.browser_automation.service import BrowserMediaService


class DummyConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_browser_service_prefers_last_used_chrome_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    chrome_root = tmp_path / ".config" / "google-chrome"
    default_profile = chrome_root / "Default"
    default_profile.mkdir(parents=True)
    (chrome_root / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Default"}}),
        encoding="utf-8",
    )

    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))

    settings = service._resolve_profile_settings("chrome")

    assert settings["user_data_dir"] == str(chrome_root)
    assert settings["profile_directory"] == "Default"
    assert "--profile-directory=Default" in settings["launch_args"]


def test_get_page_recreates_closed_browser_context():
    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))
    contexts = []

    class ClosedContext:
        pages = []

        def new_page(self):
            raise RuntimeError("BrowserContext.new_page: Target page, context or browser has been closed")

    class HealthyContext:
        def __init__(self):
            self.pages = []

        def new_page(self):
            return "healthy-page"

    contexts.extend([ClosedContext(), HealthyContext()])
    cleanup_calls = []

    def fake_ensure_context(browser_name):
        return contexts.pop(0)

    service._ensure_context = fake_ensure_context
    service._cleanup_playwright = lambda: cleanup_calls.append("cleanup")

    page = service._get_page("chrome", "youtube_music", "https://music.youtube.com")

    assert page == "healthy-page"
    assert cleanup_calls == ["cleanup"]
    assert service._pages["youtube_music"] == "healthy-page"


def test_get_page_returns_help_message_after_repeated_closed_contexts():
    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))
    cleanup_calls = []

    class ClosedContext:
        pages = []

        def new_page(self):
            raise RuntimeError("BrowserContext.new_page: Target page, context or browser has been closed")

    service._ensure_context = lambda browser_name: ClosedContext()
    service._cleanup_playwright = lambda: cleanup_calls.append("cleanup")

    page = service._get_page("chrome", "youtube_music", "https://music.youtube.com")

    assert "Browser automation" in page or "Failed to start browser automation" in page
    assert cleanup_calls == ["cleanup", "cleanup"]


def test_browser_service_clones_profile_when_live_profile_is_locked(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    chrome_root = tmp_path / ".config" / "google-chrome"
    default_profile = chrome_root / "Default"
    default_profile.mkdir(parents=True)
    (chrome_root / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Default"}}),
        encoding="utf-8",
    )
    (default_profile / "Preferences").write_text("{}", encoding="utf-8")
    (default_profile / "Cookies").write_text("cookie-db", encoding="utf-8")
    (default_profile / "SingletonLock").write_text("locked", encoding="utf-8")
    (default_profile / "Cache").mkdir()

    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))

    locked_settings = service._resolve_profile_settings("chrome")
    cloned_settings = service._clone_profile_settings(locked_settings, "chrome")

    assert cloned_settings["mode"] == "cloned"
    assert cloned_settings["profile_directory"] == "Default"
    assert os.path.exists(os.path.join(cloned_settings["user_data_dir"], "Local State"))
    assert os.path.exists(os.path.join(cloned_settings["user_data_dir"], "Default", "Cookies"))
    assert not os.path.exists(os.path.join(cloned_settings["user_data_dir"], "Default", "SingletonLock"))
    assert not os.path.exists(os.path.join(cloned_settings["user_data_dir"], "Default", "Cache"))


def test_browser_service_prepares_signed_in_clone_outside_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    chrome_root = tmp_path / ".config" / "google-chrome"
    default_profile = chrome_root / "Default"
    default_profile.mkdir(parents=True)
    (chrome_root / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Default"}}),
        encoding="utf-8",
    )
    (default_profile / "Cookies").write_text("cookie-db", encoding="utf-8")

    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))

    launch_settings = service._prepare_launch_profile_settings("chrome")

    assert launch_settings["mode"] == "cloned"
    assert launch_settings["profile_directory"] == "Default"
    assert launch_settings["user_data_dir"].startswith(str(tmp_path / ".cache" / "friday"))
    assert os.path.exists(os.path.join(launch_settings["user_data_dir"], "Default", "Cookies"))


def test_prepare_media_page_fullscreens_only_youtube():
    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))
    calls = []

    class DummyPage:
        def wait_for_load_state(self, state):
            calls.append(("load", state))

        def wait_for_timeout(self, ms):
            calls.append(("timeout", ms))

        def bring_to_front(self):
            calls.append(("front", None))

    page = DummyPage()
    service._start_media_playback = lambda current_page: calls.append(("play", current_page))
    service._focus_browser_window = lambda platform_name, fullscreen=False: calls.append(("focus", platform_name, fullscreen))
    service._enter_fullscreen = lambda current_page: calls.append(("enter_fullscreen", current_page))
    service._exit_fullscreen = lambda current_page: calls.append(("exit_fullscreen", current_page))

    service._prepare_media_page(page, "youtube")
    service._prepare_media_page(page, "youtube_music")

    assert ("enter_fullscreen", page) in calls
    assert ("exit_fullscreen", page) in calls
    assert ("focus", "youtube", False) in calls
    assert ("focus", "youtube_music", False) in calls


def test_launch_context_uses_real_password_store_settings(tmp_path):
    service = BrowserMediaService(SimpleNamespace(config=DummyConfig()))
    profile_root = tmp_path / "chrome-clone"
    profile_root.mkdir()
    captured = {}

    class DummyChromium:
        def launch_persistent_context(self, **kwargs):
            captured.update(kwargs)
            return "context"

    context = service._launch_context(
        DummyChromium(),
        "/usr/bin/google-chrome",
        "chrome",
        {
            "user_data_dir": str(profile_root),
            "profile_directory": "Default",
            "launch_args": ["--profile-directory=Default"],
            "mode": "cloned",
        },
    )

    assert context == "context"
    assert captured["ignore_default_args"] == ["--password-store=basic", "--use-mock-keychain"]
    assert captured["no_viewport"] is True
