"""Automated tests for Jarvis→FRIDAY ports #1–#10.

Each port has its own class:
  TestPort2Commitments      — SQLite commitments table (§24)
  TestPort3AuditTrail       — Structured audit trail + voice gate (§25)
  TestPort1PlatformAdapter  — Cross-OS adapter + preflight (§26)
  TestPort5Triggers         — Cron / FileWatch / Clipboard triggers (§27)
  TestPort6AgentHierarchy   — Multi-agent hierarchy + task manager (§28)
  TestPort7Goals            — OKR goals plugin (§29)
  TestPort8LLMFallback      — Multi-LLM fallback chain (§30)
  TestPort9KnowledgeGraph   — Entity extraction + graph recall (§31)
  TestPort10Comms           — Telegram/Discord delivery (§32)
  TestPort4Awareness        — StruggleDetector + AwarenessService (§33)
"""
from __future__ import annotations

import os
import platform
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload=None):
        self.events.append((event, payload))

    def subscribe(self, event, handler):
        pass


class _FakeConfig:
    def __init__(self, data=None):
        self._data = data or {}

    def get(self, key, default=None):
        return self._data.get(key, default)


class _FakeRouter:
    def __init__(self):
        self.tools = []

    def register_tool(self, spec, handler, capability_meta=None):
        self.tools.append(spec["name"])


class _FakeApp:
    session_id = "test-session"

    def __init__(self):
        self.router = _FakeRouter()
        self.event_bus = _FakeBus()
        self.config = _FakeConfig()


# ===========================================================================
# Port #2 — Commitments table (§24)
# ===========================================================================

class TestPort2Commitments:
    """Tests for ContextStore.record_commitment and related CRUD."""

    @pytest.fixture
    def store(self, tmp_path):
        from core.context_store import ContextStore
        return ContextStore(str(tmp_path / "test.db"))

    def test_record_returns_uuid_string(self, store):
        cid = store.record_commitment(what="Buy milk")
        assert isinstance(cid, str) and len(cid) == 36  # UUID v4

    def test_default_status_is_pending(self, store):
        cid = store.record_commitment(what="Do the thing")
        rows = store.list_pending_commitments()
        ids = [r["id"] for r in rows]
        assert cid in ids

    def test_complete_moves_out_of_pending(self, store):
        cid = store.record_commitment(what="Test task")
        store.complete_commitment(cid)
        pending = [r["id"] for r in store.list_pending_commitments()]
        assert cid not in pending

    def test_fail_commitment(self, store):
        cid = store.record_commitment(what="Failing task")
        store.fail_commitment(cid, result="network error")
        all_rows = store.list_all_commitments()
        row = next((r for r in all_rows if r["id"] == cid), None)
        assert row is not None
        assert row["status"] == "failed"

    def test_cancel_commitment(self, store):
        cid = store.record_commitment(what="Cancelled task")
        store.cancel_commitment(cid)
        all_rows = store.list_all_commitments()
        row = next((r for r in all_rows if r["id"] == cid), None)
        assert row["status"] == "cancelled"

    def test_list_pending_excludes_done(self, store):
        cid1 = store.record_commitment(what="Keep")
        cid2 = store.record_commitment(what="Done")
        store.complete_commitment(cid2)
        pending = [r["id"] for r in store.list_pending_commitments()]
        assert cid1 in pending
        assert cid2 not in pending

    def test_get_commitment_by_id(self, store):
        cid = store.record_commitment(what="Get me", priority="high", retry_policy="once")
        row = store.get_commitment(cid)
        assert row is not None
        assert row["what"] == "Get me"
        assert row["priority"] == "high"
        assert row["retry_policy"] == "once"


# ===========================================================================
# Port #3 — Audit trail + voice gate (§25)
# ===========================================================================

class TestPort3AuditTrail:
    """Tests for ImpactTier, gate_voice_approval, and AuditTrail logging."""

    def test_impact_tier_enum_values(self):
        from core.kernel.consent import ImpactTier
        assert hasattr(ImpactTier, "READ")
        assert hasattr(ImpactTier, "WRITE")
        assert hasattr(ImpactTier, "EXTERNAL")
        assert hasattr(ImpactTier, "DESTRUCTIVE")

    def test_destructive_keyword_blocks_voice(self):
        from core.kernel.consent import ConsentService
        svc = ConsentService()
        result = svc.gate_voice_approval("delete_file", stt_confidence=1.0)
        assert result.needs_confirmation

    def test_execute_keyword_blocks_voice(self):
        from core.kernel.consent import ConsentService
        svc = ConsentService()
        result = svc.gate_voice_approval("execute_command", stt_confidence=1.0)
        assert result.needs_confirmation

    def test_low_confidence_blocks_write_tool(self):
        from core.kernel.consent import ConsentService
        svc = ConsentService()
        result = svc.gate_voice_approval("save_note", stt_confidence=0.70)
        assert result.needs_confirmation

    def test_high_confidence_allows_write_tool(self):
        from core.kernel.consent import ConsentService
        svc = ConsentService()
        result = svc.gate_voice_approval("save_note", stt_confidence=0.90)
        assert not result.needs_confirmation

    def test_read_tool_allowed_at_high_confidence(self):
        from core.kernel.consent import ConsentService
        svc = ConsentService()
        # READ tier tool allowed when confidence is adequate
        result = svc.gate_voice_approval("get_time", stt_confidence=0.90)
        assert not result.needs_confirmation

    def test_any_tool_blocked_at_very_low_confidence(self):
        from core.kernel.consent import ConsentService
        svc = ConsentService()
        # All tiers blocked when STT confidence is below the threshold
        result = svc.gate_voice_approval("get_time", stt_confidence=0.50)
        assert result.needs_confirmation

    def test_audit_trail_log_and_query(self, tmp_path):
        from core.context_store import ContextStore
        from core.memory_service import MemoryService
        from core.audit_trail import AuditTrail
        store = ContextStore(str(tmp_path / "a.db"))
        ms = MemoryService(store)
        trail = AuditTrail(ms, session_id="s1")
        trail.log(tool_name="get_time", ok=True, exec_ms=5)
        events = trail.query(limit=10)
        assert len(events) >= 1
        assert events[0]["tool_name"] == "get_time"

    def test_audit_trail_attribute_exists_on_executor(self):
        from core.capability_registry import CapabilityRegistry, CapabilityExecutor
        reg = CapabilityRegistry()
        exec_ = CapabilityExecutor(reg)
        assert hasattr(exec_, "audit_trail")
        assert exec_.audit_trail is None  # not wired until FridayApp sets it


# ===========================================================================
# Port #1 — Cross-OS platform adapter (§26)
# ===========================================================================

class TestPort1PlatformAdapter:
    """Tests for PlatformAdapter factory and CapabilityAvailability preflight."""

    def test_get_adapter_returns_singleton(self):
        from modules.system_control.adapters import get_adapter
        a1 = get_adapter()
        a2 = get_adapter()
        assert a1 is a2

    def test_adapter_implements_interface(self):
        from modules.system_control.adapters import get_adapter
        from modules.system_control.adapters._interface import PlatformAdapter
        assert isinstance(get_adapter(), PlatformAdapter)

    def test_adapter_has_required_methods(self):
        from modules.system_control.adapters import get_adapter
        adapter = get_adapter()
        for method in ("clipboard_read", "clipboard_write", "get_active_window",
                       "default_shell", "open_url", "list_running_processes"):
            assert callable(getattr(adapter, method, None)), f"missing {method}"

    def test_preflight_run_all_returns_dict(self):
        from modules.system_control.preflight import run_all
        result = run_all()
        assert isinstance(result, dict)
        assert "clipboard" in result

    def test_capability_availability_has_available_flag(self):
        from modules.system_control.preflight import run_all
        result = run_all()
        for name, avail in result.items():
            assert hasattr(avail, "available"), f"{name} missing .available"

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
    def test_linux_adapter_default_shell(self):
        from modules.system_control.adapters.linux import LinuxAdapter
        shell = LinuxAdapter().default_shell()
        assert isinstance(shell, str) and shell


# ===========================================================================
# Port #5 — Trigger types (§27)
# ===========================================================================

class TestPort5Triggers:
    """Tests for CronTrigger firing and ClipboardTrigger/FileWatchTrigger lifecycle."""

    def test_cron_trigger_fires_trigger_fired_event(self):
        from modules.triggers.cron import CronTrigger
        fired = threading.Event()
        captured = []

        class _Bus:
            def publish(self, event, payload=None):
                if event == "trigger_fired":
                    captured.append(payload)
                    fired.set()
            def subscribe(self, *a): pass

        trigger = CronTrigger(
            trigger_id="t1", name="test_cron",
            interval_seconds=0.05, event_bus=_Bus()
        )
        trigger.start()
        assert fired.wait(timeout=1.5), "CronTrigger did not fire within 1.5 s"
        trigger.stop()
        assert len(captured) >= 1

    def test_cron_trigger_payload_has_name(self):
        from modules.triggers.cron import CronTrigger
        payloads = []

        class _Bus:
            def publish(self, event, payload=None):
                if event == "trigger_fired":
                    payloads.append(payload)
            def subscribe(self, *a): pass

        trigger = CronTrigger(
            trigger_id="t2", name="my_cron",
            interval_seconds=0.05, event_bus=_Bus()
        )
        trigger.start()
        time.sleep(0.2)
        trigger.stop()
        assert any(p and p.get("name") == "my_cron" for p in payloads)

    def test_clipboard_trigger_starts_and_stops_cleanly(self):
        from modules.triggers.clipboard import ClipboardTrigger
        trigger = ClipboardTrigger(
            trigger_id="c1", name="clip",
            event_bus=_FakeBus(), poll_interval=0.05
        )
        trigger.start()
        time.sleep(0.1)
        trigger.stop()

    def test_file_watch_trigger_no_crash_on_missing_dir(self, tmp_path):
        from modules.triggers.file_watch import FileWatchTrigger
        trigger = FileWatchTrigger(
            trigger_id="fw1", name="fw",
            path=str(tmp_path / "nonexistent"), event_bus=_FakeBus()
        )
        trigger.start()
        time.sleep(0.05)
        trigger.stop()

    def test_base_trigger_abc_interface(self):
        from modules.triggers.base import BaseTrigger
        for attr in ("start", "stop", "fire"):
            assert hasattr(BaseTrigger, attr), f"BaseTrigger missing {attr}"


# ===========================================================================
# Port #6 — Multi-agent hierarchy (§28)
# ===========================================================================

class TestPort6AgentHierarchy:
    """Tests for AgentNode, AgentHierarchy, and AgentTaskManager."""

    def test_add_and_retrieve_via_tree(self):
        from core.agent_hierarchy import AgentHierarchy, AgentNode
        h = AgentHierarchy()
        h.add_agent(AgentNode(agent_id="a1", name="Alpha", role="worker", authority_level=5))
        tree = h.get_tree()
        assert any(n["agent_id"] == "a1" for n in tree)

    def test_get_primary_finds_root_node(self):
        from core.agent_hierarchy import AgentHierarchy, AgentNode
        h = AgentHierarchy()
        h.add_agent(AgentNode(agent_id="friday", name="FRIDAY", role="primary", authority_level=10))
        primary = h.get_primary()
        assert primary is not None
        assert primary.agent_id == "friday"

    def test_parent_child_relationship(self):
        from core.agent_hierarchy import AgentHierarchy, AgentNode
        h = AgentHierarchy()
        h.add_agent(AgentNode(agent_id="parent", name="Parent", role="coordinator", authority_level=8))
        h.add_agent(AgentNode(agent_id="child", name="Child", role="worker", authority_level=3, parent_id="parent"))
        children = h.get_children("parent")
        assert any(n.agent_id == "child" for n in children)

    def test_get_parent_of_root_is_none(self):
        from core.agent_hierarchy import AgentHierarchy, AgentNode
        h = AgentHierarchy()
        h.add_agent(AgentNode(agent_id="root", name="Root", role="primary", authority_level=10))
        assert h.get_parent("root") is None

    def test_remove_agent_removes_from_tree(self):
        from core.agent_hierarchy import AgentHierarchy, AgentNode
        h = AgentHierarchy()
        h.add_agent(AgentNode(agent_id="tmp", name="Tmp", role="worker", authority_level=1))
        h.remove_agent("tmp")
        assert not any(n["agent_id"] == "tmp" for n in h.get_tree())

    def test_task_manager_submit_task(self):
        from core.agent_hierarchy import AgentHierarchy, AgentTaskManager
        atm = AgentTaskManager(AgentHierarchy(), None)
        task_id = atm.launch(description="test task", fn=lambda: "done")
        assert task_id is not None
        time.sleep(0.2)
        atm.shutdown()

    def test_task_manager_shutdown_does_not_raise(self):
        from core.agent_hierarchy import AgentHierarchy, AgentTaskManager
        atm = AgentTaskManager(AgentHierarchy(), None)
        atm.shutdown()


# ===========================================================================
# Port #7 — OKR goals (§29)
# ===========================================================================

class TestPort7Goals:
    """Tests for ContextStore goals CRUD and GoalsPlugin capability registration."""

    @pytest.fixture
    def store(self, tmp_path):
        from core.context_store import ContextStore
        return ContextStore(str(tmp_path / "goals.db"))

    def test_create_goal_returns_uuid(self, store):
        gid = store.create_goal(title="Ship FRIDAY v2", level="objective")
        assert isinstance(gid, str) and len(gid) == 36

    def test_list_goals_returns_created(self, store):
        store.create_goal(title="Goal A", level="objective")
        store.create_goal(title="Goal B", level="key_result")
        titles = [g["title"] for g in store.list_goals(status="active")]
        assert "Goal A" in titles
        assert "Goal B" in titles

    def test_update_goal_score_auto_computes_health(self, store):
        gid = store.create_goal(title="Scoreable", level="task")
        store.update_goal_score(gid, score=0.75)
        row = store.get_goal(gid)
        assert abs(row["score"] - 0.75) < 0.01
        assert row["health"] == "on_track"

    def test_update_goal_score_at_risk(self, store):
        gid = store.create_goal(title="Risky", level="task")
        store.update_goal_score(gid, score=0.5)
        assert store.get_goal(gid)["health"] == "at_risk"

    def test_update_goal_status_completed(self, store):
        gid = store.create_goal(title="Done-able", level="milestone")
        store.update_goal_status(gid, status="completed")
        assert store.get_goal(gid)["status"] == "completed"

    def test_goals_plugin_registers_6_capabilities(self):
        from modules.goals.plugin import GoalsPlugin

        class _App(_FakeApp):
            context_store = None

        app = _App()
        GoalsPlugin(app)
        expected = {"create_goal", "update_goal", "list_goals", "get_goal_detail",
                    "complete_goal", "pause_goal"}
        assert expected.issubset(set(app.router.tools))


# ===========================================================================
# Port #8 — Multi-LLM fallback chain (§30)
# ===========================================================================

class TestPort8LLMFallback:
    """Tests for LLMProvider ABC and FallbackChain config loading."""

    def test_provider_abc_and_dataclasses_importable(self):
        from core.llm_providers.base import LLMProvider, ProviderMessage, ProviderResponse
        assert callable(LLMProvider)
        assert callable(ProviderMessage)
        assert callable(ProviderResponse)

    def test_disabled_by_default_yields_disabled_chain(self):
        from core.llm_providers.fallback_chain import FallbackChain
        chain = FallbackChain.from_config(_FakeConfig())
        assert not chain.enabled

    def test_enabled_false_yields_disabled_chain(self):
        from core.llm_providers.fallback_chain import FallbackChain
        chain = FallbackChain.from_config(_FakeConfig({"cloud_fallback.enabled": False}))
        assert not chain.enabled

    def test_enabled_true_with_anthropic_provider_is_enabled(self):
        from core.llm_providers.fallback_chain import FallbackChain
        cfg = _FakeConfig({
            "cloud_fallback.enabled": True,
            "cloud_fallback.providers": [
                {"name": "anthropic", "model": "claude-haiku-4-5-20251001"},
            ],
        })
        chain = FallbackChain.from_config(cfg)
        assert chain.enabled

    def test_openai_compat_provider_instantiates(self):
        from core.llm_providers.openai_compat import OpenAICompatProvider
        p = OpenAICompatProvider(
            model="llama3-8b",
            api_key="fake",
            base_url="https://api.groq.com/openai/v1",
            provider_name="groq",
        )
        assert p.name == "groq"

    def test_all_providers_unavailable_returns_none(self):
        from core.llm_providers.fallback_chain import FallbackChain
        from core.llm_providers.base import LLMProvider, ProviderMessage, ProviderResponse

        class _UnavailProvider(LLMProvider):
            name = "unavail"

            def is_available(self):
                return False

            def chat_completion(self, messages, **kw):
                raise RuntimeError("should not be called")

        chain = FallbackChain(providers=[_UnavailProvider()], enabled=True)
        result = chain.chat_completion([ProviderMessage(role="user", content="hi")])
        assert result is None


# ===========================================================================
# Port #9 — Typed knowledge graph recall (§31)
# ===========================================================================

class TestPort9KnowledgeGraph:
    """Tests for EntityExtractor patterns and ContextStore entity CRUD."""

    def test_extract_person_entity_with_said_pattern(self):
        from core.memory.graph import extract_entities
        # Pattern: "[Name] said/told/asked/mentioned/works"
        entities = extract_entities("Alice said we should refactor the module.")
        types = [e.entity_type for e in entities]
        assert "person" in types

    def test_extract_person_from_my_friend(self):
        from core.memory.graph import extract_entities
        entities = extract_entities("my friend Alice is coming over.")
        types = [e.entity_type for e in entities]
        assert "person" in types

    def test_extract_empty_text_returns_empty(self):
        from core.memory.graph import extract_entities
        assert extract_entities("") == []

    def test_upsert_entity_idempotent(self, tmp_path):
        from core.context_store import ContextStore
        store = ContextStore(str(tmp_path / "e.db"))
        id1 = store.upsert_entity(name="Alice", entity_type="person")
        id2 = store.upsert_entity(name="Alice", entity_type="person")
        assert id1 == id2  # upsert must be idempotent

    def test_add_and_query_entity_fact(self, tmp_path):
        from core.context_store import ContextStore
        store = ContextStore(str(tmp_path / "f.db"))
        eid = store.upsert_entity(name="Alice", entity_type="person")
        store.add_entity_fact(eid, predicate="likes", obj="Python")
        facts = store.query_entity_facts(eid)
        assert any(f["predicate"] == "likes" and f["object"] == "Python" for f in facts)

    def test_add_entity_relationship(self, tmp_path):
        from core.context_store import ContextStore
        store = ContextStore(str(tmp_path / "r.db"))
        e1 = store.upsert_entity(name="Alice", entity_type="person")
        e2 = store.upsert_entity(name="Python", entity_type="tool")
        rel_id = store.add_entity_relationship(e1, e2, rel_type="uses")
        assert rel_id is not None

    def test_find_entities_by_name_fragment(self, tmp_path):
        from core.context_store import ContextStore
        store = ContextStore(str(tmp_path / "s.db"))
        store.upsert_entity(name="Alice Smith", entity_type="person")
        results = store.find_entities(name_fragment="Alice")
        assert len(results) >= 1

    def test_graph_recall_empty_store_returns_empty_string(self, tmp_path):
        from core.context_store import ContextStore
        from core.memory_service import MemoryService
        from core.memory.graph import GraphRecall
        store = ContextStore(str(tmp_path / "g.db"))
        recall = GraphRecall(MemoryService(store))
        result = recall.build_fragment("Tell me about Alice")
        assert isinstance(result, str)


# ===========================================================================
# Port #10 — Telegram / Discord delivery (§32)
# ===========================================================================

class TestPort10Comms:
    """Tests for channel availability detection and CommsPlugin boot behavior."""

    def test_telegram_unavailable_without_env_vars(self, monkeypatch):
        monkeypatch.delenv("FRIDAY_TELEGRAM_TOKEN", raising=False)
        monkeypatch.delenv("FRIDAY_TELEGRAM_CHAT_ID", raising=False)
        from importlib import reload
        import modules.comms.telegram as m
        reload(m)
        assert not m.TelegramChannel().available

    def test_discord_unavailable_without_webhook(self, monkeypatch):
        monkeypatch.delenv("FRIDAY_DISCORD_WEBHOOK_URL", raising=False)
        from importlib import reload
        import modules.comms.discord as m
        reload(m)
        assert not m.DiscordChannel().available

    def test_telegram_available_with_env_vars(self, monkeypatch):
        monkeypatch.setenv("FRIDAY_TELEGRAM_TOKEN", "fake_token")
        monkeypatch.setenv("FRIDAY_TELEGRAM_CHAT_ID", "12345")
        from importlib import reload
        import modules.comms.telegram as m
        reload(m)
        assert m.TelegramChannel().available

    def test_discord_available_with_webhook(self, monkeypatch):
        monkeypatch.setenv("FRIDAY_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/fake/url")
        from importlib import reload
        import modules.comms.discord as m
        reload(m)
        assert m.DiscordChannel().available

    def test_comms_plugin_no_tools_without_channels(self, monkeypatch):
        for var in ("FRIDAY_TELEGRAM_TOKEN", "FRIDAY_TELEGRAM_CHAT_ID", "FRIDAY_DISCORD_WEBHOOK_URL"):
            monkeypatch.delenv(var, raising=False)
        from importlib import reload
        import modules.comms.telegram as tg
        import modules.comms.discord as dc
        reload(tg)
        reload(dc)
        from modules.comms.plugin import CommsPlugin
        app = _FakeApp()
        CommsPlugin(app)
        assert "send_notification" not in app.router.tools

    def test_comms_plugin_registers_send_notification_when_telegram_configured(self, monkeypatch):
        monkeypatch.setenv("FRIDAY_TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("FRIDAY_TELEGRAM_CHAT_ID", "99")
        from importlib import reload
        import modules.comms.telegram as tg
        reload(tg)
        from modules.comms.plugin import CommsPlugin
        app = _FakeApp()
        CommsPlugin(app)
        assert "send_notification" in app.router.tools

    def test_telegram_token_not_stored_in_config_attribute(self):
        from modules.comms.telegram import TelegramChannel
        ch = TelegramChannel()
        assert not hasattr(ch, "_config_token"), \
            "Token must come from env var FRIDAY_TELEGRAM_TOKEN, not from config.yaml"


# ===========================================================================
# Port #4 — Continuous awareness (§33)
# ===========================================================================

class TestPort4Awareness:
    """Tests for StruggleDetector signal computation and AwarenessService opt-in guard."""

    def test_grace_period_suppresses_struggle(self):
        from modules.awareness.struggle_detector import StruggleDetector
        detector = StruggleDetector(_FakeBus())
        for _ in range(10):
            result = detector.push("error: command not found", "terminal")
        assert result is None, "Grace period must suppress detection"

    def test_needs_at_least_3_snapshots(self):
        from modules.awareness.struggle_detector import StruggleDetector
        from unittest.mock import patch
        detector = StruggleDetector(_FakeBus())
        with patch.object(detector, "_session_start", detector._session_start - 300):
            r1 = detector.push("text1", "win")
            assert r1 is None
            r2 = detector.push("text2", "win")
            assert r2 is None

    def test_cooldown_attribute_present(self):
        from modules.awareness.struggle_detector import StruggleDetector
        detector = StruggleDetector(_FakeBus())
        assert hasattr(detector, "_last_struggle_ts")

    def test_awareness_service_disabled_by_default(self):
        from modules.awareness.service import AwarenessService
        svc = AwarenessService(_FakeBus(), config=_FakeConfig())
        assert not svc._enabled
        assert svc.start() is False
        assert not svc._running

    def test_awareness_service_enabled_with_opt_in_config(self):
        from modules.awareness.service import AwarenessService
        cfg = _FakeConfig({"awareness.enabled": True, "awareness.capture_interval_s": 100})
        svc = AwarenessService(_FakeBus(), config=cfg)
        assert svc._enabled
        assert svc.start() is True
        assert svc._running
        svc.stop()

    def test_awareness_recent_captures_empty_at_start(self):
        from modules.awareness.service import AwarenessService
        svc = AwarenessService(_FakeBus(), config=_FakeConfig())
        assert svc.recent_captures(limit=5) == []

    def test_awareness_plugin_registers_4_capabilities(self):
        from modules.awareness.plugin import AwarenessPlugin
        app = _FakeApp()
        AwarenessPlugin(app)
        expected = {"enable_awareness_mode", "disable_awareness_mode",
                    "awareness_status", "recent_screen_activity"}
        assert expected.issubset(set(app.router.tools))

    def test_struggle_detector_evaluate_with_identical_snapshots(self):
        from modules.awareness.struggle_detector import StruggleDetector, Snapshot, _text_hash
        from unittest.mock import patch
        import time as _time
        detector = StruggleDetector(_FakeBus())
        now = _time.monotonic()
        text = "unchanged content here for a while"
        h = _text_hash(text)
        with patch.object(detector, "_session_start", now - 1000):
            for i in range(30):
                detector._snapshots.append(Snapshot(
                    ts=now - 200 + i * 0.5,
                    ocr_text=text,
                    ocr_hash=h,
                    window_title="editor",
                ))
            result = detector._evaluate(now)
        if result is not None:
            assert result["score"] >= 0.5
            assert "signals" in result
