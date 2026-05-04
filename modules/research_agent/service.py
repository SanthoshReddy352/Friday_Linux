"""Research-agent service — Vane-inspired agentic research pipeline.

Inspired by Vane (MIT License): https://github.com/ItzCrazyKns/Vane

Pipeline
--------
1. Classifier  – LLM classifies the query: skip_search / academic / discussion,
                 and generates a standalone reformulation of the topic.
2. Researcher  – Agentic loop where the LLM picks tools each iteration:
                   web_search · academic_search · social_search · scrape_url · done
   Iteration budgets (matched to Vane): speed=2, balanced=6, quality=25
3. Writer      – Final synthesis with numbered [N] citations.

Search backend
--------------
Vane queries a SearxNG instance for everything (general / science / social
categories). We mirror that — see ``searxng_client.SearxNGClient``. Public
SearxNG instances fail often, so the client maintains a pool with per-
instance circuit breakers. If the entire pool is unreachable we fall
through to a DuckDuckGo HTML scrape so the agent always returns *something*.

Outputs  ~/Documents/friday-research/<slug>/
  00-summary.md     ← synthesis with citations
  01-<source>.md …  ← per-source notes
  sources.md        ← raw URL list
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from urllib.parse import quote_plus, urlparse

import numpy as np
import requests

from core.logger import logger

from .searxng_client import (
    SearxNGClient,
    SearxNGError,
    SearxResult,
    get_default_client as _get_default_searxng,
)

# Optional deps — keep imports lazy so the module loads even on a stripped
# environment. Each fallback path checks for None and degrades gracefully.
try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None  # type: ignore

try:
    import html2text as _html2text_lib  # type: ignore
    _HAS_HTML2TEXT = True
except ImportError:
    _html2text_lib = None  # type: ignore
    _HAS_HTML2TEXT = False

try:
    import trafilatura  # type: ignore
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) FRIDAY-ResearchAgent/0.2"
)
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "friday-research")
MAX_BYTES_PER_PAGE = 750_000
REQUEST_TIMEOUT_S = 12.0

# Vane-inspired research modes (speed=2 iters, balanced=6, quality=25)
MODES: dict[str, dict] = {
    "speed":    {"max_iter": 2,  "max_sources": 4,  "final_tokens": 600},
    "balanced": {"max_iter": 6,  "max_sources": 8,  "final_tokens": 900},
    "quality":  {"max_iter": 25, "max_sources": 12, "final_tokens": 1800},
}
DEFAULT_MODE = "balanced"

# Slightly longer than the old 3s to give the agentic loop room to breathe.
# Voice turns still get priority via the inference lock — this is just the
# acquire timeout before falling back to a heuristic action.
RESEARCH_INFERENCE_TIMEOUT_S = 60.0

# One concurrent research workflow at a time.
_RESEARCH_SEMAPHORE = threading.BoundedSemaphore(1)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ResearchSource:
    title: str
    url: str
    snippet: str = ""
    origin: str = "web"
    body: str = ""
    summary: str = ""
    error: str = ""


@dataclass
class ResearchReport:
    topic: str
    folder: str
    summary_path: str
    sources: list[ResearchSource] = field(default_factory=list)
    duration_s: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ResearchAgentService:
    def __init__(self, app, searx_client: SearxNGClient | None = None):
        self.app = app
        # Caller can inject a pre-built client (tests, custom pool). Otherwise
        # we share the process-wide singleton so all research turns benefit
        # from a common circuit-breaker view.
        self._searx_override = searx_client

    @property
    def searx(self) -> SearxNGClient:
        return self._searx_override or _get_default_searxng()

    # ------------------------------------------------------------------
    # Public entry — non-blocking
    # ------------------------------------------------------------------

    def start_research(
        self,
        topic: str,
        max_sources: int = 5,
        on_complete: Callable[[ResearchReport], None] | None = None,
        mode: str = DEFAULT_MODE,
    ) -> threading.Thread:
        thread = threading.Thread(
            target=self._run_safely,
            args=(topic, max_sources, on_complete, mode),
            daemon=True,
            name="friday-research",
        )
        thread.start()
        return thread

    def _run_safely(self, topic, max_sources, on_complete, mode):
        try:
            report = self.run_research(topic, max_sources=max_sources, mode=mode)
        except Exception as exc:
            logger.exception("Research run failed: %s", exc)
            report = ResearchReport(
                topic=topic, folder="", summary_path="",
                error=f"Research failed: {exc}",
            )
        if on_complete is not None:
            try:
                on_complete(report)
            except Exception:
                logger.exception("Research completion callback failed")

    # ------------------------------------------------------------------
    # Pipeline entry
    # ------------------------------------------------------------------

    def run_research(
        self,
        topic: str,
        max_sources: int = 5,
        mode: str = DEFAULT_MODE,
    ) -> ResearchReport:
        with _RESEARCH_SEMAPHORE:
            return self._run_research_locked(topic, max_sources, mode)

    def _run_research_locked(
        self,
        topic: str,
        max_sources: int,
        mode: str,
    ) -> ResearchReport:
        topic = (topic or "").strip()
        if not topic:
            return ResearchReport(topic=topic, folder="", summary_path="", error="No topic provided.")

        cfg = MODES.get(mode, MODES[DEFAULT_MODE])
        max_iter = cfg["max_iter"]
        final_tokens = cfg["final_tokens"]
        max_sources = max(1, min(int(max_sources or 5), cfg["max_sources"]))

        started_at = time.monotonic()
        slug = self._slugify(topic)
        when = datetime.now()
        folder = os.path.join(DEFAULT_DIR, f"{when.strftime('%Y-%m-%d_%H%M')}_{slug}")
        os.makedirs(folder, exist_ok=True)

        logger.info("[research] Starting topic=%r mode=%s → %s", topic, mode, folder)

        # Step 1: classify the query (Vane classifier)
        classification = self._classify_query(topic)
        standalone = classification.get("query") or topic
        logger.info("[research] Classification: %s", classification)

        if classification.get("skip_search"):
            sources: list[ResearchSource] = []
            synthesis = self._write_from_knowledge(topic, final_tokens)
        else:
            # Step 2: agentic researcher loop (Vane researcher)
            sources = self._researcher_loop(
                standalone,
                classification=classification,
                max_iter=max_iter,
                max_sources=max_sources,
            )
            if not sources:
                report = ResearchReport(
                    topic=topic, folder=folder, summary_path="",
                    error="No search results were available for that topic.",
                )
                self._write_failure_summary(folder, report)
                return report

            # Step 3: per-source summarization (parallel)
            with ThreadPoolExecutor(max_workers=min(len(sources), 3)) as pool:
                futs = {pool.submit(self._summarize_source, s, topic): s for s in sources}
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception as exc:
                        logger.warning("[research] Source summarize failed: %s", exc)

            # Step 4: writer synthesis with citations (Vane writer)
            synthesis = self._writer_synthesis(topic, sources, final_tokens)

        summary_path = self._write_outputs(folder, topic, synthesis, sources, when)
        duration = time.monotonic() - started_at
        successful = [s for s in sources if s.summary and not s.error]

        report = ResearchReport(
            topic=topic, folder=folder, summary_path=summary_path,
            sources=sources, duration_s=duration,
        )
        logger.info(
            "[research] Done topic=%r mode=%s in %.1fs (%d/%d sources) → %s",
            topic, mode, duration, len(successful), len(sources), summary_path,
        )
        return report

    # ------------------------------------------------------------------
    # Step 1 — Classifier (adapted from Vane src/lib/prompts/search/classifier.ts)
    # ------------------------------------------------------------------

    def _classify_query(self, topic: str) -> dict:
        """Classify the query to guide the research strategy.

        Returns a dict with keys: skip_search, academic, discussion, query.
        Mirrors Vane's classifier labels: skipSearch, academicSearch,
        discussionSearch, standaloneFollowUp.
        """
        default = {"skip_search": False, "academic": False, "discussion": False, "query": topic}
        llm, role = self._get_llm()
        if llm is None:
            return default

        prompt = (
            "Analyze this research query and output JSON only (no other text).\n"
            f'Query: "{topic}"\n\n'
            "Required output format:\n"
            '{"skip_search": bool, "academic": bool, "discussion": bool, "query": "standalone question"}\n\n'
            "Rules:\n"
            "- skip_search: true ONLY for simple arithmetic or greetings — ALWAYS FALSE when uncertain\n"
            "- academic: true if user wants research papers, studies, scientific data, or citations\n"
            "- discussion: true if user wants opinions, reviews, community experiences, or Reddit-style discussion\n"
            "- query: self-contained reformulation as a clear research question with full context\n"
            "IMPORTANT: ALWAYS SET skip_search TO FALSE IF YOU ARE UNCERTAIN OR IF THE QUERY IS AMBIGUOUS."
        )

        def _infer():
            try:
                if hasattr(llm, "create_chat_completion"):
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=120,
                        temperature=0.1,
                    )
                    text = (resp["choices"][0]["message"]["content"] or "").strip()
                else:
                    resp = llm(prompt, max_tokens=120, temperature=0.1)
                    text = (resp["choices"][0].get("text") or "").strip()
                result = self._extract_json(text)
                if isinstance(result, dict):
                    result.setdefault("query", topic)
                    return result
                return default
            except Exception as exc:
                logger.warning("[research] Classifier failed: %s", exc)
                return default

        result = self._run_inference(role, _infer, fallback=default)
        return result if isinstance(result, dict) else default

    # ------------------------------------------------------------------
    # Step 2 — Researcher agentic loop (Vane src/lib/agents/search/researcher/index.ts)
    # ------------------------------------------------------------------

    def _researcher_loop(
        self,
        query: str,
        classification: dict,
        max_iter: int,
        max_sources: int,
    ) -> list[ResearchSource]:
        """Iterative tool-calling loop: LLM decides what to search/scrape each step.

        Mirrors Vane's Researcher class with tools: web_search, academic_search,
        scrape_url, done. Iterations: speed=2, balanced=6, quality=15.
        """
        sources: list[ResearchSource] = []
        seen_urls: set[str] = set()
        action_history: list[str] = []

        for iteration in range(max_iter):
            if len(sources) >= max_sources:
                break

            # Reasoning preamble (Vane balanced/quality: think before acting)
            # Only run in balanced/quality modes AND when the model lock is
            # immediately available — skip rather than block if it's busy.
            if iteration > 0 and max_iter > 2:
                llm_check, role_check = self._get_llm()
                preamble_lock = self._inference_lock(role_check) if llm_check is not None else None
                lock_free = (preamble_lock is not None and preamble_lock.acquire(timeout=0))
                if lock_free:
                    preamble_lock.release()
                if llm_check is not None and lock_free:
                    reasoning = self._reasoning_preamble(
                        query=query, sources=sources, history=action_history,
                        iteration=iteration, max_iter=max_iter,
                    )
                    if reasoning:
                        action_history.append(f"[reasoning] {reasoning}")

            action = self._pick_action(
                query=query,
                classification=classification,
                sources=sources,
                history=action_history,
                iteration=iteration,
                max_iter=max_iter,
            )

            action_name = (action.get("action") or "").lower()
            logger.info("[research] Iter %d/%d → action=%s", iteration + 1, max_iter, action_name)

            if not action_name or action_name == "done":
                break

            elif action_name == "web_search":
                q = (action.get("query") or query).strip()
                new = self._search_web(q, limit=max_sources * 2)
                # In discussion mode, mix in social results so the LLM has
                # community voices to draw on even if it didn't pick the
                # social_search tool explicitly.
                if classification.get("discussion") and not any(self._looks_social(s.url) for s in new):
                    new = new + self._search_social(q, limit=3)
                added = self._merge_sources(sources, new, seen_urls, max_sources)
                action_history.append(f"web_search({q!r}) → {added} new results")

            elif action_name == "academic_search":
                q = (action.get("query") or query).strip()
                new = self._search_academic(q, limit=max(3, max_sources // 2))
                added = self._merge_sources(sources, new, seen_urls, max_sources)
                action_history.append(f"academic_search({q!r}) → {added} papers")

            elif action_name == "social_search":
                q = (action.get("query") or query).strip()
                new = self._search_social(q, limit=max(3, max_sources // 2))
                added = self._merge_sources(sources, new, seen_urls, max_sources)
                action_history.append(f"social_search({q!r}) → {added} discussions")

            elif action_name == "scrape_url":
                url = (action.get("url") or "").strip()
                normalized = self._normalize_url(url) if url else ""
                if url and normalized and normalized not in seen_urls and not self._is_skippable_url(normalized):
                    body = self._fetch_main_text(url)
                    if body:
                        src = ResearchSource(
                            title=action.get("title") or url,
                            url=url, snippet=body[:300], body=body, origin="scrape",
                        )
                        sources.append(src)
                        seen_urls.add(normalized)
                        action_history.append(f"scrape_url({url!r}) → {len(body)} chars")
                    else:
                        action_history.append(f"scrape_url({url!r}) → failed")
                else:
                    action_history.append(f"scrape_url({url!r}) → skipped")

            else:
                logger.warning("[research] Unknown action %r — stopping loop", action_name)
                break

        return sources

    def _reasoning_preamble(
        self,
        query: str,
        sources: list[ResearchSource],
        history: list[str],
        iteration: int,
        max_iter: int,
    ) -> str:
        """Brief LLM reasoning step before choosing the next search action.

        Mirrors Vane's __reasoning_preamble tool used in balanced/quality modes.
        Returns a short reasoning string to add to action_history so the action
        picker has more context.
        """
        llm, role = self._get_llm()
        if llm is None:
            return ""

        gathered = self._format_gathered(sources, max_chars=300)
        history_text = "\n".join(f"  {h}" for h in history[-3:]) if history else "  (none)"

        prompt = (
            f'Research topic: "{query}"\n'
            f"Sources so far ({len(sources)}): {gathered}\n"
            f"Recent actions:\n{history_text}\n\n"
            f"Iteration {iteration + 1}/{max_iter}. "
            "In one sentence, what should the next research action focus on and why? "
            "Be specific (e.g. 'search for mechanism details' or 'scrape the overview page'). "
            "No JSON, just one plain sentence."
        )

        def _infer():
            try:
                if hasattr(llm, "create_chat_completion"):
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=60, temperature=0.3,
                    )
                    return (resp["choices"][0]["message"]["content"] or "").strip()
                resp = llm(prompt, max_tokens=60, temperature=0.3)
                return (resp["choices"][0].get("text") or "").strip()
            except Exception:
                return ""

        result = self._run_inference(role, _infer, fallback="")
        return (result or "").strip()

    def _pick_action(
        self,
        query: str,
        classification: dict,
        sources: list[ResearchSource],
        history: list[str],
        iteration: int,
        max_iter: int,
    ) -> dict:
        """Ask the LLM for the next research action (JSON).

        Heuristic fallback when LLM is unavailable or times out.
        """
        # Heuristic fallback — multi-step productive schedule
        academic = classification.get("academic", False)
        # Identify sources that have no body fetched yet (candidates for scraping)
        unscraped = [s for s in sources if not s.body]

        if iteration == 0:
            if academic:
                fallback = {"action": "academic_search", "query": query}
            else:
                fallback = {"action": "web_search", "query": query}
        elif iteration == 1:
            if academic and not any(s.origin == "arxiv" for s in sources):
                fallback = {"action": "academic_search", "query": query}
            else:
                fallback = {"action": "web_search", "query": f"{query} explained overview"}
        elif iteration == 2:
            # Scrape first unscraped source if available
            if unscraped:
                target = unscraped[0]
                fallback = {"action": "scrape_url", "url": target.url, "title": target.title}
            else:
                fallback = {"action": "web_search", "query": f"{query} 2024 2025"}
        elif iteration == 3:
            if len(sources) < max_sources:
                fallback = {"action": "web_search", "query": f"{query} 2024 2025"}
            else:
                fallback = {"action": "done"}
        elif iteration == 4:
            # Scrape second unscraped source if available
            unscraped_now = [s for s in sources if not s.body]
            if len(unscraped_now) > 1:
                target = unscraped_now[1]
                fallback = {"action": "scrape_url", "url": target.url, "title": target.title}
            elif unscraped_now:
                target = unscraped_now[0]
                fallback = {"action": "scrape_url", "url": target.url, "title": target.title}
            else:
                fallback = {"action": "done"}
        else:
            fallback = {"action": "done"}

        llm, role = self._get_llm()
        if llm is None:
            return fallback

        is_last = (iteration >= max_iter - 1)
        last_hint = " This is your LAST iteration — call done." if is_last else ""
        sources_text = self._format_gathered(sources, max_chars=500)
        history_text = "\n".join(f"  {h}" for h in history[-4:]) if history else "  (none)"

        discussion_hint = " (discussion mode is on — prefer social_search for opinions/reviews)" \
            if classification.get("discussion") else ""

        prompt = (
            f'Research topic: "{query}"\n\n'
            f"Sources gathered so far ({len(sources)}):\n{sources_text}\n\n"
            f"Recent actions:\n{history_text}\n\n"
            "Available tools:\n"
            "  web_search(query)       – general web search via SearxNG\n"
            "  academic_search(query)  – research papers (arXiv, Scholar) via SearxNG\n"
            "  social_search(query)    – Reddit / community discussions via SearxNG\n"
            "  scrape_url(url)         – fetch full content from a specific URL\n"
            "  done()                  – finish research\n\n"
            f"Iteration {iteration + 1}/{max_iter}.{last_hint}{discussion_hint}\n"
            "Output ONE JSON action and nothing else:\n"
            '{"action": "web_search", "query": "..."}\n'
            '{"action": "academic_search", "query": "..."}\n'
            '{"action": "social_search", "query": "..."}\n'
            '{"action": "scrape_url", "url": "https://...", "title": "..."}\n'
            '{"action": "done"}'
        )

        def _infer():
            try:
                if hasattr(llm, "create_chat_completion"):
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=80,
                        temperature=0.2,
                    )
                    text = (resp["choices"][0]["message"]["content"] or "").strip()
                else:
                    resp = llm(prompt, max_tokens=80, temperature=0.2)
                    text = (resp["choices"][0].get("text") or "").strip()
                parsed = self._extract_json(text)
                if isinstance(parsed, dict) and "action" in parsed:
                    return parsed
                return fallback
            except Exception as exc:
                logger.warning("[research] Action pick failed iter %d: %s", iteration, exc)
                return fallback

        result = self._run_inference(role, _infer, fallback=fallback)
        return result if isinstance(result, dict) else fallback

    def _format_gathered(self, sources: list[ResearchSource], max_chars: int = 500) -> str:
        if not sources:
            return "  (nothing gathered yet)"
        lines = [f"  [{i}] {s.title[:70]} ({s.origin})" for i, s in enumerate(sources, 1)]
        return "\n".join(lines)[:max_chars]

    def _merge_sources(
        self,
        sources: list[ResearchSource],
        new: list[ResearchSource],
        seen_urls: set[str],
        max_sources: int,
    ) -> int:
        added = 0
        for s in new:
            if len(sources) >= max_sources:
                break
            n = self._normalize_url(s.url)
            if not n or n in seen_urls or self._is_skippable_url(n):
                continue
            seen_urls.add(n)
            sources.append(s)
            added += 1
        return added

    # ------------------------------------------------------------------
    # Step 3 — Per-source summarization
    # ------------------------------------------------------------------

    def _summarize_source(self, source: ResearchSource, topic: str) -> None:
        """Fetch body if missing, then LLM-summarize the source (mutates in-place)."""
        if not source.body:
            body = self._fetch_main_text(source.url)
            if not body:
                source.error = "couldn't fetch or parse this page"
                return
            source.body = body

        content = (source.snippet + "\n\n" + source.body).strip()[:5_000]
        source.summary = self._llm_source_summary(topic, source.title, source.url, content)

    def _llm_source_summary(self, topic: str, title: str, url: str, content: str) -> str:
        if not content:
            return ""
        llm, role = self._get_llm()
        extractive_fallback = self._extractive_summary(content[:3000], topic, n_sentences=5)
        if llm is None:
            return extractive_fallback

        prompt = (
            f'Summarize this source for a research briefing on "{topic}".\n'
            f"Title: {title}\n\n"
            "Write 4-6 bullet points on key claims and relevance. "
            "Use '- ' bullets. No preamble.\n\n"
            f"Content:\n{content}"
        )

        def _infer():
            try:
                if hasattr(llm, "create_chat_completion"):
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=220,
                        temperature=0.3,
                    )
                    return (resp["choices"][0]["message"]["content"] or "").strip()
                resp = llm(prompt, max_tokens=220, temperature=0.3)
                return (resp["choices"][0].get("text") or "").strip()
            except Exception as exc:
                logger.warning("[research] Source summary failed for %s: %s", url, exc)
                return extractive_fallback

        result = self._run_inference(role, _infer, fallback=extractive_fallback)
        return result or extractive_fallback

    # ------------------------------------------------------------------
    # Step 4 — Writer synthesis with citations (Vane src/lib/prompts/search/writer.ts)
    # ------------------------------------------------------------------

    def _writer_synthesis(self, topic: str, sources: list[ResearchSource], final_tokens: int) -> str:
        """Synthesize all source summaries into a final briefing with [N] citations."""
        chunks = []
        for i, s in enumerate(sources, 1):
            if not s.summary:
                continue
            chunks.append(f"[{i}] {s.title}\n{s.summary.strip()}")
        if not chunks:
            return (
                f"No usable sources were retrieved for '{topic}'. "
                "The raw search links are listed in the Sources section."
            )

        is_quality = final_tokens >= 1400
        bundle = "\n\n".join(chunks)[:6_000]
        llm, role = self._get_llm()
        if llm is None:
            return self._extractive_writer_report(topic, sources)

        if is_quality:
            format_instructions = (
                "Write a comprehensive research report in Markdown.\n"
                "Structure:\n"
                "## Summary\n(2-3 sentence headline takeaway)\n\n"
                "## Key Findings\n(6-10 detailed bullet points)\n\n"
                "## Analysis\n(2-3 paragraphs of deeper analysis)\n\n"
                "## Open Questions\n(3-5 bullet points on gaps or future directions)\n\n"
                "CITATION RULES — follow strictly:\n"
                "- Cite EVERY SINGLE fact, statement, and sentence with [N] inline.\n"
                "- Every sentence must include at least one citation.\n"
                "- Use numbered brackets like [1], [2], [1][3] for multiple sources.\n"
            )
        else:
            format_instructions = (
                "Write a research briefing in Markdown.\n"
                "Structure:\n"
                "## Summary\n(1-2 sentence headline takeaway)\n\n"
                "## Key Findings\n(4-6 bullet points)\n\n"
                "## Open Questions\n(1-2 bullet points)\n\n"
                "CITATION RULES — follow strictly:\n"
                "- Cite every fact and statement with [N] inline.\n"
                "- Every sentence must include at least one citation.\n"
                "- Use numbered brackets like [1], [2].\n"
            )

        prompt = (
            f'Write a research briefing about "{topic}" using the {len(chunks)} sources below.\n\n'
            f"{format_instructions}\n"
            f"Sources:\n{bundle}"
        )

        extractive_report = self._extractive_writer_report(topic, sources)

        def _infer():
            try:
                if hasattr(llm, "create_chat_completion"):
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=final_tokens,
                        temperature=0.4,
                    )
                    return (resp["choices"][0]["message"]["content"] or "").strip()
                resp = llm(prompt, max_tokens=final_tokens, temperature=0.4)
                return (resp["choices"][0].get("text") or "").strip()
            except Exception as exc:
                logger.warning("[research] Writer synthesis failed: %s", exc)
                return extractive_report

        # Give the writer a longer lock window — it's the final and most important call.
        lock = self._inference_lock(role)
        acquired = lock.acquire(timeout=RESEARCH_INFERENCE_TIMEOUT_S * 2)
        if not acquired:
            logger.info("[research] Writer lock busy — using extractive fallback")
            return extractive_report
        try:
            result = _infer()
        finally:
            lock.release()
        return result or extractive_report

    # ------------------------------------------------------------------
    # Extractive helpers (numpy-based, no LLM required)
    # ------------------------------------------------------------------

    def _extractive_summary(self, text: str, topic: str, n_sentences: int = 5) -> str:
        """Return top-N sentences from *text* ranked by relevance to *topic*.

        Scoring: 2× word-overlap with topic words + document word frequency.
        Sentences shorter than 6 words are discarded.  Top-N are returned in
        original document order, joined with spaces.
        """
        if not text:
            return ""

        # Split into sentences on sentence-ending punctuation
        raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        sentences = [s.strip() for s in raw_sentences if len(s.split()) >= 6]
        if not sentences:
            return text.strip()[:500]

        # Build document word-frequency table
        all_words = re.findall(r"[a-z]+", text.lower())
        if not all_words:
            return sentences[0] if sentences else ""
        freq = {}
        for w in all_words:
            freq[w] = freq.get(w, 0) + 1
        max_freq = max(freq.values()) or 1

        # Topic words (filter stopwords crudely by length ≥ 4)
        topic_words = {w for w in re.findall(r"[a-z]+", topic.lower()) if len(w) >= 4}

        scores = np.zeros(len(sentences), dtype=float)
        for idx, sent in enumerate(sentences):
            words = re.findall(r"[a-z]+", sent.lower())
            if not words:
                continue
            # Normalised document frequency score
            freq_score = sum(freq.get(w, 0) / max_freq for w in words) / len(words)
            # Topic overlap score (2× weight)
            overlap_score = 2.0 * sum(1 for w in words if w in topic_words) / max(len(words), 1)
            scores[idx] = freq_score + overlap_score

        n = min(n_sentences, len(sentences))
        top_indices = sorted(np.argsort(scores)[-n:].tolist())
        return " ".join(sentences[i] for i in top_indices)

    def _extractive_writer_report(self, topic: str, sources: list[ResearchSource]) -> str:
        """Build a structured Markdown research report using only extractive sentences.

        Used when no LLM is available or the writer inference lock is busy.
        Structure:
          ## Summary      — top 3 sentences from all source summaries combined
          ## Key Findings — one top sentence per source with [N] citation
          ## Open Questions — 2 generic gap sentences
        """
        all_text = " ".join(s.summary for s in sources if s.summary).strip()
        if not all_text:
            return (
                f"No usable sources were retrieved for '{topic}'. "
                "The raw search links are listed in the Sources section."
            )

        # Summary section — top 3 from combined corpus
        summary_sentences = self._extractive_summary(all_text, topic, n_sentences=3)

        # Key Findings — best sentence from each source with citation
        bullets: list[str] = []
        for i, src in enumerate(sources, 1):
            if not src.summary:
                continue
            best = self._extractive_summary(src.summary, topic, n_sentences=1)
            if best:
                bullets.append(f"- {best} [{i}]")
            if len(bullets) >= 7:
                break

        findings_block = "\n".join(bullets) if bullets else "- (no source summaries available)"

        open_q = (
            f"- What are the most recent developments in {topic} not covered by these sources?\n"
            f"- What methodological details or primary data would be needed to verify these claims?"
        )

        return (
            f"## Summary\n\n{summary_sentences}\n\n"
            f"## Key Findings\n\n{findings_block}\n\n"
            f"## Open Questions\n\n{open_q}"
        )

    def _write_from_knowledge(self, topic: str, final_tokens: int) -> str:
        """Answer from LLM general knowledge when classifier sets skip_search=True."""
        llm, role = self._get_llm()
        if llm is None:
            return f"Research topic: {topic}\n(No LLM available for synthesis.)"
        prompt = (
            f'Write a concise briefing about "{topic}" from your knowledge.\n'
            "Include: headline takeaway, 3-5 key facts, any caveats or open questions.\n"
            "Plain text, no preamble."
        )

        def _infer():
            try:
                if hasattr(llm, "create_chat_completion"):
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=final_tokens,
                        temperature=0.4,
                    )
                    return (resp["choices"][0]["message"]["content"] or "").strip()
                resp = llm(prompt, max_tokens=final_tokens, temperature=0.4)
                return (resp["choices"][0].get("text") or "").strip()
            except Exception as exc:
                logger.warning("[research] Knowledge synthesis failed: %s", exc)
                return f"Research topic: {topic} — synthesis unavailable."

        return self._run_inference(role, _infer, fallback=f"Research topic: {topic}")

    # ------------------------------------------------------------------
    # Search backends
    # ------------------------------------------------------------------

    # ---- Layered search backends ------------------------------------------
    #
    # Priority order is the same Vane uses (SearxNG first), but every layer
    # has a direct-backend fallback so research never hard-fails on a
    # transient SearxNG outage. Public SearxNG instances often serve JS
    # anti-bot challenges instead of results — when that happens, we drop
    # straight through to the direct backends below.

    def _search_web(self, topic: str, limit: int) -> list[ResearchSource]:
        """General web search. SearxNG → DuckDuckGo HTML."""
        searx = self._try_searx(topic, categories=["general"], limit=limit, default_origin="web")
        if searx:
            return searx
        return self._search_duckduckgo_fallback(topic, limit)

    def _search_academic(self, topic: str, limit: int) -> list[ResearchSource]:
        """Academic search. SearxNG (science) → arXiv API → DDG site:arxiv.org."""
        searx = self._try_searx(topic, categories=["science"], limit=limit, default_origin="academic")
        if searx:
            return searx
        arxiv = self._search_arxiv_fallback(topic, limit)
        if arxiv:
            return arxiv
        return self._search_duckduckgo_fallback(f"site:arxiv.org {topic}", limit)

    def _search_social(self, topic: str, limit: int) -> list[ResearchSource]:
        """Discussion search. SearxNG (social) → Reddit JSON → DDG site:reddit.com."""
        searx = self._try_searx(topic, categories=["social_media"], limit=limit, default_origin="social")
        if searx:
            return searx
        reddit = self._search_reddit_fallback(topic, limit)
        if reddit:
            return reddit
        return self._search_duckduckgo_fallback(f"site:reddit.com {topic}", limit)

    def _try_searx(
        self, topic: str, *, categories: list[str], limit: int, default_origin: str,
    ) -> list[ResearchSource]:
        """Single attempt against the SearxNG pool. Empty list = couldn't get
        results (caller should fall through). Never raises."""
        try:
            results = self.searx.search(topic, categories=categories, max_results=limit)
        except SearxNGError as exc:
            logger.info("[research] SearxNG pool unavailable for %s: %s", categories, exc)
            return []
        except Exception as exc:
            logger.warning("[research] SearxNG %s search errored: %s", categories, exc)
            return []
        return [self._searx_to_source(r, default_origin=default_origin) for r in results]

    def _searx_to_source(self, r: SearxResult, *, default_origin: str) -> ResearchSource:
        # Pick a more specific origin label when SearxNG tells us the engine.
        origin = (r.engine or default_origin or "web").lower().strip() or default_origin
        return ResearchSource(
            title=r.title,
            url=r.url,
            snippet=r.snippet,
            origin=origin,
        )

    def _looks_social(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(s in host for s in (
            "reddit.com", "old.reddit.com", "news.ycombinator.com",
            "stackexchange.com", "stackoverflow.com",
        ))

    # ---- Fallback backends (used only when SearxNG is unreachable) --------

    def _search_duckduckgo_fallback(self, topic: str, limit: int) -> list[ResearchSource]:
        """Last-ditch DuckDuckGo HTML scrape used only when the SearxNG pool
        is fully unreachable. Vane doesn't ship this — it's our safety net
        so research never hard-fails."""
        for attempt in range(2):
            try:
                response = requests.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": topic},
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                    timeout=REQUEST_TIMEOUT_S,
                )
                response.raise_for_status()
                break
            except Exception as exc:
                if attempt == 1:
                    logger.warning("[research] DuckDuckGo HTML fallback failed: %s", exc)
                    return []
                time.sleep(1.5)

        if BeautifulSoup is None:
            logger.warning("[research] beautifulsoup4 not installed — DDG HTML fallback disabled")
            return []

        try:
            soup = BeautifulSoup(response.text, "lxml")
        except Exception:
            soup = BeautifulSoup(response.text, "html.parser")
        results: list[ResearchSource] = []

        for node in soup.select("div.result, div.web-result, div.results_links_deep"):
            title_node = node.select_one("a.result__a")
            snippet_node = node.select_one("a.result__snippet, span.result__snippet")
            if not title_node:
                continue
            title = title_node.get_text(" ", strip=True)
            href = self._unwrap_ddg_href(title_node.get("href", ""))
            if not href or not title:
                continue
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
            results.append(ResearchSource(
                title=title, url=href, snippet=snippet, origin="duckduckgo",
            ))
            if len(results) >= limit:
                break

        if not results:
            for link in soup.select("a.result__a, a[href*='duckduckgo.com/l/?']")[:limit]:
                title = link.get_text(" ", strip=True)
                href = self._unwrap_ddg_href(link.get("href", ""))
                if href and title and not href.startswith("https://duckduckgo.com"):
                    results.append(ResearchSource(
                        title=title, url=href, snippet="", origin="duckduckgo",
                    ))

        return results

    def _search_arxiv_fallback(self, topic: str, limit: int) -> list[ResearchSource]:
        """Direct arXiv Atom feed — parsed without feedparser to avoid an
        optional dep. Used when SearxNG science pool fails."""
        url = (
            "http://export.arxiv.org/api/query?"
            f"search_query=all:{quote_plus(topic)}&start=0&max_results={int(limit)}"
            "&sortBy=relevance&sortOrder=descending"
        )
        try:
            response = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("[research] arXiv fallback failed: %s", exc)
            return []

        # Parse the Atom feed with stdlib ElementTree. arXiv's namespace is
        # the standard Atom one; we strip it for simpler XPath.
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            logger.warning("[research] arXiv XML parse failed: %s", exc)
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        results: list[ResearchSource] = []
        for entry in root.findall("atom:entry", ns)[:limit]:
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            # arXiv puts the abstract page URL in <id>; the alternate <link>
            # rel="alternate" also points to the same thing.
            id_el = entry.find("atom:id", ns)
            link = (id_el.text or "").strip() if id_el is not None else ""
            title = (title_el.text or "").strip() if title_el is not None else ""
            # Collapse whitespace inside the title (arXiv wraps long titles)
            title = re.sub(r"\s+", " ", title)
            summary = (summary_el.text or "").strip() if summary_el is not None else ""
            summary = re.sub(r"\s+", " ", summary)
            if not link or not title:
                continue
            results.append(ResearchSource(
                title=title,
                url=link,
                snippet=summary[:400],
                origin="arxiv",
            ))
        return results

    def _search_reddit_fallback(self, topic: str, limit: int) -> list[ResearchSource]:
        """Reddit's public JSON search — no auth required, very stable.

        Used when SearxNG social pool fails. More relevant than scraping
        DuckDuckGo with site:reddit.com because we get post bodies and
        comment counts directly.
        """
        try:
            response = requests.get(
                "https://www.reddit.com/search.json",
                params={"q": topic, "limit": str(int(limit)), "sort": "relevance"},
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
                timeout=REQUEST_TIMEOUT_S,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("[research] Reddit fallback failed: %s", exc)
            return []

        try:
            data = response.json()
        except ValueError:
            return []

        results: list[ResearchSource] = []
        for child in (data.get("data", {}) or {}).get("children", [])[:limit]:
            d = child.get("data") or {}
            permalink = d.get("permalink") or ""
            title = (d.get("title") or "").strip()
            if not permalink or not title:
                continue
            url = "https://www.reddit.com" + permalink
            selftext = (d.get("selftext") or "").strip()
            subreddit = d.get("subreddit") or ""
            score = d.get("score") or 0
            num_comments = d.get("num_comments") or 0
            snippet = selftext[:400] if selftext else f"r/{subreddit} · {score} pts · {num_comments} comments"
            results.append(ResearchSource(
                title=title,
                url=url,
                snippet=snippet,
                origin="reddit",
            ))
        return results

    def _unwrap_ddg_href(self, href: str) -> str:
        if not href:
            return ""
        if href.startswith("//duckduckgo.com/l/?"):
            href = "https:" + href
        if "duckduckgo.com/l/?" in href:
            from urllib.parse import parse_qs, urlsplit
            query = parse_qs(urlsplit(href).query)
            target = query.get("uddg", [""])[0]
            if target:
                return target
        return href

    # ------------------------------------------------------------------
    # Content fetching — trafilatura (Readability-style) with html2text fallback
    # (Vane uses Playwright + @mozilla/readability; trafilatura is the Python equivalent)
    # ------------------------------------------------------------------

    def _fetch_main_text(self, url: str) -> str:
        if not url:
            return ""
        if url.lower().endswith(".pdf"):
            return ""
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_S,
                allow_redirects=True,
                stream=True,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.info("[research] Skipping %s — fetch failed: %s", url, exc)
            return ""

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
            return ""

        try:
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(8192):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_BYTES_PER_PAGE:
                    break
            raw = b"".join(chunks).decode(response.encoding or "utf-8", errors="ignore")
        except Exception as exc:
            logger.info("[research] Skipping %s — read failed: %s", url, exc)
            return ""

        return self._extract_main_text(raw)

    def _extract_main_text(self, html: str) -> str:
        if not html:
            return ""
        if _HAS_TRAFILATURA:
            try:
                text = trafilatura.extract(
                    html, include_links=False, include_images=False,
                    no_fallback=False, favor_recall=True,
                )
                if text:
                    return re.sub(r"\n{3,}", "\n\n", text).strip()
            except Exception:
                pass

        # BeautifulSoup + html2text path. Both are optional — degrade to a
        # crude tag-strip if either is missing.
        text = ""
        if BeautifulSoup is not None and _HAS_HTML2TEXT:
            try:
                h2t = _html2text_lib.HTML2Text()
                h2t.ignore_links = False
                h2t.ignore_images = True
                h2t.body_width = 0
                # Try lxml first (faster) then html.parser as fallback
                try:
                    soup = BeautifulSoup(html, "lxml")
                except Exception:
                    soup = BeautifulSoup(html, "html.parser")
                for tag in ("script", "style", "noscript", "svg", "form", "footer", "header", "nav", "aside"):
                    for node in soup.select(tag):
                        node.decompose()
                article = soup.select_one("article") or soup.select_one("main") or soup.body or soup
                text = h2t.handle(str(article)).strip()
            except Exception:
                text = ""

        if not text:
            # Last-ditch: strip tags with a regex. Ugly but never crashes.
            text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
            text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&nbsp;", " ", text)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    # ------------------------------------------------------------------
    # Output writing (same structure as before)
    # ------------------------------------------------------------------

    def _write_outputs(
        self,
        folder: str,
        topic: str,
        synthesis: str,
        sources: list[ResearchSource],
        when: datetime,
    ) -> str:
        summary_path = os.path.join(folder, "00-summary.md")
        successful = [s for s in sources if s.summary and not s.error]
        with open(summary_path, "w", encoding="utf-8") as fh:
            fh.write(f"# {topic}\n\n")
            fh.write(
                f"_Generated {when.strftime('%Y-%m-%d %H:%M')} "
                f"· {len(successful)}/{len(sources)} sources usable_\n\n"
            )
            fh.write("---\n\n")
            fh.write(synthesis.strip() + "\n\n")
            fh.write("---\n\n")
            fh.write("## References\n\n")
            for i, s in enumerate(sources, 1):
                marker = "" if s.summary else " _(no usable text)_"
                fh.write(f"[{i}] [{s.title}]({s.url}) — _{s.origin}_{marker}\n")

        for i, s in enumerate(sources, 1):
            slug = self._slugify(s.title)[:60] or "source"
            note_path = os.path.join(folder, f"{i:02d}-{slug}.md")
            with open(note_path, "w", encoding="utf-8") as fh:
                fh.write(f"# {s.title}\n\n")
                fh.write(f"- URL: {s.url}\n")
                fh.write(f"- Source: {s.origin}\n")
                if s.error:
                    fh.write(f"- Status: {s.error}\n\n")
                else:
                    fh.write("\n## Summary\n\n")
                    fh.write((s.summary or s.snippet or "").strip() + "\n\n")
                    excerpt = (s.body or "").strip()[:2000]
                    if excerpt:
                        fh.write("## Excerpt\n\n")
                        fh.write(excerpt + ("\n\n…" if len(s.body) > 2000 else "\n"))

        with open(os.path.join(folder, "sources.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# Sources for {topic}\n\n")
            for i, s in enumerate(sources, 1):
                fh.write(f"{i}. {s.title} — {s.url}\n")

        return summary_path

    def _write_failure_summary(self, folder: str, report: ResearchReport) -> None:
        path = os.path.join(folder, "00-summary.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# Research briefing — {report.topic}\n\n")
            fh.write(report.error or "No content produced.\n")
        report.summary_path = path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_json(self, text: str) -> dict | None:
        """Extract first JSON object from LLM output."""
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return None

    def _slugify(self, text: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").lower()).strip("-")
        return slug or "topic"

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                return ""
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            return url

    def _is_skippable_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(skip in host for skip in (
            "duckduckgo.com", "google.com/search", "bing.com/search",
            "youtube.com", "twitter.com", "x.com",
            "facebook.com", "instagram.com", "tiktok.com",
        ))

    def _get_llm(self):
        router = getattr(self.app, "router", None)
        if router is None:
            return None, ""
        try:
            llm = router.get_tool_llm()
            if llm is not None:
                return llm, "tool"
        except Exception:
            pass
        try:
            llm = router.get_llm()
            if llm is not None:
                return llm, "chat"
        except Exception:
            pass
        return None, ""

    def _run_inference(self, role: str, fn, fallback=""):
        lock = self._inference_lock(role)
        acquired = lock.acquire(timeout=RESEARCH_INFERENCE_TIMEOUT_S)
        if not acquired:
            logger.info("[research] %s inference lock busy — using fallback", role or "model")
            return fallback
        try:
            return fn()
        finally:
            lock.release()

    def _inference_lock(self, role: str):
        manager = getattr(self.app, "model_manager", None)
        if manager is None:
            router = getattr(self.app, "router", None)
            if router is not None:
                attr = "tool_inference_lock" if role == "tool" else "chat_inference_lock"
                lock = getattr(router, attr, None)
                if lock is not None:
                    return lock
            return _NullLock()
        try:
            return manager.inference_lock(role or "tool")
        except KeyError:
            return _NullLock()


class _NullLock:
    def acquire(self, timeout=None):
        return True

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
