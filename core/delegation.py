from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DelegationRequest:
    agent_type: str
    task: str
    context_bundle: dict = field(default_factory=dict)
    timeout_ms: int = 3000


@dataclass
class DelegationResult:
    summary: str
    structured_output: dict = field(default_factory=dict)
    memory_candidates: list[dict] = field(default_factory=list)
    confidence: float = 0.5


class PlannerAgent:
    def __init__(self, app):
        self.app = app

    def handle(self, request: DelegationRequest) -> DelegationResult:
        actions = self.app.router._plan_actions(request.task)
        if not actions:
            return DelegationResult(
                summary="I need a bit more detail before I can plan that.",
                confidence=0.2,
            )
        response = self.app.router._execute_plan(actions)
        return DelegationResult(
            summary=response,
            structured_output={"tool_calls": [
                {
                    "name": action["route"]["spec"]["name"],
                    "args": dict(action.get("args", {})),
                    "text": action.get("text", request.task),
                }
                for action in actions
            ]},
            confidence=0.8,
        )


class WorkflowAgent:
    def __init__(self, app):
        self.app = app

    def handle(self, request: DelegationRequest) -> DelegationResult:
        workflow_result = self.app.router._continue_active_workflow(request.task)
        if workflow_result is not None:
            return DelegationResult(
                summary=workflow_result,
                structured_output={"workflow": "active"},
                confidence=0.85,
            )
        response = self.app.router.process_text(request.task)
        return DelegationResult(
            summary=response,
            structured_output={"workflow": "fallback"},
            confidence=0.6,
        )


class ResearchAgent:
    def __init__(self, app):
        self.app = app

    def handle(self, request: DelegationRequest) -> DelegationResult:
        response = self.app.router.process_text(request.task)
        return DelegationResult(
            summary=response,
            structured_output={"mode": "online_research"},
            confidence=0.65,
        )


class PersonaStylistAgent:
    def handle(self, request: DelegationRequest) -> DelegationResult:
        persona = dict((request.context_bundle or {}).get("persona") or {})
        if not persona:
            return DelegationResult(summary="", confidence=0.0)
        style = (
            f"Identity: {persona.get('display_name', 'FRIDAY')}. "
            f"Tone: {persona.get('tone_traits', 'warm, calm, capable')}. "
            f"Conversation style: {persona.get('conversation_style', 'natural and concise')}. "
            f"Tool acknowledgements: {persona.get('tool_ack_style', 'brief and reassuring')}."
        )
        return DelegationResult(
            summary=style,
            structured_output={"style_hint": style},
            confidence=0.9,
        )


class MemoryCuratorAgent:
    SAFE_PATTERNS = (
        (re.compile(r"\bmy name is ([a-z][a-z0-9 _'-]{1,40})\b", re.IGNORECASE), "name"),
        (re.compile(r"\bcall me ([a-z][a-z0-9 _'-]{1,40})\b", re.IGNORECASE), "preferred_name"),
        (re.compile(r"\bi like ([a-z0-9 ,._'-]{2,80})\b", re.IGNORECASE), "likes"),
        (re.compile(r"\bi prefer ([a-z0-9 ,._'-]{2,80})\b", re.IGNORECASE), "preference"),
        (re.compile(r"\bmy favorite ([a-z0-9 _'-]{2,40}) is ([a-z0-9 ,._'-]{1,80})\b", re.IGNORECASE), "favorite"),
    )
    EXPLICIT_MEMORY_PATTERN = re.compile(
        r"\b(?:remember|keep in mind|note that|save this memory)\b[:\s]*(.+)",
        re.IGNORECASE,
    )

    def __init__(self, app):
        self.app = app

    def curate(self, session_id: str, user_text: str, assistant_text: str, persona_id: str = ""):
        text = str(user_text or "").strip()
        if not text:
            return []

        candidates = []
        lowered = text.lower()
        for pattern, key in self.SAFE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            if key == "favorite":
                item_key = f"favorite_{match.group(1).strip().lower().replace(' ', '_')}"
                item_value = match.group(2).strip()
            else:
                item_key = key
                item_value = match.group(1).strip()
            self.app.context_store.store_fact(item_key, item_value, session_id=session_id, namespace="profile")
            candidates.append({"key": item_key, "value": item_value, "memory_type": "profile"})

        explicit = self.EXPLICIT_MEMORY_PATTERN.search(text)
        if explicit and explicit.group(1).strip():
            self.app.context_store.store_memory_item(
                session_id=session_id,
                content=explicit.group(1).strip(),
                memory_type="episodic",
                persona_id=persona_id,
                sensitivity="explicit_user",
                metadata={"role": "user", "source": "explicit_memory"},
            )
            candidates.append({"memory_type": "episodic", "content": explicit.group(1).strip(), "confidence": 0.95})
        return candidates


class DelegationManager:
    def __init__(self, app):
        self.app = app
        self.planner_agent = PlannerAgent(app)
        self.workflow_agent = WorkflowAgent(app)
        self.research_agent = ResearchAgent(app)
        self.memory_curator = MemoryCuratorAgent(app)
        self.persona_stylist = PersonaStylistAgent()

    def delegate(self, request: DelegationRequest) -> DelegationResult:
        if request.agent_type == "planner":
            return self.planner_agent.handle(request)
        if request.agent_type == "workflow":
            return self.workflow_agent.handle(request)
        if request.agent_type == "research":
            return self.research_agent.handle(request)
        if request.agent_type == "persona_stylist":
            return self.persona_stylist.handle(request)
        return DelegationResult(
            summary="I couldn't hand that task to a specialist.",
            confidence=0.0,
        )
