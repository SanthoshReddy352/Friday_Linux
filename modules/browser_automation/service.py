import json
import os
import platform
import shutil
import subprocess
import time
from urllib.parse import quote_plus, urljoin

from core.logger import logger


class BrowserMediaService:
    def __init__(self, app):
        self.app = app
        self.profile_dir = ""
        self._playwright = None
        self._context = None
        self._pages = {}
        self._current_platform = None
        self._current_browser_name = None
        self._fallback_profile_root = os.path.join(
            os.path.expanduser("~"),
            ".cache",
            "friday",
            "browser-profile",
        )

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

    def scroll_page(self, platform="browser", pixels=420):
        page = self._pages.get(platform)
        if page is None:
            return f"I don't have an active {platform.replace('_', ' ')} browser page yet."
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            page.mouse.wheel(0, int(pixels))
        except Exception:
            page.evaluate("(amount) => window.scrollBy({ top: amount, left: 0, behavior: 'smooth' })", int(pixels))
        return f"Scrolled {platform.replace('_', ' ')}."

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
            # Click the body or some safe area to ensure the player window is focused for shortcuts
            try:
                page.mouse.click(10, 10)
            except:
                pass

            if action in ("pause", "resume"):
                page.keyboard.press("k")
                return f"{action.capitalize()}d {platform.replace('_', ' ')}."
            if action == "next":
                page.keyboard.press("Shift+N")
                return f"Skipped to next item on {platform.replace('_', ' ')}."
            if action == "previous":
                page.go_back()
                return f"Went back on {platform.replace('_', ' ')}."
            if action == "forward":
                page.keyboard.press("l")
                return f"Skipped forward on {platform.replace('_', ' ')}."
            if action == "backward":
                page.keyboard.press("j")
                return f"Reverted back on {platform.replace('_', ' ')}."
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
            target_url = self._resolve_first_result_url(page, first_result_selector, home_url)
            if target_url:
                page.goto(target_url, wait_until="domcontentloaded")
            else:
                locator = page.locator(first_result_selector).first
                locator.wait_for(state="attached", timeout=8000)
                try:
                    locator.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                locator.click(force=True)
                page.wait_for_load_state("domcontentloaded")
            self._prepare_media_page(page, platform)
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
        page = self._pages.get(platform)
        try:
            if page and not page.is_closed():
                page.bring_to_front()
                return page
        except Exception:
            page = None

        last_exc = None
        for attempt in range(2):
            context = self._ensure_context(browser_name)
            if isinstance(context, str):
                return context
            try:
                page = context.new_page()
                self._pages[platform] = page
                return page
            except Exception as exc:
                last_exc = exc
                if not self._is_closed_target_error(exc):
                    raise
                logger.warning(
                    "Browser page creation hit a closed context on attempt %s. Recreating browser automation context.",
                    attempt + 1,
                )
                self._cleanup_playwright()
        if last_exc is not None:
            logger.error("Browser automation session closed unexpectedly while creating a page: %s", last_exc)
            return self._playwright_help_message(last_exc)
        return "Browser automation could not create a browser page."

    def _ensure_context(self, browser_name):
        if self._context is not None and self._context_is_usable():
            return self._context
        if self._context is not None:
            logger.warning("Browser automation context was no longer usable. Reinitializing it.")
            self._cleanup_playwright()

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

        profile_settings = self._prepare_launch_profile_settings(browser_name)
        try:
            self._playwright = sync_playwright().start()
            chromium = self._playwright.chromium
            self._context = self._launch_context(chromium, executable_path, browser_name, profile_settings)
            return self._context
        except Exception as exc:
            if self._is_profile_in_use_error(exc) and profile_settings.get("mode") == "system":
                logger.warning(
                    "Chrome profile '%s' is busy. Falling back to a cloned signed-in profile snapshot for automation.",
                    profile_settings.get("profile_directory") or "default",
                )
                try:
                    cloned_settings = self._clone_profile_settings(profile_settings, browser_name)
                    self._context = self._launch_context(chromium, executable_path, browser_name, cloned_settings)
                    return self._context
                except Exception as clone_exc:
                    self._cleanup_playwright()
                    logger.error("Failed to start browser automation from cloned profile: %s", clone_exc)
                    return self._playwright_help_message(clone_exc)
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
        if "user data directory is already in use" in lowered or "singletonlock" in lowered:
            return (
                "Chrome is already using that profile, so Playwright could not attach to it. "
                "FRIDAY can usually reuse a signed-in snapshot automatically, but this launch still failed."
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
        self._current_browser_name = None
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

    def _context_is_usable(self):
        if self._context is None:
            return False
        try:
            _ = self._context.pages
            return True
        except Exception:
            return False

    def _resolve_profile_settings(self, browser_name):
        config = getattr(self.app, "config", None)
        use_system_profile = self._config_get(
            "browser_automation.use_system_profile",
            browser_name in {"chrome", "chromium"},
        )
        if use_system_profile:
            profile_root = self._config_get(
                f"browser_automation.{browser_name}_user_data_dir",
                self._default_profile_root(browser_name),
            )
            if profile_root and os.path.isdir(profile_root):
                profile_directory = self._config_get(
                    f"browser_automation.{browser_name}_profile_directory",
                    "",
                ) or self._detect_profile_directory(profile_root)
                launch_args = []
                if profile_directory and os.path.isdir(os.path.join(profile_root, profile_directory)):
                    launch_args.append(f"--profile-directory={profile_directory}")
                return {
                    "user_data_dir": profile_root,
                    "profile_directory": profile_directory,
                    "launch_args": launch_args,
                    "mode": "system",
                }

        fallback_root = os.path.join(self._fallback_profile_root, browser_name)
        return {
            "user_data_dir": fallback_root,
            "profile_directory": "",
            "launch_args": [],
            "mode": "isolated",
        }

    def _prepare_launch_profile_settings(self, browser_name):
        profile_settings = self._resolve_profile_settings(browser_name)
        if profile_settings.get("mode") != "system":
            return profile_settings

        try:
            return self._clone_profile_settings(profile_settings, browser_name)
        except Exception as exc:
            logger.warning(
                "Could not refresh a signed-in browser profile clone from '%s': %s. Falling back to an isolated automation profile.",
                profile_settings.get("user_data_dir"),
                exc,
            )
            isolated_root = os.path.join(self._fallback_profile_root, browser_name)
            return {
                "user_data_dir": isolated_root,
                "profile_directory": "",
                "launch_args": [],
                "mode": "isolated",
            }

    def _default_profile_root(self, browser_name):
        if browser_name == "chromium":
            return os.path.expanduser("~/.config/chromium")
        return os.path.expanduser("~/.config/google-chrome")

    def _detect_profile_directory(self, profile_root):
        local_state_path = os.path.join(profile_root, "Local State")
        try:
            if os.path.exists(local_state_path):
                with open(local_state_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                last_used = (
                    data.get("profile", {}).get("last_used")
                    or data.get("profile", {}).get("last_active_profiles", [None])[0]
                )
                if last_used and os.path.isdir(os.path.join(profile_root, last_used)):
                    return last_used
        except Exception as exc:
            logger.warning("Could not read browser Local State from %s: %s", local_state_path, exc)

        if os.path.isdir(os.path.join(profile_root, "Default")):
            return "Default"

        profile_dirs = sorted(
            name
            for name in os.listdir(profile_root)
            if name.startswith("Profile ") and os.path.isdir(os.path.join(profile_root, name))
        )
        return profile_dirs[0] if profile_dirs else ""

    def _config_get(self, key, default=None):
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            value = config.get(key, default)
            if value == "":
                return default
            return value
        return default

    def _is_closed_target_error(self, exc):
        message = str(exc).lower()
        return "target page, context or browser has been closed" in message

    def _is_profile_in_use_error(self, exc):
        message = str(exc).lower()
        return "processsingleton" in message or "user data directory is already in use" in message

    def _launch_context(self, chromium, executable_path, browser_name, profile_settings):
        self.profile_dir = profile_settings["user_data_dir"]
        self._current_browser_name = browser_name
        os.makedirs(self.profile_dir, exist_ok=True)
        launch_args = list(profile_settings["launch_args"])
        launch_args.extend(self._default_launch_args())
        logger.info(
            "Launching browser automation with profile root '%s'%s",
            self.profile_dir,
            f" and profile '{profile_settings['profile_directory']}'" if profile_settings["profile_directory"] else "",
        )
        return chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            executable_path=executable_path,
            headless=False,
            args=launch_args,
            ignore_default_args=self._playwright_ignore_default_args(),
            no_viewport=True,
        )

    def _clone_profile_settings(self, profile_settings, browser_name):
        source_root = profile_settings["user_data_dir"]
        profile_directory = profile_settings.get("profile_directory") or self._detect_profile_directory(source_root)
        clone_root = os.path.join(self._fallback_profile_root, f"{browser_name}-system-clone")
        if os.path.isdir(clone_root):
            shutil.rmtree(clone_root, ignore_errors=True)
        os.makedirs(clone_root, exist_ok=True)

        for filename in ("Local State", "First Run"):
            source_path = os.path.join(source_root, filename)
            if os.path.exists(source_path):
                shutil.copy2(source_path, os.path.join(clone_root, filename))

        profile_source = os.path.join(source_root, profile_directory) if profile_directory else ""
        if profile_source and os.path.isdir(profile_source):
            shutil.copytree(
                profile_source,
                os.path.join(clone_root, profile_directory),
                dirs_exist_ok=True,
                ignore=self._profile_clone_ignore,
            )

        return {
            "user_data_dir": clone_root,
            "profile_directory": profile_directory,
            "launch_args": [f"--profile-directory={profile_directory}"] if profile_directory else [],
            "mode": "cloned",
        }

    def _profile_clone_ignore(self, directory, names):
        ignored_names = {
            "SingletonLock",
            "SingletonSocket",
            "SingletonCookie",
            "lockfile",
            "Cache",
            "Code Cache",
            "GPUCache",
            "Crashpad",
            "GrShaderCache",
            "ShaderCache",
            "Safe Browsing",
            "OptimizationHints",
            "Subresource Filter",
            "CacheStorage",
            "ScriptCache",
        }
        return {
            name
            for name in names
            if name in ignored_names or name.endswith(".lock")
        }

    def _default_launch_args(self):
        args = ["--start-maximized"]
        if platform.system() == "Linux":
            args.extend(["--disable-vulkan", "--ozone-platform=x11"])
        return args

    def _playwright_ignore_default_args(self):
        return [
            "--password-store=basic",
            "--use-mock-keychain",
        ]

    def _resolve_first_result_url(self, page, selector, base_url):
        selectors = [f"{selector}:visible", selector]
        for candidate in selectors:
            locator = page.locator(candidate).first
            try:
                locator.wait_for(state="attached", timeout=8000)
                href = locator.get_attribute("href")
            except Exception:
                continue
            if href:
                return urljoin(base_url, href)
        return ""

    def _prepare_media_page(self, page, platform_name):
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        try:
            page.bring_to_front()
        except Exception:
            pass

        self._start_media_playback(page)
        if platform_name == "youtube":
            self._focus_browser_window(platform_name, fullscreen=False)
            self._enter_fullscreen(page)
            self._focus_browser_window(platform_name, fullscreen=False)
        else:
            self._exit_fullscreen(page)
            self._focus_browser_window(platform_name, fullscreen=False)

    def _start_media_playback(self, page):
        # Force playback via JavaScript instead of toggling keys.
        # This ensures the video starts if paused, but does nothing if already playing.
        try:
            page.evaluate(
                """
                () => {
                    const media = document.querySelector("video, audio");
                    if (media && media.paused) {
                        media.play().catch(() => {});
                    }
                }
                """
            )
        except Exception:
            pass

    def _media_paused(self, page):
        try:
            return page.evaluate(
                """
                () => {
                    const media = document.querySelector("video, audio");
                    if (!media) return null;
                    // If the video is still in a pending/loading state, don't assume it's paused
                    if (media.readyState < 2) return false; 
                    return media.paused;
                }
                """
            )
        except Exception:
            return None

    def _enter_fullscreen(self, page):
        for _ in range(3):
            if self._player_is_fullscreen(page):
                return
            if self._click_youtube_fullscreen_button(page):
                page.wait_for_timeout(700)
                if self._player_is_fullscreen(page):
                    return
            try:
                page.keyboard.press("f")
                page.wait_for_timeout(600)
            except Exception:
                return

    def _exit_fullscreen(self, page):
        try:
            is_fullscreen = bool(
                page.evaluate(
                    """
                    () => !!document.fullscreenElement
                    """
                )
            )
        except Exception:
            is_fullscreen = False

        if not is_fullscreen:
            return

        try:
            page.evaluate(
                """
                async () => {
                    if (document.fullscreenElement) {
                        await document.exitFullscreen();
                    }
                }
                """
            )
            page.wait_for_timeout(400)
        except Exception:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
            except Exception:
                pass

    def _player_is_fullscreen(self, page):
        try:
            return bool(
                page.evaluate(
                    """
                    () => {
                        const player = document.querySelector(".html5-video-player");
                        return !!(document.fullscreenElement || (player && player.classList.contains("ytp-fullscreen")));
                    }
                    """
                )
            )
        except Exception:
            return False

    def _click_youtube_fullscreen_button(self, page):
        # Hovering the player is usually enough to reveal the controls.
        # We avoid clicking the 'video' element directly because that toggles play/pause on YouTube.
        try:
            page.locator(".html5-video-player").first.hover(timeout=2000)
            page.wait_for_timeout(400)
        except Exception:
            pass
        selectors = (
            "button.ytp-fullscreen-button",
            ".ytp-fullscreen-button",
        )
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="attached", timeout=2500)
                locator.click(force=True)
                return True
            except Exception:
                continue
        return False

    def _focus_browser_window(self, platform_name, fullscreen=False):
        if platform.system() != "Linux":
            return
        if not shutil.which("wmctrl"):
            return

        title_terms = ["YouTube Music"] if platform_name == "youtube_music" else ["YouTube"]
        window_id = self._find_matching_window_id(title_terms)
        if not window_id:
            return

        commands = [
            ["wmctrl", "-ia", window_id],
            ["wmctrl", "-ir", window_id, "-b", "add,maximized_vert,maximized_horz"],
        ]
        if shutil.which("xdotool"):
            commands.insert(1, ["xdotool", "windowactivate", "--sync", window_id])
        if fullscreen:
            commands.append(["wmctrl", "-ir", window_id, "-b", "add,fullscreen"])
        else:
            commands.append(["wmctrl", "-ir", window_id, "-b", "remove,fullscreen"])

        for command in commands:
            try:
                subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
            except Exception:
                continue

    def _find_matching_window_id(self, title_terms):
        deadline = time.monotonic() + 5
        title_terms = [term.lower() for term in title_terms]
        while time.monotonic() < deadline:
            try:
                result = subprocess.run(
                    ["wmctrl", "-lx"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            except Exception:
                return ""
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            for line in reversed(lines):
                lowered = line.lower()
                if not any(term in lowered for term in title_terms):
                    continue
                if "google-chrome" not in lowered and "chromium" not in lowered:
                    continue
                return line.split()[0]
            time.sleep(0.25)
        return ""
