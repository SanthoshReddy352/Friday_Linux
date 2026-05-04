"""Tests for the research_agent plugin: intent routing + plugin behaviour.

Network and LLM access are stubbed — the goal is to verify that:

* IntentRecognizer routes natural-language research phrasings to
  ``research_topic`` with a clean topic argument.
* The plugin returns the immediate "I'll work on this" ack and spawns a
  background thread.
* The completion callback summarizes the report through the event bus.
"""
from __future__ import annotations

import os
import sys
import threading
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.intent_recognizer import IntentRecognizer  # noqa: E402
from core.router import CommandRouter  # noqa: E402
from modules.research_agent.plugin import ResearchAgentPlugin  # noqa: E402
from modules.research_agent.service import (  # noqa: E402
    ResearchAgentService,
    ResearchReport,
    ResearchSource,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_router():
    bus = MagicMock()
    router = CommandRouter(bus)
    router.llm = None
    app = MagicMock()
    app.router = router
    app.event_bus = bus
    app.capability_registry = router.capability_registry
    # Give the app a real ``emit_assistant_message`` collector so tests
    # can inspect what the research agent says on completion. The plugin
    # prefers this over publishing voice_response directly.
    app.assistant_messages = []

    def _collect(text, source="friday", speak=True, spoken_text=None):
        app.assistant_messages.append({"text": text, "source": source})

    app.emit_assistant_message = _collect
    return app


@pytest.fixture
def plugin(app_with_router, monkeypatch):
    # Replace the heavy network pipeline with a stub that returns a known
    # report immediately on the same thread.
    plugin = ResearchAgentPlugin(app_with_router)

    def fake_start_research(topic, max_sources=5, on_complete=None, mode="balanced"):
        report = ResearchReport(
            topic=topic,
            folder=f"/tmp/friday-research/{topic.replace(' ', '-')}",
            summary_path=f"/tmp/friday-research/{topic.replace(' ', '-')}/00-summary.md",
            sources=[ResearchSource(title="t1", url="https://x", origin="duckduckgo", summary="ok")],
            duration_s=0.01,
        )
        thread = threading.Thread(target=lambda: None, daemon=True)
        thread.start()
        if on_complete is not None:
            on_complete(report)
        return thread

    monkeypatch.setattr(plugin.service, "start_research", fake_start_research)
    return plugin


# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "utterance, expected_topic",
    [
        ("research the latest on quantum dot displays",
         "quantum dot displays"),
        ("research quantum dot displays", "quantum dot displays"),
        ("do a deep dive on rust async runtimes", "rust async runtimes"),
        ("do a literature review on protein folding", "protein folding"),
        ("brief me on the indian general election", "the indian general election"),
        ("put together a briefing on edge ai chips", "edge ai chips"),
        ("find research papers about transformer scaling laws",
         "transformer scaling laws"),
        ("find me articles on small modular reactors", "small modular reactors"),
        ("investigate the rise of synthetic biology",
         "the rise of synthetic biology"),
        ("study the history of cryptography", "the history of cryptography"),
        ("give me a literature review of mrna vaccines", "mrna vaccines"),
    ],
)
def test_research_intent_routing(plugin, utterance, expected_topic):
    recognizer = IntentRecognizer(plugin.app.router)
    actions = recognizer.plan(utterance)
    assert len(actions) == 1, f"expected single action for {utterance!r}, got {actions}"
    action = actions[0]
    assert action["tool"] == "research_topic", f"got tool={action['tool']}"
    assert action["args"].get("topic") == expected_topic


def test_research_intent_skips_when_tool_missing():
    bus = MagicMock()
    router = CommandRouter(bus)
    router.llm = None
    recognizer = IntentRecognizer(router)
    # No research_topic registered — recognizer should not synthesize the
    # action and the (no other parser will match) plan should fall through
    # to []; it must not crash.
    assert recognizer.plan("research quantum dot displays") == []


def test_research_intent_does_not_swallow_lookup_phrases(plugin):
    recognizer = IntentRecognizer(plugin.app.router)
    # "look up the time" is a get_time intent — research_topic must not
    # outrun it via the more-specific look-up phrasings used by the
    # research parser.
    actions = recognizer.plan("look up the time")
    if actions:
        assert actions[0]["tool"] != "research_topic"


# ---------------------------------------------------------------------------
# Plugin handler
# ---------------------------------------------------------------------------


def test_handle_research_returns_immediate_ack(plugin):
    response = plugin.handle_research("research mrna vaccines", {"topic": "mrna vaccines"})
    assert "researching 'mrna vaccines'" in response.lower()


def test_handle_research_extracts_topic_from_text(plugin):
    response = plugin.handle_research("do a deep dive on rust async runtimes", {})
    assert "rust async runtimes" in response.lower()


def test_handle_research_clamps_max_sources(plugin):
    captured = {}

    def fake_start_research(topic, max_sources=5, on_complete=None, mode="balanced"):
        captured["max_sources"] = max_sources
        return threading.Thread(target=lambda: None, daemon=True)

    plugin.service.start_research = fake_start_research
    plugin.handle_research("research X", {"topic": "X", "max_sources": 99})
    assert captured["max_sources"] == 8  # balanced mode caps at 8
    plugin.handle_research("research X", {"topic": "X", "max_sources": -3})
    assert captured["max_sources"] == 1
    plugin.handle_research("research X", {"topic": "X", "max_sources": "not a number"})
    assert captured["max_sources"] == 5


def test_handle_research_prompts_when_topic_missing(plugin):
    response = plugin.handle_research("", {})
    assert "what should i research" in response.lower()


def test_announce_completion_emits_assistant_message(plugin):
    plugin.handle_research("research transformer scaling", {})
    messages = plugin.app.assistant_messages
    assert messages, "expected emit_assistant_message on completion"
    spoken = messages[-1]["text"].lower()
    assert "transformer scaling" in spoken
    assert "ready" in spoken or "briefing" in spoken
    assert messages[-1]["source"] == "research"


def test_announce_completion_reports_error(app_with_router):
    plugin = ResearchAgentPlugin(app_with_router)
    plugin._announce_completion(ResearchReport(
        topic="x", folder="/tmp/x", summary_path="", error="DuckDuckGo offline",
    ))
    messages = app_with_router.assistant_messages
    assert messages, "expected emit_assistant_message on error"
    spoken = messages[-1]["text"].lower()
    assert "snag" in spoken
    assert "duckduckgo offline" in spoken


def test_announce_completion_falls_back_to_voice_response_when_emit_unavailable(app_with_router):
    """When the app exposes only event_bus (older entry points), the plugin
    should still announce results via the voice_response topic."""
    del app_with_router.emit_assistant_message
    plugin = ResearchAgentPlugin(app_with_router)
    plugin._announce_completion(ResearchReport(
        topic="rust", folder="/tmp/rust", summary_path="/tmp/rust/00.md",
    ))
    publish_calls = [
        call for call in app_with_router.event_bus.publish.call_args_list
        if call.args[0] == "voice_response"
    ]
    assert publish_calls
    assert "rust" in publish_calls[-1].args[1].lower()


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------


def test_service_skips_known_search_engine_urls():
    service = ResearchAgentService(MagicMock())
    assert service._is_skippable_url("https://duckduckgo.com/foo")
    assert service._is_skippable_url("https://www.youtube.com/watch?v=x")
    assert not service._is_skippable_url("https://example.com/article")


def test_service_normalizes_urls():
    service = ResearchAgentService(MagicMock())
    assert service._normalize_url("https://EXAMPLE.com/A?q=1") == "https://EXAMPLE.com/A"
    assert service._normalize_url("not-a-url") == ""


def test_service_slugifies_topic():
    service = ResearchAgentService(MagicMock())
    assert service._slugify("Quantum Dot Displays!") == "quantum-dot-displays"
    assert service._slugify("") == "topic"


def test_service_get_llm_prefers_tool_llm(app_with_router):
    """_get_llm() should return the tool LLM and the matching role when available."""
    from unittest.mock import MagicMock
    mock_tool_llm = MagicMock()
    app_with_router.router.get_tool_llm = MagicMock(return_value=mock_tool_llm)
    service = ResearchAgentService(app_with_router)
    llm, role = service._get_llm()
    assert llm is mock_tool_llm
    assert role == "tool"
    # The model_manager owns the inference lock and it must be acquire/release-able.
    lock = service._inference_lock(role)
    acquired = lock.acquire(timeout=0.1)
    assert acquired
    lock.release()


def test_service_get_llm_falls_back_to_empty_role():
    """When the app has no router the service returns (None, "") and the
    inference-lock helper degrades to a no-op _NullLock."""
    service = ResearchAgentService(MagicMock(spec=[]))
    llm, role = service._get_llm()
    assert llm is None
    assert role == ""
    lock = service._inference_lock(role)
    assert lock.acquire(timeout=0.1) is True
    lock.release()
