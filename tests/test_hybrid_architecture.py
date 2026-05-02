import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext
from core.capability_registry import CapabilityRegistry
from core.context_store import ContextStore
from core.conversation_agent import ConversationAgent
from core.delegation import DelegationManager
from core.kernel.consent import ConsentService
from core.memory_broker import MemoryBroker
from core.persona_manager import PersonaManager
from core.router import CommandRouter
from core.workflow_orchestrator import WorkflowOrchestrator
from modules.browser_automation.plugin import BrowserAutomationPlugin


class DummyConfig:
    def get(self, key, default=None):
        values = {
            "browser_automation.enabled": True,
            "browser_automation.allow_online": True,
        }
        return values.get(key, default)


def build_conversation_app(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    session_id = store.start_session({"source": "tests"})
    persona_manager = PersonaManager(store)
    store.set_active_persona(session_id, persona_manager.DEFAULT_PERSONA_ID)
    registry = CapabilityRegistry()
    assistant_context = AssistantContext()
    assistant_context.bind_context_store(store, session_id)

    app = SimpleNamespace()
    app.config = DummyConfig()
    app.session_id = session_id
    app.context_store = store
    app.persona_manager = persona_manager
    app.memory_broker = MemoryBroker(store, persona_manager)
    app.capability_registry = registry
    app.consent_service = ConsentService(app.config)
    app.router = CommandRouter(MagicMock())
    app.router.capability_registry = registry
    app.router.assistant_context = assistant_context
    app.router.context_store = store
    app.router.session_id = session_id
    app.assistant_context = assistant_context
    app.workflow_orchestrator = WorkflowOrchestrator(app)
    app.router.workflow_orchestrator = app.workflow_orchestrator
    app.delegation_manager = DelegationManager(app)
    app.event_bus = MagicMock()
    app.capability_executor = MagicMock()
    return app


def test_router_registers_capability_metadata():
    registry = CapabilityRegistry()
    router = CommandRouter(MagicMock())
    router.capability_registry = registry

    router.register_tool(
        {"name": "open_browser_url", "description": "Open a website in the browser.", "parameters": {"url": "string"}},
        lambda t, a: "opened",
        capability_meta={
            "connectivity": "online",
            "permission_mode": "ask_first",
            "side_effect_level": "write",
        },
    )

    descriptor = registry.get_descriptor("open_browser_url")
    assert descriptor is not None
    assert descriptor.connectivity == "online"
    assert descriptor.permission_mode == "ask_first"
    assert descriptor.side_effect_level == "write"


def test_persona_manager_persists_and_activates_personas(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    manager = PersonaManager(store)
    session_id = store.start_session({"source": "tests"})

    manager.save_persona(
        {
            "persona_id": "ops_mode",
            "display_name": "Ops",
            "system_identity": "A terse technical operator.",
            "tone_traits": "direct, technical",
            "conversation_style": "brief",
            "speech_style": "plain",
        }
    )
    manager.set_active_persona(session_id, "ops_mode")

    active = manager.get_active_persona(session_id)
    assert active["persona_id"] == "ops_mode"
    assert active["display_name"] == "Ops"
    assert store.get_active_persona_id(session_id) == "ops_mode"


def test_conversation_agent_asks_before_online_current_info(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    session_id = store.start_session({"source": "tests"})
    persona_manager = PersonaManager(store)
    store.set_active_persona(session_id, persona_manager.DEFAULT_PERSONA_ID)
    registry = CapabilityRegistry()
    registry.register_tool(
        {"name": "get_weather", "description": "Get online weather.", "parameters": {"city": "string"}},
        lambda t, a: "sunny",
        metadata={"connectivity": "online", "permission_mode": "ask_first"},
    )

    app = SimpleNamespace()
    app.session_id = session_id
    app.context_store = store
    app.persona_manager = persona_manager
    app.memory_broker = MemoryBroker(store, persona_manager)
    app.capability_registry = registry
    app.consent_service = ConsentService()
    app.router = CommandRouter(MagicMock())
    app.router.capability_registry = registry
    app.assistant_context = None
    app.delegation_manager = DelegationManager(app)
    app.event_bus = MagicMock()
    app.capability_executor = MagicMock()

    agent = ConversationAgent(app)
    plan = agent.plan_turn("what's the latest weather in mumbai", context_bundle=app.memory_broker.build_context_bundle("weather", session_id))

    assert plan.mode == "clarify"
    assert plan.online_required is True
    pending = store.get_session_state(session_id).get("pending_online")
    assert pending is not None


def test_conversation_agent_skips_extra_prompt_for_direct_youtube_play(tmp_path):
    app = build_conversation_app(tmp_path)
    BrowserAutomationPlugin(app)
    agent = ConversationAgent(app)

    plan = agent.plan_turn(
        "play love selfie on youtube",
        context_bundle=app.memory_broker.build_context_bundle("play love selfie on youtube", app.session_id),
    )

    assert plan.mode == "local_tool"
    assert plan.tool_calls[0]["name"] == "play_youtube"
    assert plan.tool_calls[0]["args"] == {"query": "love selfie", "browser_name": "chrome"}


def test_conversation_agent_accepts_natural_yes_for_pending_online_request(tmp_path):
    app = build_conversation_app(tmp_path)
    BrowserAutomationPlugin(app)
    agent = ConversationAgent(app)
    app.context_store.set_pending_online(
        app.session_id,
        {
            "tool_name": "play_youtube",
            "args": {"query": "love selfie", "browser_name": "chrome"},
            "text": "play love selfie on youtube",
            "ack": "",
        },
    )

    plan = agent.plan_turn(
        "yeah you can go on and in for this request yes",
        context_bundle=app.memory_broker.build_context_bundle("yes", app.session_id),
    )

    assert plan.mode == "local_tool"
    assert plan.tool_calls[0]["name"] == "play_youtube"
    assert plan.tool_calls[0]["args"] == {"query": "love selfie", "browser_name": "chrome"}
