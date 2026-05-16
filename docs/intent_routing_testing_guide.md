# Intent-Routing A/B Benchmark — Testing Guide

This guide explains how to evaluate FRIDAY's intent router against
candidate LLMs. It is the single reference for:

* Installing the candidate models
* Running the benchmark against `tests/datasets/intent_routing_bench.yaml`
* Interpreting accuracy, precision/recall/F1, latency, and the
  per-tool confusion matrix
* Deciding whether to fine-tune

The latest run output lives at
`docs/bench_results_<YYYY_MM_DD>.md`. The script overwrites that file
on every invocation; copy or rename earlier reports if you want to keep
them.

---

## Quick Start

```bash
# 1. Install candidate models (idempotent; skips files already present).
python scripts/install_gemma_270m.py             # both Gemma variants

# 2. Run the full bench against every model.
python scripts/bench_intent_routing.py

# 3. Open the report.
xdg-open docs/bench_results_$(date -u +%Y_%m_%d).md
```

A full run takes roughly:

| Slice | Wall-clock |
|---|---|
| current only (240 cases) | ~1 minute |
| current + gemma + fn-gemma | ~5 minutes |
| current + all four LLMs | **~25 minutes** (the Qwen 4B pass dominates) |

Use `--limit N` to smoke-test a slice before committing to the full run.

---

## Pipelines Under Test

| Flag | Model | Why we test it |
|---|---|---|
| `current` | FRIDAY's live router (deterministic + embedding-router; LLM tool router off) | The baseline we have to beat. |
| `gemma` | `unsloth/gemma-3-270m-it-GGUF` Q4_K_M (~240 MB) | The smallest chat-tuned 270M Gemma. Compete on accuracy at near-zero latency cost. |
| `fn-gemma` | `unsloth/functiongemma-270m-it-GGUF` Q4_K_M (~240 MB) | Google's function-calling fine-tune of the 270M base. Best-case for a tiny dedicated intent model. |
| `qwen-1.7b` | `mlabonne_Qwen3-1.7B-abliterated-Q4_K_M` (~1.1 GB) — already shipped | Mid-size local fallback. Higher latency, much higher capability. |
| `qwen-4b` | `mlabonne_Qwen3-4B-abliterated-Q4_K_M` (~2.5 GB) — already shipped | Upper bound on what local inference can give us. |

The bench loads one LLM at a time so total RAM headroom stays under
~3 GB.

> **Note on the `current` pipeline:** the bench sets
> `FRIDAY_USE_LLM_TOOL_ROUTER=0` so the slow Qwen-4B layer inside
> `CommandRouter` is disabled — what's being measured is the
> deterministic + embedding-router fast path, which is what every
> candidate model is competing against on the latency front.

---

## Common CLI Recipes

```bash
# Default — all models, full dataset
python scripts/bench_intent_routing.py

# Only the deterministic baseline (fast — under a minute)
python scripts/bench_intent_routing.py --models current

# Only the small Gemma variants
python scripts/bench_intent_routing.py --models gemma,fn-gemma

# Quick smoke (first 30 cases)
python scripts/bench_intent_routing.py --limit 30

# Custom output path
python scripts/bench_intent_routing.py --output docs/bench_results_baseline.md

# Skip the current router (when you only want to evaluate LLM candidates)
python scripts/bench_intent_routing.py --skip-current
```

---

## Dataset Coverage

`tests/datasets/intent_routing_bench.yaml` currently holds **240
labelled cases** spanning **50 distinct tools** plus a 25-case `llm_chat`
fallback bucket and several deliberate **negative** rows (utterances
that mention a tool keyword but should NOT route to it, e.g. "the
battery in my car died").

Each row has:

| Field | Purpose |
|---|---|
| `utterance` | The literal user input. |
| `expected_tool` | Ground-truth tool name. `llm_chat` means "no specific tool should fire — defer to conversation." |
| `category` | Used for the per-category breakdown in the report. |
| `notes` | Freeform — usually a regression-guard tag back to `docs/Issues.md`. |

### Adding more cases

* Aim for **8–15 phrasings per tool** — formal, casual, terse, polite,
  typo'd, indirect, with/without args.
* For every tool, also add **1–2 negatives** if it has an obvious
  homonym ("date", "battery", "memory", …).
* Use phrasings observed in real user logs first; only invent rows
  when the logs run dry.
* Keep `expected_tool` lowercase.
* Sort within a tool by ascending complexity so the report's per-case
  table reads smoothly.

---

## Metrics Glossary

Every row produces a single `(predicted_tool, expected_tool)` pair. We
treat each tool as its own binary class — "is this case an instance of
tool T or not?" — and compute the standard text-classification metrics.

### Per-tool confusion-matrix terms

For tool **T**:

| Term | Definition |
|---|---|
| **TP (True Positive)** | Ground truth is T **and** model predicted T. |
| **FP (False Positive)** | Ground truth is **not** T but the model predicted T anyway. Tells you the tool is "trigger-happy." |
| **FN (False Negative)** | Ground truth is T but the model picked something else. Tells you the tool is **missed**. |
| **TN (True Negative)** | Ground truth is not T **and** model did not predict T. |
| **Support** | Number of cases where T is the ground truth (= TP + FN). |

### Derived per-tool metrics

| Metric | Formula | Reading it |
|---|---|---|
| **Precision** | TP / (TP + FP) | "When the model says it's T, how often is it right?" Low precision → user gets surprise side-effects. |
| **Recall** | TP / (TP + FN) | "Of all the cases where T is right, how often did we catch them?" Low recall → users have to rephrase. |
| **F1** | 2·P·R / (P + R) | Harmonic mean — balanced single-number score per tool. |
| **Accuracy** | (TP + TN) / total | Useful only as a sanity headline; doesn't distinguish per-tool errors. |

### Aggregate metrics

| Metric | Definition |
|---|---|
| **Overall accuracy** | Cases where prediction == ground truth ÷ total. The single number people glance at first. |
| **Macro precision/recall/F1** | Unweighted mean across all tools that appear in ground truth. Treats rare tools equally with common ones — sensitive to long-tail failures. |
| **Micro precision/recall/F1** | Computed from the global TP/FP/FN totals. Equivalent to overall accuracy in single-label settings. Reflects the user's average experience. |

### Latency metrics

| Metric | Definition |
|---|---|
| **p50 ms** | Median per-utterance latency. The "typical" turn cost. |
| **p95 ms** | 95th-percentile latency — the bad days. Voice UX target: < 250 ms. |
| **Mean ms** | Average — useful for cost projection but skewed by outliers; prefer p50. |

---

## Reading the Report

Open `docs/bench_results_<date>.md`. It has four sections:

### 1. Headline metrics
A compact table with one row per model: accuracy, macro P/R/F1, micro
F1, p50/p95 latency. Start here.

### 2. Per-category accuracy
One row per category (time, calendar, weather, …) with each model's
✓-count and median latency in that category. Use this to spot which
**slices** a candidate model wins or loses on. For example, the small
Gemma might match the deterministic router on `time` queries but
collapse on `calendar`.

### 3. Per-tool metrics — one section per model
The full per-tool breakdown: support, TP, FP, FN, TN, precision,
recall, F1. Sorted by support descending so the most-tested tools come
first. Two patterns to look for:

* **Low recall on a high-support tool** → users have to rephrase often.
* **Low precision on a low-support tool** → that tool is acting as a
  "vacuum cleaner" pulling in unrelated requests. Investigate the FPs.

### 4. Per-case detail
The full table — one row per utterance with each model's prediction
and per-utterance latency. Use this for failure-mode triage and to
generate new dataset entries.

---

## Decision Rules — When to Switch / Fine-tune

After running the bench against all four models, apply these rules in
order. They reflect FRIDAY's design constraints (CPU-only, voice-first,
sub-300 ms target).

1. **If the current router's macro F1 ≥ 0.90 and p95 ≤ 80 ms**, do
   nothing. We're already at the speed/quality knee for this dataset.
   Iterate on failing categories with targeted regex/embedding fixes
   instead of swapping the whole stack.

2. **If a candidate model beats the current router by < 5 macro-F1
   points but adds ≥ 200 ms p95**, do nothing. The accuracy lift is
   too small to be worth the latency hit on a voice assistant.

3. **If `fn-gemma` beats the current router by ≥ 5 macro-F1 points
   and stays under 350 ms p95**, fine-tuning is worth the effort —
   the function-tuned base is responsive to FRIDAY's tool taxonomy.
   Path: collect 1–2 k more `(utterance, expected_tool)` rows, generate
   synthetic positives + hard negatives, LoRA-tune the 270M with
   Unsloth's notebook (~30 min on Colab T4), re-export to GGUF.

4. **If `qwen-1.7b` beats everything but `qwen-4b` only marginally
   improves it (< 2 macro-F1)**, the right architecture is "Qwen 1.7B
   as the primary router, current pipeline as the fast pre-filter
   for high-confidence matches." The 4B has nothing to add.

5. **If every candidate underperforms the current router**, the
   deterministic + embedding stack is the right primitive. The
   benchmark itself is the deliverable — keep it green as we add
   tools and re-run it on every release.

---

## Known Issues / Findings

* **Function Gemma 270M with the bench's chat-completion prompt
  defaults to conversational replies** ("I can certainly help …")
  rather than emitting tool-call envelopes. The model's training
  expects a specific developer-role chat template + JSON-schema tool
  definitions that llama-cpp-python's default template doesn't supply.
  Treat the bench's `fn-gemma` numbers as a **lower bound** on what
  the model can do — proper templating (or a fine-tune) is needed
  before drawing conclusions about its capability.

* **All 270M models tend to pick the first tool in the list** when
  uncertain. Random-ordering the tool list per call may add ~3% macro
  F1 but skews repeatability; keep the deterministic order for the
  benchmark and only randomize at deployment if it survives an A/B in
  production.

* **Latency floor for any LLM-based router is ~300 ms cold + ~250 ms
  warm** on i5-12th-gen CPU at Q4_K_M. The current deterministic
  pipeline is 5–50 ms. Even a perfect-accuracy 270M trade-off has to
  justify a ~10× latency increase.

---

## Fine-Tuning Worth-It Checklist

Run this against the **failed** rows in the current best-performing
candidate model before deciding to fine-tune:

* **Coverage:** Are the failures concentrated in a few tools, or
  spread across the registry? Concentrated → easier to fix by
  prompt/regex tweaks. Spread → consider a fine-tune.
* **Pattern diversity:** Do the failed utterances share a phrasing
  pattern the training set lacks (e.g. all are "polite + question"
  but training is "imperative")? If yes, augment the dataset first;
  fine-tune second.
* **Negative pollution:** Are negatives ("I have a date tonight"
  routing to `get_date`) the dominant failure mode? Negatives are
  cheap to add to the prompt context; try that first.
* **Latency budget:** Will the fine-tuned model still meet your p95
  target? If even the base model is over 250 ms p95, fine-tuning
  won't help — switch architectures instead.

When all four checks pass, fine-tuning is the right next move. The
recommended path is LoRA on `google/gemma-3-270m-it` using
`unsloth/notebooks/gemma3-270m-it-finetune` as the starting point;
target ~1500 well-graded `(utterance, tool, args)` triples drawn from
the bench dataset's failed rows plus 3–4× as many synthetic
variations.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `gemma-3-270m-it-Q4_K_M.gguf not found` | Forgot the install step. | `python scripts/install_gemma_270m.py` |
| `functiongemma-270m-it-Q4_K_M.gguf not found` | Same. | `python scripts/install_gemma_270m.py --only fn` |
| Bench hangs on `[bench] running current router` | A registered plugin spawned a thread expecting hardware (audio, etc.). | Confirm `VoiceIOPlugin` is NOT in `register_all_plugins`; the bench uses lightweight stubs instead. |
| 0% accuracy across the board for a model | Wrong prompt template (Function Gemma) or model file corrupted. | Re-download with `python scripts/install_gemma_270m.py --only <key>`. Inspect raw output with the debug snippet in this guide. |
| `Requested tokens (N) exceed context window` mid-run | Dataset added an utterance much longer than usual. | Increase `LlmTarget.n_ctx` in `scripts/bench_intent_routing.py` for the affected model. |
| Bench shows `ms=0` for a model | The model couldn't load (file missing or `llama_cpp` import failed). The report will say `model-missing` or `load-failed` in the per-case detail's raw column. | Check the bench's stderr — the actual error is printed at load time. |

### Debug a single utterance

```python
from core.gemma_router import GemmaIntentRouter
r = GemmaIntentRouter(
    model_path="models/functiongemma-270m-it-Q4_K_M.gguf",
    mode="function",   # use "chat" for the plain Gemma + Qwen models
)
r.load()
tools = [
    {"name": "get_time", "description": "Tell the current time"},
    {"name": "get_weather", "description": "Weather for a city"},
]
d = r.route("what time is it", tools)
print(d.tool, d.latency_ms)
print(repr(d.raw_output))
```

---

## Versioning the Dataset

Treat `intent_routing_bench.yaml` as a versioned artifact. Bump it
whenever:

* a new tool is registered,
* a new Issue surfaces in `docs/Issues.md` (add a regression-guard
  row),
* a phrasing pattern is observed in user logs that the bench doesn't
  cover.

Re-run the bench after every dataset change to refresh
`bench_results_<date>.md`. The report's headline accuracy is the
single number to track between releases.
