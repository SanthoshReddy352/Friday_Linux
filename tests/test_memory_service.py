"""Tests for MemoryService — Phase 2 (v2) unified memory facade.

The service is intentionally a thin delegator: each test verifies the
facade forwards the call to the right underlying surface (ContextStore
or MemoryBroker) with the right arguments. Behavior tests for the
underlying stores live in their own modules.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.memory_service import MemoryService  # noqa: E402


# ---------------------------------------------------------------------------
# Doc §12 — v2 contract
# ---------------------------------------------------------------------------

def test_build_context_bundle_delegates_to_broker():
    broker = MagicMock()
    broker.build_context_bundle.return_value = {"persona": {"persona_id": "p1"}}
    svc = MemoryService(MagicMock(), broker)

    bundle = svc.build_context_bundle("sess-1", "what's the weather")
    assert bundle == {"persona": {"persona_id": "p1"}}
    broker.build_context_bundle.assert_called_once_with("what's the weather", "sess-1")


def test_build_context_bundle_returns_empty_on_blank_session():
    broker = MagicMock()
    svc = MemoryService(MagicMock(), broker)
    assert svc.build_context_bundle("", "anything") == {}
    broker.build_context_bundle.assert_not_called()


def test_build_context_bundle_returns_empty_when_broker_absent():
    svc = MemoryService(MagicMock(), memory_broker=None)
    assert svc.build_context_bundle("sess", "anything") == {}


def test_record_turn_appends_user_and_assistant_when_store_turns():
    store = MagicMock()
    svc = MemoryService(store)
    # Default behaviour no longer double-writes turns (emit_message already
    # calls append_turn). Tests requesting explicit storage pass store_turns=True.
    svc.record_turn("sess", "hi", "hello back", trace_id="trace-9", store_turns=True)
    assert store.append_turn.call_count == 2
    store.append_turn.assert_any_call("sess", "user", "hi", source="trace-9")
    store.append_turn.assert_any_call("sess", "assistant", "hello back", source="trace-9")


def test_record_turn_default_does_not_double_write_turns():
    store = MagicMock()
    svc = MemoryService(store)
    svc.record_turn("sess", "hi", "hello back", trace_id="trace-9")
    # With the default store_turns=False, append_turn must not be invoked —
    # `app.emit_message` is the single writer for turn rows.
    store.append_turn.assert_not_called()


def test_record_turn_skips_when_session_blank():
    store = MagicMock()
    MemoryService(store).record_turn("", "x", "y", store_turns=True)
    store.append_turn.assert_not_called()


def test_record_turn_skips_blank_text_for_each_role():
    store = MagicMock()
    svc = MemoryService(store)
    svc.record_turn("sess", "", "only-assistant", store_turns=True)
    store.append_turn.assert_called_once_with("sess", "assistant", "only-assistant", source=None)


def test_record_turn_queues_extractor_even_when_store_turns_is_false():
    """The Mem0 queue must be fed on every turn even though ContextStore writes
    are skipped — that fix is the whole reason record_turn exists in v2."""
    store = MagicMock()
    extractor = MagicMock()
    svc = MemoryService(store, extractor=extractor)
    svc.record_turn("sess", "what's the weather", "sunny")
    extractor.queue_turn.assert_called_once_with("what's the weather", "sunny", user_id="default")


def test_learn_fact_writes_to_store_and_semantic():
    store = MagicMock()
    broker = MagicMock()
    svc = MemoryService(store, broker)
    svc.learn_fact("sess", "name", "Tricky", confidence=0.95)
    store.store_fact.assert_called_once_with("name", "Tricky", session_id="sess", namespace="general")
    broker.semantic.upsert.assert_called_once_with(
        session_id="sess", key="name", value="Tricky", confidence=0.95
    )


def test_learn_fact_swallows_broker_exception():
    store = MagicMock()
    broker = MagicMock()
    broker.semantic.upsert.side_effect = RuntimeError("vector store down")
    svc = MemoryService(store, broker)
    # Must not raise — the persistent store write is the source of truth.
    svc.learn_fact("sess", "k", "v")
    store.store_fact.assert_called_once()


def test_learn_fact_skips_when_key_blank():
    store = MagicMock()
    MemoryService(store).learn_fact("sess", "", "value")
    store.store_fact.assert_not_called()


def test_forget_fact_delegates_to_store():
    store = MagicMock()
    MemoryService(store).forget_fact("memory:abc")
    store.delete_memory_item.assert_called_once_with("memory:abc")


def test_forget_fact_noop_on_blank_id():
    store = MagicMock()
    MemoryService(store).forget_fact("")
    store.delete_memory_item.assert_not_called()


def test_record_outcome_routes_to_broker():
    broker = MagicMock()
    svc = MemoryService(MagicMock(), broker)
    svc.record_outcome("launch_app", {"k": "v"}, True)
    broker.record_capability_outcome.assert_called_once_with("launch_app", {"k": "v"}, True)


def test_top_capabilities_returns_empty_when_broker_absent():
    svc = MemoryService(MagicMock(), memory_broker=None)
    assert svc.top_capabilities(limit=5) == []


def test_top_capabilities_delegates_to_procedural():
    proc = MagicMock()
    proc.top_capabilities.return_value = ["a", "b"]
    broker = SimpleNamespace(procedural=proc)
    svc = MemoryService(MagicMock(), broker)
    assert svc.top_capabilities(limit=2) == ["a", "b"]
    proc.top_capabilities.assert_called_once_with(limit=2)


def test_recall_semantic_delegates_to_store():
    store = MagicMock()
    store.semantic_recall.return_value = [{"key": "favorite_color", "value": "blue"}]
    svc = MemoryService(store)
    out = svc.recall_semantic("color", session_id="sess", limit=2)
    assert out == [{"key": "favorite_color", "value": "blue"}]
    store.semantic_recall.assert_called_once_with("color", "sess", limit=2)


def test_workflow_state_methods_pass_through():
    store = MagicMock()
    store.get_active_workflow.return_value = {"workflow_name": "file_workflow"}
    svc = MemoryService(store)

    assert svc.get_active_workflow("sess", "file_workflow") == {"workflow_name": "file_workflow"}
    store.get_active_workflow.assert_called_once_with("sess", workflow_name="file_workflow")

    svc.save_workflow_state("sess", "file_workflow", {"status": "active"})
    store.save_workflow_state.assert_called_once_with("sess", "file_workflow", {"status": "active"})

    svc.clear_workflow_state("sess", "file_workflow")
    store.clear_workflow_state.assert_called_once_with("sess", "file_workflow")


# ---------------------------------------------------------------------------
# Legacy ops kept on the facade for migration
# ---------------------------------------------------------------------------

def test_session_state_methods_round_trip():
    store = MagicMock()
    store.get_session_state.return_value = {"last_source": "voice"}
    svc = MemoryService(store)

    assert svc.get_session_state("sess") == {"last_source": "voice"}
    svc.save_session_state("sess", {"last_source": "text"})
    store.save_session_state.assert_called_once_with("sess", {"last_source": "text"})


def test_pending_online_methods_pass_through():
    store = MagicMock()
    svc = MemoryService(store)
    svc.set_pending_online("sess", {"tool_name": "search_web"})
    store.set_pending_online.assert_called_once_with("sess", {"tool_name": "search_web"})
    svc.clear_pending_online("sess")
    store.clear_pending_online.assert_called_once_with("sess")


def test_log_online_permission_pass_through():
    store = MagicMock()
    MemoryService(store).log_online_permission("sess", "search_web", "approved", reason="user")
    store.log_online_permission.assert_called_once_with(
        "sess", "search_web", "approved", reason="user"
    )


def test_store_fact_pass_through():
    store = MagicMock()
    MemoryService(store).store_fact("favorite_color", "blue", session_id="sess", namespace="profile")
    store.store_fact.assert_called_once_with(
        "favorite_color", "blue", session_id="sess", namespace="profile"
    )


def test_store_memory_item_pass_through():
    store = MagicMock()
    MemoryService(store).store_memory_item(
        "sess",
        "remember to call mom",
        memory_type="episodic",
        persona_id="default",
        sensitivity="explicit_user",
        metadata={"role": "user"},
    )
    store.store_memory_item.assert_called_once_with(
        "sess",
        "remember to call mom",
        memory_type="episodic",
        persona_id="default",
        sensitivity="explicit_user",
        metadata={"role": "user"},
    )


# ---------------------------------------------------------------------------
# Backing-store accessors (used during migration)
# ---------------------------------------------------------------------------

def test_facade_exposes_underlying_objects():
    store = MagicMock()
    broker = MagicMock()
    svc = MemoryService(store, broker)
    assert svc.context_store is store
    assert svc.memory_broker is broker
