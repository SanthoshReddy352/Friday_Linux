"""PlannerEngine — turn user text + intent into an executable ToolPlan.

Phase 3 of the v2 architecture (docs/friday_architecture.md §9).

This is a thin adapter over the existing `CapabilityBroker`. The broker
already implements the full pipeline that the v2 doc splits into
PlannerEngine + ConsentGate + WorkflowCoordinator (consent check,
workflow check, online proposal, route scoring, LLM tool selection,
chat fallback). Re-implementing it would duplicate well-tested logic
with no behavior change, so the adapter delegates and lets the
structural separation come from `TurnOrchestrator` calling
`WorkflowCoordinator` first and `IntentEngine` second — not from
breaking the broker apart prematurely.

When IntentEngine returned a high-confidence multi-action result, the
adapter builds the ToolPlan directly from those actions and skips the
broker's redundant re-classification, matching the doc's "bypass the
LLM-based planner" fast path.
"""
from __future__ import annotations

from core.capability_broker import ToolPlan, ToolStep
from core.planning.intent_engine import HIGH_THRESHOLD, IntentResult


class PlannerEngine:
    """Adapter that produces a `ToolPlan` for a turn."""

    def __init__(self, capability_broker):
        self._broker = capability_broker

    def plan(self, text: str, ctx=None, intent: IntentResult | None = None) -> ToolPlan:
        """Build the plan for a turn.

        If *intent* has high confidence we synthesise the ToolPlan from its
        actions directly — the broker's intent_recognizer call would
        produce the same actions, so skipping it is a measurable
        fast-path win without changing the user-visible result.

        Otherwise we hand off to CapabilityBroker, which today still owns
        consent / online-pending / LLM tool selection / chat fallback.
        """
        if intent is not None and intent.confidence >= HIGH_THRESHOLD and intent.actions:
            fast_plan = self._plan_from_intent(intent, text, ctx)
            if fast_plan is not None:
                return fast_plan

        context_bundle = self._context_bundle(ctx)
        return self._broker.build_plan(
            text,
            turn_id=self._attr(ctx, "turn_id", ""),
            source=self._attr(ctx, "source", "user"),
            context_bundle=context_bundle,
            style_hint=self._attr(ctx, "style_hint", ""),
        )

    # ------------------------------------------------------------------
    # Fast-path: build a ToolPlan from a high-confidence IntentResult
    # ------------------------------------------------------------------

    def _plan_from_intent(
        self, intent: IntentResult, text: str, ctx
    ) -> ToolPlan | None:
        """Convert IntentResult.actions → ToolPlan, skipping the broker.

        Returns None if any action references a capability that needs
        consent or is otherwise sensitive — those still flow through the
        broker so the existing safety logic owns them.
        """
        steps: list[ToolStep] = []
        registry = self._capability_registry()
        consent = self._consent_service()

        for idx, action in enumerate(intent.actions):
            tool_name = action.get("tool") or ""
            if not tool_name:
                return None
            descriptor = (
                registry.get_descriptor(tool_name) if registry is not None else None
            )
            # Defer to the broker for anything that needs a confirmation
            # gesture or online consent. Only deterministic, locally-safe
            # paths are eligible for the fast path.
            if descriptor is not None and consent is not None:
                try:
                    decision = consent.evaluate(tool_name, descriptor, text)
                    if getattr(decision, "needs_confirmation", False):
                        return None
                except Exception:
                    return None
            steps.append(
                ToolStep(
                    capability_name=tool_name,
                    args=dict(action.get("args") or {}),
                    raw_text=text,
                    node_id=f"intent{idx}",
                    timeout_ms=self._tool_timeout_ms(),
                )
            )

        if not steps:
            return None

        return ToolPlan(
            turn_id=self._attr(ctx, "turn_id", ""),
            mode="tool",
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _attr(self, ctx, name, default):
        if ctx is None:
            return default
        return getattr(ctx, name, default) if not isinstance(ctx, dict) else ctx.get(name, default)

    def _context_bundle(self, ctx) -> dict:
        if ctx is None:
            return {}
        bundle = getattr(ctx, "context_bundle", None) if not isinstance(ctx, dict) else ctx.get("context_bundle")
        return dict(bundle or {})

    def _capability_registry(self):
        return getattr(self._broker, "app", None) and getattr(self._broker.app, "capability_registry", None)

    def _consent_service(self):
        app = getattr(self._broker, "app", None)
        return getattr(app, "consent_service", None) if app is not None else None

    def _tool_timeout_ms(self) -> int:
        app = getattr(self._broker, "app", None)
        config = getattr(app, "config", None) if app is not None else None
        if config is not None and hasattr(config, "get"):
            try:
                return int(config.get("routing.tool_timeout_ms", 8000) or 8000)
            except (TypeError, ValueError):
                pass
        return 8000
