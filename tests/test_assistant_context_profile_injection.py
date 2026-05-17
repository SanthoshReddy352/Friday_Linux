"""Regression guard: user_profile facts must surface in chat prompts.

The bug this prevents: even with profile facts persisted, the chat model
answered "what's my name?" generically because the prompt builder gated
the only user-facts injection path on Mem0 availability. This test exercises
the unconditional injection added to `AssistantContext.build_chat_messages`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext
from core.context_store import ContextStore


def _make_ctx(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "f.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    session_id = store.start_session({"source": "profile-injection-tests"})
    ctx = AssistantContext()
    ctx.bind_context_store(store, session_id)
    return ctx, store


def _join_prompt(messages):
    return "\n\n".join(m["content"] for m in messages)


def test_profile_block_present_when_facts_exist(tmp_path):
    ctx, store = _make_ctx(tmp_path)
    store.store_fact("name", "Tricky", namespace="user_profile")
    store.store_fact("role", "AI assistant builder", namespace="user_profile")
    store.store_fact("location", "Mumbai", namespace="user_profile")

    messages = ctx.build_chat_messages("what is my name?")
    prompt = _join_prompt(messages)

    assert "The user's profile" in prompt
    assert "Tricky" in prompt
    assert "AI assistant builder" in prompt
    assert "Mumbai" in prompt


def test_profile_block_present_on_short_referential_query(tmp_path):
    """Short queries with referential signals (pronouns) must still inject the
    profile block — otherwise 'who am I?' would skip it because it's ≤ 6 words."""
    ctx, store = _make_ctx(tmp_path)
    store.store_fact("name", "Cody", namespace="user_profile")

    messages = ctx.build_chat_messages("who am i?")
    prompt = _join_prompt(messages)

    assert "Cody" in prompt
    assert "The user's profile" in prompt


def test_profile_block_absent_when_no_facts(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    messages = ctx.build_chat_messages("hello")
    prompt = _join_prompt(messages)
    assert "The user's profile" not in prompt


def test_only_populated_fields_appear(tmp_path):
    ctx, store = _make_ctx(tmp_path)
    store.store_fact("name", "Tricky", namespace="user_profile")
    # Empty values from a skipped onboarding question are NOT surfaced.
    store.store_fact("role", "", namespace="user_profile")
    store.store_fact("location", "", namespace="user_profile")

    messages = ctx.build_chat_messages("what is my name?")
    prompt = _join_prompt(messages)

    assert "Tricky" in prompt
    assert "Role:" not in prompt
    assert "Location:" not in prompt


def test_profile_injection_works_when_mem0_disabled(tmp_path):
    """`memory_service` is not bound here, so the existing Mem0-based
    `user_facts` path is dead. The new user_profile block must still appear.
    """
    ctx, store = _make_ctx(tmp_path)
    assert ctx.memory_service is None
    store.store_fact("name", "Tricky", namespace="user_profile")

    # Long query so we hit the non-short branch as well.
    messages = ctx.build_chat_messages(
        "Tell me a long story about my own work in software engineering today."
    )
    prompt = _join_prompt(messages)
    assert "Tricky" in prompt
    assert "The user's profile" in prompt
