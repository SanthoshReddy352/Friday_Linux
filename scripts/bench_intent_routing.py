"""A/B benchmark — current intent router vs. one or more candidate LLMs.

Runs every utterance in ``tests/datasets/intent_routing_bench.yaml``
through one or more pipelines and writes a Markdown report to
``docs/bench_results_<UTC date>.md``. Reported metrics per pipeline:

* Overall accuracy
* Per-tool precision, recall, F1 (treating each tool as a binary class)
* Macro-averaged precision / recall / F1
* Confusion-style TP / FP / FN / TN per tool
* p50 / p95 latency

Pipelines available (pick any subset via ``--models``):

* ``current``  — the live FRIDAY CommandRouter (deterministic +
  embedding-router; the slow Qwen-4B LLM tool router is disabled via
  ``FRIDAY_USE_LLM_TOOL_ROUTER=0`` so the bench focuses on the fast
  path).
* ``gemma``    — Gemma 3 270M IT (general instruction-tuned).
* ``fn-gemma`` — Function Gemma 270M (Google's tool-calling fine-tune
  of the 270M base).
* ``qwen-1.7b``, ``qwen-4b`` — the same Qwen3 GGUFs FRIDAY ships,
  prompted with the same JSON-output classification template so the
  comparison is apples-to-apples.

Usage::

    python scripts/bench_intent_routing.py                 # all models
    python scripts/bench_intent_routing.py --models current,gemma
    python scripts/bench_intent_routing.py --limit 30      # quick smoke
    python scripts/bench_intent_routing.py --output docs/my_run.md

Tool callbacks are stubbed before benching so the current pipeline
doesn't fire real side effects (HTTP calls, file writes, etc.).
"""

from __future__ import annotations


def _relaunch_under_project_venv() -> None:
    """Stdlib-only venv shim — see ``main.py`` for rationale."""
    import os
    import sys

    if os.environ.get("FRIDAY_SKIP_VENV_AUTOEXEC") == "1":
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_root = os.path.join(repo_root, ".venv")
    if os.name == "nt":
        candidate = os.path.join(venv_root, "Scripts", "python.exe")
    else:
        candidate = os.path.join(venv_root, "bin", "python3")
        if not os.path.exists(candidate):
            candidate = os.path.join(venv_root, "bin", "python")
    if not os.path.exists(candidate):
        return
    try:
        already = os.path.realpath(sys.prefix) == os.path.realpath(venv_root)
    except OSError:
        already = False
    if already:
        return
    if os.environ.get("_FRIDAY_VENV_RELAUNCHED") == "1":
        return
    os.environ["_FRIDAY_VENV_RELAUNCHED"] = "1"
    os.execv(candidate, [candidate, *sys.argv])


_relaunch_under_project_venv()


import argparse
import gc
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Disable the slow Qwen-4B in-router tool path for the current-pipeline
# runs — must be set before importing CommandRouter.
os.environ.setdefault("FRIDAY_USE_LLM_TOOL_ROUTER", "0")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml  # PyYAML — already in requirements.txt

from core.assistant_context import AssistantContext
from core.context_store import ContextStore
from core.dialog_state import DialogState
from core.gemma_router import GemmaIntentRouter
from core.router import CommandRouter
from core.workflow_orchestrator import WorkflowOrchestrator


# =====================================================================
# Model catalogue — which GGUFs map to which CLI flag
# =====================================================================


@dataclass(frozen=True)
class LlmTarget:
    key: str
    display_name: str
    gguf_filename: str   # under ``models/``
    install_hint: str    # what to run if missing
    n_ctx: int = 2048
    max_tokens: int = 64


LLM_TARGETS: dict[str, LlmTarget] = {
    "gemma": LlmTarget(
        key="gemma",
        display_name="Gemma 3 270M IT (FRIDAY-tuned)",
        gguf_filename="gemma-3-270m-it-Q4_K_M.gguf",
        install_hint="python scripts/train_gemma_lora.py",
        max_tokens=16,        # tool name only
    ),
    "fn-gemma": LlmTarget(
        key="fn-gemma",
        display_name="Function Gemma 270M (FRIDAY-tuned)",
        gguf_filename="functiongemma-270m-it-Q4_K_M.gguf",
        install_hint="python scripts/train_fngemma_lora.py",
        max_tokens=40,        # envelope + JSON: <start_function_call>{"tool":"...","args":{}}<end_function_call>
    ),
}

# Qwen models dropped from the lineup — too slow for the 250 ms p95
# budget. Bench now compares only the deterministic baseline vs the
# two FRIDAY-tuned 270M LoRAs.
ALL_MODELS = ("current", "gemma", "fn-gemma")


# =====================================================================
# Test bench scaffolding
# =====================================================================


@dataclass
class CaseResult:
    utterance: str
    expected: str
    category: str
    notes: str
    predictions: dict = field(default_factory=dict)   # model_key -> (tool, latency_ms, raw)


def load_dataset(path: str, limit: int | None = None) -> list[dict]:
    """Load bench cases from YAML (legacy) or JSONL (synth output)."""
    import json
    lower = path.lower()
    if lower.endswith(".jsonl"):
        cases = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                cases.append({
                    "utterance":     row["utterance"],
                    "expected_tool": row["expected_tool"],
                    "category":      row.get("category", row["expected_tool"]),
                    "notes":         row.get("notes") or row.get("source", ""),
                })
    else:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        cases = data.get("cases", [])
    if limit:
        cases = cases[:limit]
    return cases


def build_app(tmp_root: str):
    event_bus = MagicMock()
    app = SimpleNamespace()
    app.config = SimpleNamespace(get=lambda k, d=None: d)
    app.event_bus = event_bus
    app.dialog_state = DialogState()
    app.assistant_context = AssistantContext()
    app.context_store = ContextStore(
        db_path=os.path.join(tmp_root, "bench.db"),
        vector_path=os.path.join(tmp_root, "bench-chroma"),
    )
    app.session_id = app.context_store.start_session({"source": "bench"})
    app.assistant_context.bind_context_store(app.context_store, app.session_id)
    app.router = CommandRouter(event_bus)
    app.router.dialog_state = app.dialog_state
    app.router.assistant_context = app.assistant_context
    app.router.context_store = app.context_store
    app.router.session_id = app.session_id
    app.workflow_orchestrator = WorkflowOrchestrator(app)
    app.router.workflow_orchestrator = app.workflow_orchestrator
    app.memory_service = app.context_store
    app.emit_assistant_message = MagicMock()
    return app


def register_all_plugins(app) -> None:
    from modules.system_control.plugin import SystemControlPlugin
    from modules.task_manager.plugin import TaskManagerPlugin
    from modules.browser_automation.plugin import BrowserAutomationPlugin
    from modules.weather.plugin import WeatherPlugin
    from modules.llm_chat.plugin import LLMChatPlugin
    from modules.dictation.plugin import DictationPlugin
    from modules.focus_session.plugin import FocusSessionPlugin

    SystemControlPlugin(app)
    TaskManagerPlugin(app)
    BrowserAutomationPlugin(app)
    WeatherPlugin(app)
    LLMChatPlugin(app)
    DictationPlugin(app)
    FocusSessionPlugin(app)
    _register_voice_stubs(app)
    _register_email_stubs(app)
    _register_memory_stubs(app)
    _register_chat_only_stubs(app)


def _register_voice_stubs(app) -> None:
    """Register voice-tool *names* without booting the audio stack."""
    voice_specs = [
        {"name": "set_voice_mode", "description": "Switch voice listening mode between persistent, wake-word, on-demand, or manual.", "parameters": {"mode": "string"}},
        {"name": "enable_voice", "description": "Enable the microphone and start listening for voice commands.", "parameters": {}},
        {"name": "disable_voice", "description": "Disable the microphone and stop listening for voice commands.", "parameters": {}},
    ]
    for spec in voice_specs:
        app.router.register_tool(spec, lambda t, a, _n=spec["name"]: f"[stub:{_n}]")


def _register_email_stubs(app) -> None:
    email_specs = [
        {"name": "read_latest_email", "description": "Read the most recent unread email aloud.", "parameters": {}, "aliases": ["read latest email"]},
        {"name": "summarize_inbox", "description": "Summarize all unread Gmail emails into a single spoken paragraph.", "parameters": {}, "aliases": ["summarize inbox"]},
    ]
    for spec in email_specs:
        app.router.register_tool(spec, lambda t, a, _n=spec["name"]: f"[stub:{_n}]")


def _register_memory_stubs(app) -> None:
    memory_specs = [
        {
            "name": "show_memories",
            "description": "Show what FRIDAY remembers about the user.",
            "parameters": {},
            "aliases": ["show my memories", "what do you remember"],
            "patterns": [r"\b(?:what do you (?:remember|know)(?:\s+about\s+(?:me|us))?|"
                         r"show (?:me )?(?:my )?memories|"
                         r"what are my preferences|what have you learned)\b"],
        },
        {
            "name": "delete_memory",
            "description": "Forget a previously remembered fact.",
            "parameters": {},
            "aliases": ["forget", "delete memory"],
            "patterns": [r"\b(?:forget (?:that|what i (?:said|told you))|"
                         r"delete (?:that )?memory|remove (?:that )?(?:memory|fact)|"
                         r"stop remembering)\b"],
        },
    ]
    for spec in memory_specs:
        if spec["name"] in app.router._tools_by_name:
            continue
        app.router.register_tool(spec, lambda t, a, _n=spec["name"]: f"[stub:{_n}]")


def _register_chat_only_stubs(app) -> None:
    extras = [
        {
            "name": "greet",
            "description": "Say hello back to the user.",
            "parameters": {},
            "aliases": ["hello", "hi", "hey"],
            "patterns": [r"^(?:hi|hello|hey)(?:\s+(?:there|friday))?[!?.]*$"],
        },
    ]
    for spec in extras:
        if spec["name"] in app.router._tools_by_name:
            continue
        app.router.register_tool(spec, lambda t, a, _n=spec["name"]: f"[stub:{_n}]")


def stub_callbacks(router: CommandRouter) -> None:
    """Replace each tool callback with a recorder that returns "OK"."""
    for spec_name, route in router._tools_by_name.items():
        route["callback"] = lambda text, args, _name=spec_name: f"[stub:{_name}]"


def collect_llm_tools(router: CommandRouter) -> list[dict]:
    tools = []
    for name, route in router._tools_by_name.items():
        spec = route.get("spec") or {}
        tools.append({
            "name": name,
            "description": spec.get("description", "")[:200],
            "examples": spec.get("aliases", [])[:2] or (spec.get("context_terms") or [])[:2],
        })
    return tools


def allowed_tool_names(tools: list[dict]) -> list[str]:
    return [t["name"] for t in tools if t.get("name")]


# =====================================================================
# Per-model runners
# =====================================================================


def run_current(app, utterance: str) -> tuple[str, float, str]:
    t0 = time.perf_counter()
    raw = ""
    try:
        raw = app.router.process_text(utterance) or ""
    except Exception:
        pass
    elapsed = (time.perf_counter() - t0) * 1000.0
    decision = app.router.last_routing_decision
    tool = getattr(decision, "tool_name", "") or ""
    return tool, elapsed, (raw[:160] if isinstance(raw, str) else "")


def run_llm(router: GemmaIntentRouter, utterance: str, tools: list[dict], names: list[str]) -> tuple[str, float, str]:
    d = router.route(utterance, tools)
    tool = GemmaIntentRouter.normalize_tool_name(d.tool, names) or ""
    return tool, d.latency_ms, d.raw_output[:160]


def make_llm_router(target: LlmTarget) -> GemmaIntentRouter:
    # Function Gemma 270M was fine-tuned for the
    # <start_function_call>{json}<end_function_call> envelope; every
    # other model gets the generic JSON chat-prompt path.
    mode = "function" if target.key == "fn-gemma" else "chat"
    return GemmaIntentRouter(
        model_path=os.path.join(REPO_ROOT, "models", target.gguf_filename),
        n_ctx=target.n_ctx,
        max_tokens=target.max_tokens,
        mode=mode,
    )


# =====================================================================
# Metrics
# =====================================================================


@dataclass
class ToolMetrics:
    name: str
    support: int = 0     # count of cases where this tool is the ground truth
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0


def compute_metrics(results: list[CaseResult], model_key: str) -> dict:
    """Return per-tool ToolMetrics + macro / micro aggregates."""
    labels: set[str] = set()
    for r in results:
        labels.add(r.expected)
        pred, *_ = r.predictions.get(model_key, ("", 0.0, ""))
        if pred:
            labels.add(pred)

    per_tool: dict[str, ToolMetrics] = {label: ToolMetrics(name=label) for label in labels}
    total = len(results)
    correct = 0
    for r in results:
        pred, *_ = r.predictions.get(model_key, ("", 0.0, ""))
        if pred == r.expected:
            correct += 1
        for label, m in per_tool.items():
            actual_positive = (r.expected == label)
            predicted_positive = (pred == label)
            if actual_positive:
                m.support += 1
            if actual_positive and predicted_positive:
                m.tp += 1
            elif not actual_positive and predicted_positive:
                m.fp += 1
            elif actual_positive and not predicted_positive:
                m.fn += 1
            else:
                m.tn += 1

    # Macro = unweighted mean across labels that have at least one ground truth.
    tracked = [m for m in per_tool.values() if m.support > 0]
    macro_p = statistics.fmean(m.precision for m in tracked) if tracked else 0.0
    macro_r = statistics.fmean(m.recall for m in tracked) if tracked else 0.0
    macro_f1 = statistics.fmean(m.f1 for m in tracked) if tracked else 0.0

    # Micro = compute from the totals (= accuracy in single-label setting).
    sum_tp = sum(m.tp for m in tracked)
    sum_fp = sum(m.fp for m in tracked)
    sum_fn = sum(m.fn for m in tracked)
    micro_p = sum_tp / (sum_tp + sum_fp) if (sum_tp + sum_fp) else 0.0
    micro_r = sum_tp / (sum_tp + sum_fn) if (sum_tp + sum_fn) else 0.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) else 0.0

    lats = [r.predictions[model_key][1] for r in results if model_key in r.predictions and r.predictions[model_key][1] > 0]
    return {
        "n": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "per_tool": per_tool,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "p50_ms": statistics.median(lats) if lats else 0.0,
        "p95_ms": _p95(lats),
        "mean_ms": statistics.fmean(lats) if lats else 0.0,
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]


# =====================================================================
# Report writer
# =====================================================================


def write_report(path: str, results: list[CaseResult], active_models: list[str], metrics: dict) -> None:
    lines: list[str] = []
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Intent-routing benchmark — {now}\n")
    lines.append(f"**Cases:** {len(results)}\n")
    lines.append(f"**Models compared:** {', '.join(active_models)}\n")
    lines.append("")

    # Headline table -------------------------------------------------
    lines.append("## Headline metrics\n")
    head = ["Model", "Accuracy", "Macro P", "Macro R", "Macro F1", "Micro F1", "p50 ms", "p95 ms"]
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + "|".join(["---"] * len(head)) + "|")
    for key in active_models:
        m = metrics[key]
        lines.append(
            f"| {key} | {m['accuracy']*100:.1f}% | {m['macro_precision']:.3f} | "
            f"{m['macro_recall']:.3f} | {m['macro_f1']:.3f} | {m['micro_f1']:.3f} | "
            f"{m['p50_ms']:.0f} | {m['p95_ms']:.0f} |"
        )
    lines.append("")

    # Per-category breakdown (accuracy + p50 latency) ---------------
    lines.append("## Per-category accuracy\n")
    cats = sorted({r.category for r in results})
    header = ["Category", "N"] + [f"{k} ✓" for k in active_models] + [f"{k} p50" for k in active_models]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for cat in cats:
        rows = [r for r in results if r.category == cat]
        row = [cat, str(len(rows))]
        for key in active_models:
            ok = sum(1 for r in rows if r.predictions.get(key, ("",))[0] == r.expected)
            row.append(f"{ok}/{len(rows)}")
        for key in active_models:
            lats = [r.predictions[key][1] for r in rows if key in r.predictions and r.predictions[key][1] > 0]
            row.append(f"{statistics.median(lats):.0f}ms" if lats else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Per-tool precision/recall/F1 — one section per model ----------
    for key in active_models:
        lines.append(f"## Per-tool metrics — `{key}`\n")
        lines.append("| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        ptm = metrics[key]["per_tool"]
        # Only show tools that appear in ground truth at least once,
        # sorted by support descending for readability.
        rows = sorted(
            (m for m in ptm.values() if m.support > 0),
            key=lambda m: (-m.support, m.name),
        )
        for m in rows:
            lines.append(
                f"| `{m.name}` | {m.support} | {m.tp} | {m.fp} | {m.fn} | {m.tn} | "
                f"{m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} |"
            )
        lines.append("")

    # Per-case detail -----------------------------------------------
    lines.append("## Per-case detail\n")
    head_cols = ["#", "Utterance", "Expected"]
    for k in active_models:
        head_cols += [f"{k}", f"{k} ✓", f"{k} ms"]
    head_cols.append("Notes")
    lines.append("| " + " | ".join(head_cols) + " |")
    lines.append("|" + "|".join(["---"] * len(head_cols)) + "|")
    for i, r in enumerate(results, 1):
        row = [str(i), f"`{r.utterance}`", f"`{r.expected}`"]
        for key in active_models:
            pred_tool, pred_ms, _ = r.predictions.get(key, ("", 0.0, ""))
            row.append(f"`{pred_tool or '—'}`")
            row.append("✓" if pred_tool == r.expected else "✗")
            row.append(f"{pred_ms:.0f}")
        row.append(r.notes.replace("|", "\\|") if r.notes else "")
        lines.append("| " + " | ".join(row) + " |")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# =====================================================================
# Main
# =====================================================================


def parse_models(arg: str | None) -> list[str]:
    if not arg:
        return list(ALL_MODELS)
    requested = [x.strip() for x in arg.split(",") if x.strip()]
    unknown = [r for r in requested if r not in ALL_MODELS]
    if unknown:
        raise SystemExit(f"unknown model(s): {unknown} — valid: {ALL_MODELS}")
    return requested


def main() -> int:
    parser = argparse.ArgumentParser(description="Intent routing A/B benchmark.")
    parser.add_argument(
        "--dataset",
        default=os.path.join(REPO_ROOT, "tests", "datasets", "intent_test.jsonl"),
        help="Default: the held-out 328-row synth test set. Pass "
             "tests/datasets/intent_routing_bench.yaml for the legacy regression set.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(REPO_ROOT, "docs", f"bench_results_{datetime.now().strftime('%Y_%m_%d')}.md"),
    )
    parser.add_argument(
        "--models",
        help="Comma-separated subset of " + ",".join(ALL_MODELS) + " (default: all)",
    )
    parser.add_argument("--limit", type=int, help="Run only the first N cases (smoke test)")
    parser.add_argument("--skip-current", action="store_true", help="Equivalent to --models without 'current'")
    args = parser.parse_args()

    active_models = parse_models(args.models)
    if args.skip_current and "current" in active_models:
        active_models.remove("current")

    cases = load_dataset(args.dataset, limit=args.limit)
    print(f"[bench] {len(cases)} cases loaded from {args.dataset}")
    print(f"[bench] models: {active_models}")

    import tempfile
    tmp = tempfile.mkdtemp(prefix="friday-bench-")
    app = build_app(tmp)
    register_all_plugins(app)
    stub_callbacks(app.router)
    llm_tools = collect_llm_tools(app.router)
    names = allowed_tool_names(llm_tools)

    # First pass: current router (no model load) ---------------------
    results: list[CaseResult] = []
    for case in cases:
        results.append(CaseResult(
            utterance=case["utterance"],
            expected=case["expected_tool"],
            category=case.get("category", "uncategorized"),
            notes=case.get("notes", ""),
        ))

    if "current" in active_models:
        print("[bench] running current router …")
        for i, r in enumerate(results, 1):
            tool, ms, raw = run_current(app, r.utterance)
            r.predictions["current"] = (tool, ms, raw)
            if i % 25 == 0 or i == len(results):
                print(f"  [{i}/{len(results)}] current")

    # Subsequent passes: load one LLM at a time, run it, unload. -----
    for key in active_models:
        if key == "current":
            continue
        target = LLM_TARGETS[key]
        path = os.path.join(REPO_ROOT, "models", target.gguf_filename)
        if not os.path.exists(path):
            print(
                f"[bench] {target.display_name} not found at {path} — "
                f"install with: {target.install_hint}",
                file=sys.stderr,
            )
            for r in results:
                r.predictions[key] = ("", 0.0, "model-missing")
            continue
        print(f"[bench] loading {target.display_name} from {target.gguf_filename} …")
        router = make_llm_router(target)
        if not router.load():
            print(f"[bench] {target.display_name} failed to load — skipping.", file=sys.stderr)
            for r in results:
                r.predictions[key] = ("", 0.0, "load-failed")
            continue
        for i, r in enumerate(results, 1):
            tool, ms, raw = run_llm(router, r.utterance, llm_tools, names)
            r.predictions[key] = (tool, ms, raw)
            if i % 25 == 0 or i == len(results):
                print(f"  [{i}/{len(results)}] {key}")
        # Free the model before loading the next one.
        router.unload()
        del router
        gc.collect()

    # Metrics --------------------------------------------------------
    metrics = {k: compute_metrics(results, k) for k in active_models}

    write_report(args.output, results, active_models, metrics)
    print(f"\n[bench] report written to {args.output}\n")

    # Stdout summary -------------------------------------------------
    header = f"{'Model':<14} {'Accuracy':>10} {'Macro F1':>10} {'p50 ms':>9} {'p95 ms':>9}"
    print(header)
    print("-" * len(header))
    for key in active_models:
        m = metrics[key]
        print(
            f"{key:<14} {m['accuracy']*100:>9.1f}% {m['macro_f1']:>10.3f} "
            f"{m['p50_ms']:>8.0f}ms {m['p95_ms']:>8.0f}ms"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
