"""TaskGraphExecutor — DAG-based parallel tool execution.

Phase 4 of the v2 architecture (docs/friday_architecture.md §10).

Replaces the sequential semantics of `OrderedToolExecutor` for multi-step
plans with a wave-based parallel runner:

  * The plan's `ToolStep`s form a DAG via their `depends_on` lists. Steps
    with no declared dependency become wave 0 and run concurrently.
  * Each subsequent wave waits for its predecessor wave to complete, then
    runs all newly-unblocked nodes in parallel.
  * Per-step `timeout_ms` is enforced via `Future.result(timeout=…)`. On
    timeout the step is recorded as failed (the underlying Python call
    cannot be forcibly cancelled — the worker thread is leaked back to the
    pool, matching the behavior described in the architecture doc).
  * Per-step `retries` reattempts a failed call before giving up.
  * A predecessor's output is injected into a dependent's args under the
    predecessor's `node_id`, so a planner can wire `summarize_text → write_file`
    by setting `write_file.depends_on = ["summarize_text"]`.

Side effects (cache writes, response_finalizer state, routing_state, memory
broker outcomes, turn-feedback events) match `OrderedToolExecutor` so the
two backends are interchangeable.

Selected via the `routing.execution_engine: "parallel"` config flag.
Default stays `"ordered"` and current behavior is preserved exactly.
"""
from __future__ import annotations

import time
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from dataclasses import dataclass

from core.logger import logger


@dataclass
class _Node:
    step: object  # ToolStep — kept untyped to avoid a hard import cycle.
    node_id: str
    depends_on: list[str]
    retries: int
    input_index: int


def topological_waves(nodes: list[_Node]) -> list[list[_Node]]:
    """Group *nodes* into execution waves where each wave depends only on
    earlier waves. Cycles raise ValueError. Unknown deps are treated as no
    dependency (the planner can hand us partial graphs)."""
    by_id = {n.node_id: n for n in nodes}
    remaining = {n.node_id: set(d for d in n.depends_on if d in by_id) for n in nodes}
    waves: list[list[_Node]] = []
    while remaining:
        ready_ids = sorted(nid for nid, deps in remaining.items() if not deps)
        if not ready_ids:
            raise ValueError(
                f"TaskGraphExecutor: dependency cycle in nodes {sorted(remaining)}"
            )
        wave = [by_id[nid] for nid in ready_ids]
        waves.append(wave)
        for nid in ready_ids:
            remaining.pop(nid)
        for deps in remaining.values():
            deps.difference_update(ready_ids)
    return waves


class TaskGraphExecutor:
    """Wave-based parallel executor. Compatible with `OrderedToolExecutor.execute()`."""

    def __init__(self, app, max_workers: int = 4):
        self.app = app
        self._max_workers = max(1, int(max_workers))

    # ------------------------------------------------------------------
    # Public dispatch — mirrors OrderedToolExecutor.execute()
    # ------------------------------------------------------------------

    def execute(self, plan, user_text: str, turn=None):
        if plan.mode in {"reply", "clarify"}:
            self.app.routing_state.set_decision("deterministic", tool_name="", args={})
            return plan.reply

        if plan.mode in {"delegate", "planner"}:
            # These modes have side effects that aren't graph-friendly
            # (delegation manager, router.process_text). Forward to the
            # ordered executor — same code, no behavior change.
            return self.app.ordered_tool_executor.execute(plan, user_text, turn=turn)

        if plan.mode in {"tool", "chat"}:
            steps = list(getattr(plan, "steps", []) or [])
            if len(steps) <= 1:
                # Single-step plans: nothing to parallelise. Forward.
                return self.app.ordered_tool_executor.execute(plan, user_text, turn=turn)
            return self._execute_graph(plan, user_text, turn=turn)

        return "I need a bit more detail before I can do that."

    # ------------------------------------------------------------------
    # Graph execution
    # ------------------------------------------------------------------

    def _execute_graph(self, plan, user_text: str, turn=None) -> str:
        nodes = self._normalize_nodes(plan.steps)
        try:
            waves = topological_waves(nodes)
        except ValueError as exc:
            logger.warning("[task_graph] %s — falling back to ordered execution", exc)
            return self.app.ordered_tool_executor.execute(plan, user_text, turn=turn)

        results_by_id: dict[str, str] = {}
        responses_by_index: list[str | None] = [None] * len(nodes)
        worker_count = min(self._max_workers, max(len(wave) for wave in waves))

        with ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="tool-graph"
        ) as pool:
            for wave in waves:
                future_to_node: dict[Future, _Node] = {}
                for node in wave:
                    fut = pool.submit(
                        self._run_node, node, user_text, dict(results_by_id), turn
                    )
                    future_to_node[fut] = node

                for fut, node in future_to_node.items():
                    timeout_s = self._timeout_seconds(node)
                    try:
                        response, output = fut.result(timeout=timeout_s)
                    except FutureTimeoutError:
                        # Best-effort: cancel pending futures; running ones
                        # cannot be killed in pure Python. Record as error.
                        fut.cancel()
                        timeout_ms = node.step.timeout_ms or 0
                        response = f"Error running command: timed out after {timeout_ms}ms"
                        output = ""
                        self._record_outcome(node, ok=False)
                    except Exception as exc:  # pragma: no cover — defensive
                        logger.exception(
                            "[task_graph] node %s raised: %s", node.node_id, exc
                        )
                        response = f"Error running command: {exc}"
                        output = ""
                        self._record_outcome(node, ok=False)
                    results_by_id[node.node_id] = output
                    responses_by_index[node.input_index] = response

        return "\n".join(r for r in responses_by_index if r)

    # ------------------------------------------------------------------
    # Per-node execution (cache, turn feedback, retries, side effects)
    # ------------------------------------------------------------------

    def _run_node(
        self,
        node: _Node,
        user_text: str,
        prior_results: dict[str, str],
        turn,
    ) -> tuple[str, str]:
        step = node.step
        cache = getattr(self.app, "result_cache", None)
        descriptor = self._descriptor_for(step.capability_name)

        # Inject upstream outputs into args under each dependency's node_id.
        args = dict(step.args or {})
        for dep_id in node.depends_on:
            if dep_id in prior_results:
                args[dep_id] = prior_results[dep_id]

        raw_text = step.raw_text or user_text

        # Cache check (read-side only; ResultCache enforces TTL=0 for writes).
        if cache is not None:
            cached_output = cache.get(step.capability_name, args, raw_text)
            if cached_output is not None:
                self._apply_success_side_effects(step, args, cached_output)
                return self.app.response_finalizer.finalize(cached_output), cached_output

        # Run with retries.
        last_error = ""
        for attempt in range(node.retries + 1):
            started = time.monotonic()
            self._emit_started(turn, step, args)
            try:
                result = self.app.capability_executor.execute(
                    step.capability_name, raw_text, args
                )
            except Exception as exc:  # pragma: no cover — capability_executor wraps errors
                last_error = str(exc)
                self._emit_finished(turn, step, ok=False, ms=(time.monotonic() - started) * 1000, error=last_error)
                continue

            duration_ms = (time.monotonic() - started) * 1000
            self._emit_finished(turn, step, ok=result.ok, ms=duration_ms, error=getattr(result, "error", ""))

            if result.ok:
                if cache is not None:
                    cache.set(
                        step.capability_name,
                        args,
                        result.output,
                        descriptor=descriptor,
                        raw_text=raw_text,
                    )
                self._apply_success_side_effects(step, args, result.output)
                self._record_outcome(node, ok=True)
                return self.app.response_finalizer.finalize(result.output), result.output

            last_error = result.error

        self._record_outcome(node, ok=False)
        return f"Error running command: {last_error}", ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_nodes(self, steps) -> list[_Node]:
        nodes: list[_Node] = []
        for idx, step in enumerate(steps):
            node_id = (getattr(step, "node_id", "") or f"step{idx}").strip()
            depends_on = [
                d for d in (getattr(step, "depends_on", []) or []) if d and d != node_id
            ]
            retries = max(0, int(getattr(step, "retries", 0) or 0))
            nodes.append(
                _Node(
                    step=step,
                    node_id=node_id,
                    depends_on=depends_on,
                    retries=retries,
                    input_index=idx,
                )
            )
        # Ensure node_ids are unique — duplicates make the graph ambiguous.
        seen: set[str] = set()
        for node in nodes:
            if node.node_id in seen:
                node.node_id = f"{node.node_id}__{node.input_index}"
            seen.add(node.node_id)
        return nodes

    def _timeout_seconds(self, node: _Node) -> float | None:
        ms = getattr(node.step, "timeout_ms", 0) or 0
        if ms <= 0:
            return None
        return ms / 1000.0

    def _descriptor_for(self, name: str):
        registry = getattr(self.app, "capability_registry", None)
        if registry is None:
            return None
        getter = getattr(registry, "get_descriptor", None)
        return getter(name) if callable(getter) else None

    def _apply_success_side_effects(self, step, args, output):
        # Match OrderedToolExecutor exactly so swapping backends is invisible.
        self.app.response_finalizer.remember_tool_use(step.capability_name, args)
        self.app.routing_state.set_decision(
            "deterministic", tool_name=step.capability_name, args=args
        )
        memory = getattr(self.app, "memory_service", None) or self.app.context_store
        memory.clear_pending_online(self.app.session_id)

    def _record_outcome(self, node: _Node, ok: bool) -> None:
        broker = getattr(self.app, "memory_broker", None)
        if broker and hasattr(broker, "record_capability_outcome"):
            try:
                broker.record_capability_outcome(node.step.capability_name, None, ok)
            except Exception:
                logger.debug("[task_graph] outcome recording failed", exc_info=True)

    def _emit_started(self, turn, step, args):
        if turn is None:
            return
        feedback = getattr(self.app, "turn_feedback", None)
        if feedback is None:
            return
        if step.capability_name == "llm_chat" and hasattr(feedback, "emit_llm_started"):
            feedback.emit_llm_started(turn, lane="chat")
        if hasattr(feedback, "emit_tool_started"):
            feedback.emit_tool_started(turn, step.capability_name, args)

    def _emit_finished(self, turn, step, ok, ms, error=""):
        if turn is None:
            return
        feedback = getattr(self.app, "turn_feedback", None)
        if feedback is None or not hasattr(feedback, "emit_tool_finished"):
            return
        feedback.emit_tool_finished(turn, step.capability_name, ok, ms, error=error)
