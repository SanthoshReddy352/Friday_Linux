import os
import shutil
import subprocess
from urllib.parse import quote_plus

from core.logger import logger


class BrowserMediaService:
    def __init__(self, app):
        self.app = app
        self.profile_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "browser-profile")
        self._playwright = None
        self._context = None
        self._pages = {}
        self._current_platform = None

    def open_browser_url(self, url, browser_name="chrome", platform="browser"):
        page = self._get_page(browser_name=browser_name, platform=platform, url=url)
        if isinstance(page, str):
            return self._open_url_fallback(url, browser_name=browser_name, platform=platform, reason=page)
        try:
            page.goto(url, wait_until="domcontentloaded")
            self._current_platform = platform
            return f"Opening {platform.replace('_', ' ')} in {browser_name}."
        except Exception as exc:
            logger.error("Browser open failed: %s", exc)
            return self._open_url_fallback(
                url,
                browser_name=browser_name,
                platform=platform,
                reason=f"Failed to open {platform.replace('_', ' ')} in {browser_name}: {exc}",
            )

    def play_youtube(self, query, browser_name="chrome"):
        return self._play_video(
            query=query,
            browser_name=browser_name,
            platform="youtube",
            home_url="https://www.youtube.com",
            search_url=f"https://www.youtube.com/results?search_query={quote_plus(query)}",
            first_result_selector="ytd-video-renderer a#video-title",
        )

    def play_youtube_music(self, query, browser_name="chrome"):
        return self._play_video(
            query=query,
            browser_name=browser_name,
            platform="youtube_music",
            home_url="https://music.youtube.com",
            search_url=f"https://music.youtube.com/search?q={quote_plus(query)}",
            first_result_selector="ytmusic-responsive-list-item-renderer a[href*='watch']",
        )

    def browser_media_control(self, action, platform=None, query=""):
        platform = platform or self._current_platform or "youtube"
        page = self._pages.get(platform)
        if page is None:
            if action == "play" and query:
                if platform == "youtube_music":
                    return self.play_youtube_music(query)
                return self.play_youtube(query)
            return "I don't have an active browser media session yet."

        try:
            page.bring_to_front()
            if action == "pause":
                page.keyboard.press("k")
                return f"Paused {platform.replace('_', ' ')}."
            if action == "resume":
                page.keyboard.press("k")
                return f"Resumed {platform.replace('_', ' ')}."
            if action == "next":
                page.keyboard.press("Shift+N")
                return f"Skipped to the next item on {platform.replace('_', ' ')}."
            if action == "play" and query:
                if platform == "youtube_music":
                    return self.play_youtube_music(query)
                return self.play_youtube(query)
            return f"I don't know how to '{action}' in the browser yet."
        except Exception as exc:
            logger.error("Browser media control failed: %s", exc)
            return f"Failed to control browser playback: {exc}"

    def _play_video(self, query, browser_name, platform, home_url, search_url, first_result_selector):
        page = self._get_page(browser_name=browser_name, platform=platform, url=home_url)
        if isinstance(page, str):
            return self._open_url_fallback(
                search_url,
                browser_name=browser_name,
                platform=platform,
                reason=page,
                action_label=f"Opening search results for {query} on {platform.replace('_', ' ')}",
            )
        try:
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            locator = page.locator(first_result_selector).first
            locator.wait_for(timeout=8000)
            locator.click()
            page.wait_for_load_state("domcontentloaded")
            self._current_platform = platform
            return f"Playing {query} on {platform.replace('_', ' ')} in {browser_name}."
        except Exception as exc:
            logger.error("Browser playback failed: %s", exc)
            return self._open_url_fallback(
                search_url,
                browser_name=browser_name,
                platform=platform,
                reason=f"Failed to play {query} on {platform.replace('_', ' ')}: {exc}",
                action_label=f"Opening search results for {query} on {platform.replace('_', ' ')}",
            )

    def _get_page(self, browser_name, platform, url):
        context = self._ensure_context(browser_name)
        if isinstance(context, str):
            return context
        page = self._pages.get(platform)
        try:
            if page and not page.is_closed():
                page.bring_to_front()
                return page
        except Exception:
            page = None

        page = context.new_page()
        self._pages[platform] = page
        return page

    def _ensure_context(self, browser_name):
        if self._context is not None:
            return self._context

        try:
            import playwright
            from playwright.sync_api import sync_playwright
        except Exception:
            return (
                "Browser automation is unavailable because Playwright is not installed. "
                "Install it and run 'playwright install chromium' to enable browser workflows."
            )

        if not self._playwright_driver_available(playwright):
            return (
                "Browser automation is installed but the Playwright driver files are missing. "
                "Full browser control needs a working Playwright install."
            )

        executable_path = self._resolve_browser_path(browser_name)
        if executable_path is None:
            if browser_name == "chrome":
                fallback = self._resolve_browser_path("chromium")
                if fallback is None:
                    return "I couldn't find Chrome or Chromium on this system."
                executable_path = fallback
                browser_name = "chromium"
            else:
                return f"I couldn't find {browser_name} on this system."

        os.makedirs(self.profile_dir, exist_ok=True)
        try:
            self._playwright = sync_playwright().start()
            chromium = self._playwright.chromium
            self._context = chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                executable_path=executable_path,
                headless=False,
            )
            return self._context
        except Exception as exc:
            self._cleanup_playwright()
            logger.error("Failed to start browser automation: %s", exc)
            return self._playwright_help_message(exc)

    def _resolve_browser_path(self, browser_name):
        candidates = {
            "chrome": ["google-chrome", "google-chrome-stable"],
            "chromium": ["chromium", "chromium-browser"],
        }
        for candidate in candidates.get(browser_name, [browser_name]):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    def _open_url_fallback(self, url, browser_name, platform, reason="", action_label=""):
        executable_path = self._resolve_browser_path(browser_name)
        if executable_path is None and browser_name == "chrome":
            executable_path = self._resolve_browser_path("chromium")
            if executable_path:
                browser_name = "chromium"

        try:
            if executable_path:
                subprocess.Popen(
                    [executable_path, url],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["xdg-open", url],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            label = action_label or f"Opening {platform.replace('_', ' ')} in {browser_name}"
            if reason:
                logger.warning("Browser automation fallback used: %s", reason)
                return f"{label}. Browser automation is unavailable, so I opened the page directly."
            return f"{label}."
        except Exception as exc:
            logger.error("Browser fallback failed: %s", exc)
            if reason:
                return f"{reason}. I also couldn't open the URL directly: {exc}"
            return f"Failed to open {platform.replace('_', ' ')} in {browser_name}: {exc}"

    def _playwright_help_message(self, exc):
        message = str(exc)
        lowered = message.lower()
        if "cli.js" in message or "module not found" in lowered or "connection closed while reading from the driver" in lowered:
            return (
                "Browser automation is installed but the Playwright driver is not set up correctly. "
                "I can still open pages directly, but full browser control needs a working Playwright install."
            )
        return f"Failed to start browser automation: {message}"

    def _cleanup_playwright(self):
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        self._context = None
        self._pages = {}
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    def _playwright_driver_available(self, playwright_module):
        package_root = os.path.dirname(getattr(playwright_module, "__file__", "") or "")
        if not package_root:
            return False
        driver_dir = os.path.join(package_root, "driver")
        node_path = os.path.join(driver_dir, "node")
        cli_path = os.path.join(driver_dir, "package", "cli.js")
        return os.path.exists(driver_dir) and (os.path.exists(node_path) or os.path.exists(cli_path))
