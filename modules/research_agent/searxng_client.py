"""Robust SearxNG client used by the research agent.

Design goals:
  - Never depend on a single instance. Maintain a pool of public SearxNG
    endpoints and rotate through them on failure.
  - Per-instance circuit breaker. Bad instances are benched for a cooldown
    period instead of being retried on every query.
  - Light JSON normalization. Callers see one consistent shape regardless
    of which instance answered.
  - Graceful failure. If the whole pool is unhealthy at once, raise a
    typed error so the caller can fall through to a different backend.

Vane's TypeScript client (src/lib/searxng.ts) is single-instance and
expects SEARXNG_API_URL to point at a private instance. Here we adapt
that contract to public-instance reality: many things go wrong (rate
limits, captchas, instance maintenance), so the pool + cooldowns
matter more than the request itself.
"""
from __future__ import annotations

import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests

from core.logger import logger

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None  # type: ignore

# ---------------------------------------------------------------------------
# Default public instance pool
# ---------------------------------------------------------------------------
#
# Order is the *initial* preference. The client re-orders dynamically by
# health (recent failures push an instance down), so this is just the
# starting tier. Instances were picked from searx.space's reliability
# board; the user has confirmed searx.be works from their network.
#
# To override at runtime, set FRIDAY_SEARXNG_INSTANCES to a comma-
# separated list of base URLs.

# Order matters: confirmed JSON-API-enabled instances first (probed
# 2026-05), then rate-limited-but-usually-recovers, then JSON-disabled
# instances (we'll fall through to HTML parsing on those).
DEFAULT_INSTANCES: tuple[str, ...] = (
    # JSON API confirmed working
    "https://search.disroot.org",
    "https://searx.work",
    "https://nyc1.sx.ggtyler.dev",
    "https://search.hbubli.cc",
    # Often rate-limited but otherwise functional
    "https://searx.tiekoetter.com",
    "https://priv.au",
    "https://baresearch.org",
    "https://paulgo.io",
    "https://opnxng.com",
    # JSON disabled — used only via HTML fallback path
    "https://searx.be",
    "https://search.ononoki.org",
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) FRIDAY-ResearchAgent/0.3 (+SearxNG client)"
)


class SearxNGError(RuntimeError):
    """Raised when no SearxNG instance in the pool can answer a query."""


@dataclass
class _InstanceState:
    failures: int = 0
    banned_until: float = 0.0
    last_success_at: float = 0.0
    last_latency_s: float = 0.0


@dataclass
class SearxResult:
    title: str
    url: str
    snippet: str = ""
    engine: str = ""
    category: str = ""
    score: float = 0.0
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SearxNGClient:
    """Pool-aware SearxNG client.

    Thread-safe: a single instance can be shared across the research
    agent's threads. State updates (failure counters, cooldowns) are
    guarded by an internal lock.
    """

    # Number of consecutive failures before an instance is benched.
    FAILURE_THRESHOLD = 2
    # How long to bench an unhealthy instance, in seconds. Short enough
    # to recover within a single research session if the instance comes
    # back; long enough to stop hammering instances that are firmly down.
    COOLDOWN_S = 90.0
    # Per-request timeout. Public instances are sometimes slow under
    # load, so this is more generous than Vane's 10s.
    REQUEST_TIMEOUT_S = 12.0
    # Substrings that indicate a JS-based anti-bot challenge page rather
    # than a real SearxNG response. Treat as instance-down.
    _ANTI_BOT_MARKERS = (
        "making sure you&#39;re not a bot",
        "making sure you're not a bot",
        "anubis",
        "checking your browser",
        "ddos protection by cloudflare",
        "just a moment",
    )

    def __init__(
        self,
        instances: Iterable[str] | None = None,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float | None = None,
    ):
        env_instances = os.environ.get("FRIDAY_SEARXNG_INSTANCES", "").strip()
        if instances is None and env_instances:
            instances = [s.strip() for s in env_instances.split(",") if s.strip()]

        seeds = list(instances) if instances else list(DEFAULT_INSTANCES)
        # De-duplicate while preserving order.
        seen: set[str] = set()
        self._instances: list[str] = []
        for url in seeds:
            normalized = url.rstrip("/")
            if normalized and normalized not in seen:
                self._instances.append(normalized)
                seen.add(normalized)

        self._state: dict[str, _InstanceState] = {url: _InstanceState() for url in self._instances}
        self._user_agent = user_agent
        self._timeout = timeout_s if timeout_s is not None else self.REQUEST_TIMEOUT_S
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        categories: Iterable[str] | None = None,
        engines: Iterable[str] | None = None,
        language: str = "en",
        pageno: int = 1,
        max_results: int = 10,
    ) -> list[SearxResult]:
        """Run a SearxNG query against the pool.

        Tries instances in health order (healthiest first). Stops on the
        first instance that returns a usable JSON response. Raises
        SearxNGError only when *every* instance failed.
        """
        if not (query or "").strip():
            return []

        ordered = self._instances_by_health()
        if not ordered:
            # Pool exhausted — give one random instance a chance anyway
            # in case the cooldown is overly cautious.
            ordered = [random.choice(self._instances)] if self._instances else []
            if not ordered:
                raise SearxNGError("No SearxNG instances configured.")

        last_err: Exception | None = None
        for base_url in ordered:
            try:
                results = self._query_one(
                    base_url,
                    query,
                    categories=list(categories) if categories else None,
                    engines=list(engines) if engines else None,
                    language=language,
                    pageno=pageno,
                    max_results=max_results,
                )
                # An empty result list is a valid response — don't treat
                # that as an instance failure.
                return results
            except Exception as exc:
                last_err = exc
                logger.info(
                    "[searxng] %s failed for query=%r: %s",
                    base_url, query[:60], exc,
                )
                continue

        raise SearxNGError(
            f"All {len(ordered)} SearxNG instance(s) failed; last error: {last_err}"
        )

    def health_snapshot(self) -> list[dict]:
        """Return a debug-friendly view of pool state."""
        now = time.time()
        with self._lock:
            return [
                {
                    "url": url,
                    "failures": st.failures,
                    "banned_for_s": max(0.0, st.banned_until - now),
                    "last_success_age_s": (now - st.last_success_at) if st.last_success_at else None,
                    "last_latency_s": st.last_latency_s,
                }
                for url, st in self._state.items()
            ]

    # ------------------------------------------------------------------
    # Internal: HTTP
    # ------------------------------------------------------------------

    def _query_one(
        self,
        base_url: str,
        query: str,
        *,
        categories: list[str] | None,
        engines: list[str] | None,
        language: str,
        pageno: int,
        max_results: int,
    ) -> list[SearxResult]:
        params: dict[str, str] = {
            "q": query,
            "format": "json",
            "pageno": str(max(1, int(pageno))),
            "language": language or "en",
            "safesearch": "0",
        }
        if categories:
            params["categories"] = ",".join(categories)
        if engines:
            params["engines"] = ",".join(engines)

        started = time.monotonic()
        try:
            resp = requests.get(
                f"{base_url}/search",
                params=params,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            self._record_failure(base_url, exc)
            raise

        latency = time.monotonic() - started

        if resp.status_code == 429:
            # Rate-limited — bench longer than a normal failure to avoid
            # hammering the same instance.
            self._record_failure(base_url, "HTTP 429 rate-limited", weight=2)
            raise SearxNGError(f"{base_url} rate-limited")

        if resp.status_code >= 500:
            self._record_failure(base_url, f"HTTP {resp.status_code}")
            raise SearxNGError(f"{base_url} HTTP {resp.status_code}")

        if resp.status_code != 200:
            self._record_failure(base_url, f"HTTP {resp.status_code}")
            raise SearxNGError(f"{base_url} HTTP {resp.status_code}")

        # Anti-bot challenge pages can come back as 200 OK HTML even when
        # we asked for JSON. Detect them up front so we don't try to
        # parse the challenge as a results page.
        if self._is_anti_bot(resp.text):
            self._record_failure(base_url, "anti-bot challenge page", weight=3)
            raise SearxNGError(f"{base_url} served anti-bot challenge")

        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "json" not in content_type:
            # Some instances disable the JSON API. Try one HTML re-request
            # against this same instance before giving up — SearxNG's HTML
            # output is parseable. If even that fails, bench the instance
            # heavily so we don't try it on every query.
            html_results = self._query_one_html(
                base_url, query,
                categories=categories, engines=engines,
                language=language, pageno=pageno, max_results=max_results,
            )
            if html_results is not None:
                self._record_success(base_url, time.monotonic() - started)
                logger.info(
                    "[searxng] %s → %d results via HTML (q=%r)",
                    base_url, len(html_results), query[:60],
                )
                return html_results
            self._record_failure(base_url, f"non-JSON response ({content_type or 'unknown'})", weight=3)
            raise SearxNGError(f"{base_url} did not return JSON")

        try:
            data = resp.json()
        except ValueError as exc:
            self._record_failure(base_url, f"bad JSON: {exc}")
            raise SearxNGError(f"{base_url} returned malformed JSON") from exc

        raw_results = data.get("results") or []
        normalized: list[SearxResult] = []
        for raw in raw_results:
            try:
                url = (raw.get("url") or "").strip()
                title = (raw.get("title") or "").strip()
                if not url or not title:
                    continue
                normalized.append(SearxResult(
                    title=title,
                    url=url,
                    snippet=(raw.get("content") or "").strip(),
                    engine=raw.get("engine", "") or "",
                    category=raw.get("category", "") or "",
                    score=float(raw.get("score") or 0.0),
                    extra={
                        "publishedDate": raw.get("publishedDate"),
                        "thumbnail": raw.get("thumbnail") or raw.get("thumbnail_src"),
                        "img_src": raw.get("img_src"),
                    },
                ))
                if len(normalized) >= max_results:
                    break
            except Exception:
                continue

        self._record_success(base_url, latency)
        logger.info(
            "[searxng] %s → %d results in %.2fs (q=%r)",
            base_url, len(normalized), latency, query[:60],
        )
        return normalized

    def _query_one_html(
        self,
        base_url: str,
        query: str,
        *,
        categories: list[str] | None,
        engines: list[str] | None,
        language: str,
        pageno: int,
        max_results: int,
    ) -> list[SearxResult] | None:
        """Parse SearxNG's HTML results page when JSON is unavailable.

        Returns None on any failure so the caller can decide whether to
        bench the instance. SearxNG's HTML uses a stable ``article.result``
        layout with ``h3 a`` for the title link and ``p.content`` for the
        snippet — works across recent SearxNG versions.
        """
        if BeautifulSoup is None:
            return None

        params: dict[str, str] = {
            "q": query,
            "pageno": str(max(1, int(pageno))),
            "language": language or "en",
        }
        if categories:
            params["categories"] = ",".join(categories)
        if engines:
            params["engines"] = ",".join(engines)
        try:
            resp = requests.get(
                f"{base_url}/search",
                params=params,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                return None
            if self._is_anti_bot(resp.text):
                return None
            try:
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception:
                soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return None

        results: list[SearxResult] = []
        for node in soup.select("article.result, div.result"):
            link = node.select_one("h3 a, a.url_wrapper, a.result-link")
            if link is None:
                continue
            href = (link.get("href") or "").strip()
            title = link.get_text(" ", strip=True)
            if not href or not title:
                continue
            snippet_node = node.select_one("p.content, p.result-content, .content")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
            engine_node = node.select_one(".engines, .result-engine")
            engine = engine_node.get_text(" ", strip=True) if engine_node else ""
            results.append(SearxResult(
                title=title, url=href, snippet=snippet, engine=engine,
            ))
            if len(results) >= max_results:
                break
        return results

    @classmethod
    def _is_anti_bot(cls, body: str) -> bool:
        """Heuristic detection of JS proof-of-work / DDoS-protection pages."""
        if not body:
            return False
        sample = body[:2048].lower()
        return any(marker in sample for marker in cls._ANTI_BOT_MARKERS)

    # ------------------------------------------------------------------
    # Internal: health bookkeeping
    # ------------------------------------------------------------------

    def _instances_by_health(self) -> list[str]:
        """Return instances eligible to be queried, healthiest first."""
        now = time.time()
        with self._lock:
            eligible: list[tuple[str, _InstanceState]] = [
                (url, st) for url, st in self._state.items()
                if st.banned_until <= now
            ]
        # Healthiest = fewest recorded failures, with a slight preference
        # for instances that recently succeeded (lower last_latency wins
        # the tiebreak).
        eligible.sort(key=lambda kv: (kv[1].failures, kv[1].last_latency_s or 99.0))
        return [url for url, _ in eligible]

    def _record_success(self, url: str, latency_s: float) -> None:
        with self._lock:
            st = self._state.setdefault(url, _InstanceState())
            st.failures = 0
            st.banned_until = 0.0
            st.last_success_at = time.time()
            st.last_latency_s = latency_s

    def _record_failure(self, url: str, reason, *, weight: int = 1) -> None:
        with self._lock:
            st = self._state.setdefault(url, _InstanceState())
            st.failures += weight
            if st.failures >= self.FAILURE_THRESHOLD:
                st.banned_until = time.time() + self.COOLDOWN_S
                logger.warning(
                    "[searxng] benching %s for %.0fs after %d failure(s); last reason: %s",
                    url, self.COOLDOWN_S, st.failures, reason,
                )


# ---------------------------------------------------------------------------
# Convenience: process-wide singleton
# ---------------------------------------------------------------------------

_default_client: SearxNGClient | None = None
_default_lock = threading.Lock()


def get_default_client() -> SearxNGClient:
    """Return a process-wide SearxNGClient, creating it on first use."""
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = SearxNGClient()
        return _default_client
