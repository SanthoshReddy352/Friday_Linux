"""Tests for Batch 6 — Web research, memory gating, and context window pruning.

Covers:
* ``core.context_window.fit_messages`` — keeps head + tail, drops middle
  until prompt fits, falls back to head+tail when even that's over budget,
  honors ``min_keep_tail``, returns input unchanged when already under.
* ``core.context_window.count_tokens`` — uses ``llm.tokenize`` when
  available, falls back to chars-per-token otherwise.
* ``core.assistant_context._needs_referential_recall`` — pronoun + proper
  noun + memory verb triggers; small-talk doesn't fire.
* Research agent priority order: ``_search_web`` calls the DDG fallback
  first now (Batch 6 / Issue 6a flip).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.assistant_context import (
    _has_proper_noun,
    _needs_referential_recall,
)
from core.context_window import count_tokens, fit_messages


# ---------------------------------------------------------------------------
# context_window — count_tokens
# ---------------------------------------------------------------------------


class _FakeTokenizerLLM:
    """llama-cpp-like stub: 1 token per word."""

    def tokenize(self, blob: bytes) -> list[int]:
        return [0] * len(blob.decode("utf-8", errors="replace").split())


class _NoTokenizerLLM:
    """Stand-in for a model without a tokenize() — count_tokens must fall back."""
    pass


class TestCountTokens:
    def test_uses_llm_tokenize_when_available(self):
        llm = _FakeTokenizerLLM()
        messages = [{"role": "user", "content": "hello world from friday"}]
        # The serialized blob is "user: hello world from friday" — five
        # whitespace-separated tokens under our stub's one-token-per-word
        # rule.
        assert count_tokens(llm, messages) == 5

    def test_fallback_chars_per_token_when_tokenize_missing(self):
        # 3.5 chars/token heuristic — exact value isn't critical, just
        # confirm it returns something > 0 and proportional to length.
        short_msgs = [{"role": "user", "content": "hi"}]
        long_msgs = [{"role": "user", "content": "hi " * 200}]
        small = count_tokens(_NoTokenizerLLM(), short_msgs)
        big = count_tokens(_NoTokenizerLLM(), long_msgs)
        assert small >= 1
        assert big > small * 10

    def test_fallback_on_tokenize_exception(self):
        class _Broken:
            def tokenize(self, blob):
                raise RuntimeError("tokenizer broken")

        result = count_tokens(_Broken(), [{"role": "user", "content": "x"}])
        assert result >= 1


# ---------------------------------------------------------------------------
# context_window — fit_messages
# ---------------------------------------------------------------------------


def _msg(role: str, words: int) -> dict:
    return {"role": role, "content": "lorem " * words}


class TestFitMessages:
    def test_under_budget_returns_input_unchanged(self):
        llm = _FakeTokenizerLLM()
        messages = [_msg("user", 10), _msg("assistant", 10), _msg("user", 5)]
        out = fit_messages(llm, messages, n_ctx=4096, response_budget=512)
        assert out == messages

    def test_drops_middle_until_fit(self):
        llm = _FakeTokenizerLLM()
        # Build a long history that will exceed budget. n_ctx=200,
        # response_budget=50 → budget=150 tokens.
        messages = (
            [_msg("user", 30)]      # head — kept
            + [_msg("assistant", 30) for _ in range(6)]  # middle — dropped
            + [_msg("user", 10), _msg("assistant", 10),
               _msg("user", 10), _msg("assistant", 10)]  # tail (min_keep=4) — kept
        )
        out = fit_messages(llm, messages, n_ctx=200, response_budget=50)
        assert out[0] == messages[0]              # head preserved
        assert out[-4:] == messages[-4:]          # tail preserved
        assert len(out) < len(messages)           # actually dropped something
        # And the result is now within the budget.
        assert count_tokens(llm, out) <= 200 - 50

    def test_falls_back_to_head_and_tail_when_still_over(self):
        llm = _FakeTokenizerLLM()
        # All messages are huge — even head+tail blows the budget. The
        # function must not loop forever; it should give up and return
        # head+tail.
        messages = [_msg("user", 500)] + [_msg("assistant", 500) for _ in range(5)]
        out = fit_messages(llm, messages, n_ctx=200, response_budget=50, min_keep_tail=2)
        assert len(out) == 3  # head (1) + tail (2)
        assert out[0] == messages[0]
        assert out[-2:] == messages[-2:]

    def test_short_history_left_alone(self):
        llm = _FakeTokenizerLLM()
        # min_keep_tail=4 means a 4-message history can't be trimmed.
        messages = [_msg("user", 9999) for _ in range(3)]
        out = fit_messages(llm, messages, n_ctx=100, response_budget=20, min_keep_tail=4)
        assert out == messages

    def test_does_not_mutate_input(self):
        llm = _FakeTokenizerLLM()
        messages = [_msg("user", 100) for _ in range(8)]
        original_ids = [id(m) for m in messages]
        fit_messages(llm, messages, n_ctx=200, response_budget=50)
        assert [id(m) for m in messages] == original_ids
        assert len(messages) == 8


# ---------------------------------------------------------------------------
# assistant_context — referential recall gate
# ---------------------------------------------------------------------------


class TestReferentialRecall:
    @pytest.mark.parametrize("query", [
        "what do you know about me",
        "remember when I told you",
        "remind me of that",
        "tell me about Mumbai",                 # proper noun
        "did we talk about Acme yesterday",     # proper noun + we
        "what did you say earlier",
    ])
    def test_referential_triggers_fire(self, query):
        assert _needs_referential_recall(query) is True

    @pytest.mark.parametrize("query", [
        "hi",
        "thanks",
        # "what time is it" contains "it" — a real pronoun — and we
        # intentionally accept the false positive: recall is cheap when
        # no semantic memories exist for the query, and the alternative
        # (carving "it" out for status-question phrases) is brittle.
        "open calculator",
        "play next song please",
        "search google",
    ])
    def test_small_talk_does_not_fire(self, query):
        assert _needs_referential_recall(query) is False

    def test_proper_noun_detection_ignores_sentence_start(self):
        # The first word is always uppercase — must not count as proper noun.
        assert _has_proper_noun("What are you doing today") is False
        # Mid-sentence capitalised → counted.
        assert _has_proper_noun("I work at Acme corp") is True

    def test_all_caps_initialism_not_treated_as_proper_noun(self):
        # USA, API etc. should not trigger — they're not capitalised+lower.
        assert _has_proper_noun("I love the USA fundamentals") is False

    def test_empty_input(self):
        assert _needs_referential_recall("") is False
        assert _needs_referential_recall(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Research agent — DDG-first priority (Issue 6a)
# ---------------------------------------------------------------------------


class TestResearchPriority:
    def test_search_web_consults_ddg_before_searxng(self, monkeypatch):
        from modules.research_agent.service import ResearchAgentService, ResearchSource

        # Build a minimal service instance without booting the app.
        svc = ResearchAgentService.__new__(ResearchAgentService)

        order: list[str] = []

        def _fake_ddg(self, topic, limit):
            order.append("ddg")
            return [ResearchSource(
                title="DDG result",
                url="https://example.com/x",
                snippet="ok",
                origin="duckduckgo",
            )]

        def _fake_searx(self, *args, **kwargs):
            order.append("searx")
            return []

        def _fake_wiki(self, *args, **kwargs):
            order.append("wiki")
            return []

        monkeypatch.setattr(ResearchAgentService, "_search_duckduckgo_fallback", _fake_ddg)
        monkeypatch.setattr(ResearchAgentService, "_try_searx", _fake_searx)
        monkeypatch.setattr(ResearchAgentService, "_search_wikipedia_fallback", _fake_wiki)

        results = svc._search_web("mars helicopter", 3)

        # DDG fires first; SearxNG is only consulted if DDG returns nothing.
        assert order[0] == "ddg"
        assert "searx" not in order
        assert results and results[0].origin == "duckduckgo"

    def test_search_web_falls_through_to_searxng_when_ddg_empty(self, monkeypatch):
        from modules.research_agent.service import ResearchAgentService, ResearchSource

        svc = ResearchAgentService.__new__(ResearchAgentService)
        order: list[str] = []

        def _fake_ddg(self, topic, limit):
            order.append("ddg")
            return []

        def _fake_searx(self, *args, **kwargs):
            order.append("searx")
            return [ResearchSource(
                title="Searx result",
                url="https://example.com/y",
                snippet="ok",
                origin="general",
            )]

        def _fake_wiki(self, *args, **kwargs):
            order.append("wiki")
            return []

        monkeypatch.setattr(ResearchAgentService, "_search_duckduckgo_fallback", _fake_ddg)
        monkeypatch.setattr(ResearchAgentService, "_try_searx", _fake_searx)
        monkeypatch.setattr(ResearchAgentService, "_search_wikipedia_fallback", _fake_wiki)

        results = svc._search_web("anything", 3)
        assert order == ["ddg", "searx"]
        assert results and results[0].title == "Searx result"
