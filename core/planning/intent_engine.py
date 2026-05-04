"""IntentEngine — deterministic fast-path intent classification.

Phase 3 of the v2 architecture (docs/friday_architecture.md §9).

This is a thin adapter over the existing `IntentRecognizer` (20 regex
parsers) and `RouteScorer` (alias/pattern/context-term scorer). The
classify() entry point returns a single `IntentResult` so the
orchestrator can branch on confidence:

  confidence ≥ HIGH_THRESHOLD → bypass the LLM-based planner, build a
                                plan directly from the IntentResult.
  confidence < HIGH_THRESHOLD → fall through to PlannerEngine.

The full multi-action list returned by `IntentRecognizer.plan()` is
preserved in `IntentResult.actions` so a downstream planner can build a
multi-step ToolPlan without re-running the parsers.
"""
from __future__ import annotations

from dataclasses import dataclass, field


HIGH_THRESHOLD = 0.9
MEDIUM_THRESHOLD = 0.5


@dataclass
class IntentResult:
    """Outcome of `IntentEngine.classify()`.

    `tool` and `args` describe the *first* action when source == "regex".
    The complete action list lives in `actions` so multi-step intents are
    not lost. When source == "score" only `tool` is populated (the scorer
    matches a capability name but does not synthesise args). When
    source == "none" the engine has nothing to offer and the orchestrator
    must call PlannerEngine.
    """

    tool: str | None
    args: dict = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "none"        # "regex" | "score" | "none"
    actions: list[dict] = field(default_factory=list)


class IntentEngine:
    """Adapter around IntentRecognizer + RouteScorer."""

    HIGH_THRESHOLD = HIGH_THRESHOLD
    MEDIUM_THRESHOLD = MEDIUM_THRESHOLD

    def __init__(self, intent_recognizer, route_scorer):
        self._recognizer = intent_recognizer
        self._scorer = route_scorer

    def classify(self, text: str, ctx=None) -> IntentResult:
        if not text or not text.strip():
            return IntentResult(tool=None, source="none")

        # 1. Regex parsers — first match short-circuits the rest of the
        #    classify() call; further parsers in IntentRecognizer.plan()
        #    are evaluated only because the existing recognizer iterates
        #    them eagerly. Caching that behavior is tracked in the doc but
        #    out of scope for this adapter.
        try:
            actions = self._recognizer.plan(text, context=self._context_dict(ctx))
        except Exception:
            actions = []

        if actions:
            first = actions[0]
            return IntentResult(
                tool=first.get("tool"),
                args=dict(first.get("args") or {}),
                confidence=1.0,
                source="regex",
                actions=actions,
            )

        # 2. Scorer fallback — alias / pattern / context-term match against
        #    registered capability descriptors. Returns medium confidence
        #    so PlannerEngine can still choose to do its own LLM planning.
        if self._scorer is not None:
            try:
                route = self._scorer.find_best_route(text, min_score=20)
            except Exception:
                route = None
            if route and route.get("spec", {}).get("name"):
                spec = route["spec"]
                return IntentResult(
                    tool=spec["name"],
                    args={},
                    confidence=0.6,
                    source="score",
                    actions=[{"tool": spec["name"], "args": {}, "domain": spec["name"]}],
                )

        return IntentResult(tool=None, source="none")

    def _context_dict(self, ctx) -> dict:
        """Marshal a TurnContext (or None) into the dict shape the legacy
        IntentRecognizer expects."""
        if ctx is None:
            return {}
        if isinstance(ctx, dict):
            return ctx
        out = {}
        for attr in ("session_id", "source", "turn_id", "trace_id"):
            value = getattr(ctx, attr, None)
            if value is not None:
                out[attr] = value
        return out
