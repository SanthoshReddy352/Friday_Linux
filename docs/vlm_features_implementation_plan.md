# FRIDAY VLM Integration — Validated Feature Set and Implementation Plan

## Current System Context

Before selecting features, the following constraints were verified against the live codebase:

- **Hardware:** Intel i5 12th Gen H, Intel UHD integrated graphics, 16 GB RAM
- **Inference stack:** llama.cpp + GGUF (Qwen3 1.7B chat, Qwen3 4B tool model)
- **Available infrastructure:** `CapabilityRegistry`, `EventBus`, `TurnFeedbackRuntime`, modular `modules/` plugin system
- **Existing embedding model:** `all-MiniLM-L6-v2` already used in `core/embedding_router.py` — no additional download for text preprocessing
- **VLM already present:** `SmolVLM2-2.2B-Instruct-Q4_K_M.gguf` (1.1 GB) + `mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf` (566 MB) in `models/`

---

## Core Architectural Rule (Confirmed Correct)

The VLM must never sit in the primary conversational pipeline. The existing `CapabilityBroker._should_use_planner()` logic and the `RouteScorer` deterministic layer already guarantee that only explicitly requested capabilities run.

**Correct flow (already achievable):**
```
Voice/Text
→ IntentRecognizer / RouteScorer (deterministic)
→ CapabilityBroker selects "analyze_screen" capability
→ VLM plugin executes on demand
→ Returns structured visual context
→ Chat model responds naturally
```

**VLM is never auto-triggered. It is a registered capability invoked only when matched.**

---

## VLM Model — Already Present

Both required model files are already in `models/`:

| File | Size | Role |
|---|---|---|
| `SmolVLM2-2.2B-Instruct-Q4_K_M.gguf` | 1.1 GB | Language decoder |
| `mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf` | 566 MB | CLIP vision projector |

**Total VLM footprint: ~1.67 GB.** With both Qwen models loaded simultaneously (1.1 GB + 2.4 GB), total resident model RAM is ~5.2 GB — well within the 16 GB budget.

**SmolVLM2 strengths for this use case:**
- Strong OCR and document reading
- Good at explaining UI elements, errors, and terminal outputs
- Instruction-tuned for short, factual visual descriptions
- Smaller than LLaVA variants at equivalent capability for screenshot analysis

**Loading in llama_cpp 0.3.20:**

```python
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava16ChatHandler

chat_handler = Llava16ChatHandler(
    clip_model_path="models/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf",
    verbose=False,
)
llm = Llama(
    model_path="models/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf",
    chat_handler=chat_handler,
    n_ctx=2048,       # keep small — vision context is image tokens + short prompt
    n_batch=256,
    verbose=False,
)
```

`Llava16ChatHandler` handles SmolVLM2's mmproj architecture correctly in llama_cpp 0.3.20. The mmproj encodes the image into visual tokens before the language decoder runs.

**Integration approach:** Load via `LocalModelManager` with a new `"vision"` role. Add `self._inference_locks["vision"]` matching the existing lock pattern in `core/model_manager.py`. Lazy-load on first request; unload after `idle_timeout_s` (default: 300 s) of inactivity.

**Realistic latency on i5-12th Gen (CPU-only):**

| Response length | Estimated time |
|---|---|
| 50 tokens (short error explanation) | 5–10 s |
| 100 tokens (screen summary) | 10–20 s |
| 150 tokens (detailed code debug) | 15–30 s |

These are explicit user requests. The voice ack ("Analyzing your screen...") fires immediately via `TurnFeedbackRuntime.emit_ack()` before VLM inference starts, so the user knows the system is working. The latency is acceptable for on-demand visual tasks.

**RAM pressure note:** When the VLM is loaded alongside both Qwen models, RAM usage reaches ~5.2 GB. The `ResourceMonitor` from the architecture plan monitors available RAM. If free RAM drops below 2 GB, the VLM auto-unloads after its current request completes.

---

## Validated Feature Set

Features are validated against three criteria:
1. Provides genuine utility on the current hardware
2. Does not degrade voice interaction latency
3. Is achievable as a standard `FridayPlugin` with a registered capability

---

## Tier 1 — Implement First (Highest ROI, Lowest Complexity)

---

### Feature 1: Screenshot Explainer

**What it does:** Captures the current screen, sends to VLM, returns a plain-language explanation.

**Use cases:**
- "What is this error?"
- "Explain this popup"
- "Why did this fail?"
- "What is on my screen?"

**Why it fits:**
- Single image, on-demand only
- No continuous processing
- VLM runs once per explicit request
- Already have `take_screenshot` capability in `system_control`

**Implementation:**

```python
# modules/vision/plugin.py
class VisionPlugin(FridayPlugin):
    def on_load(self):
        self.app.router.register_tool({
            "name": "analyze_screen",
            "description": "Take a screenshot and explain what is on the screen, including any errors, popups, or UI elements.",
            "context_terms": ["screen", "explain", "what is this", "error", "popup", "what happened"],
        })
```

**Capability handler:**
1. Take screenshot using existing `take_screenshot` tool
2. Resize to 1024px wide (reduces token count ~4x vs full resolution)
3. Load VLM via `LocalModelManager.get_model("vision")`
4. Run single inference pass
5. Return plain-language explanation to `CapabilityExecutionResult`

**Estimated latency:** 3–8 seconds on CPU (VLM inference). Acceptable because the user explicitly asked for visual analysis. Voice ack fires immediately: "Analyzing your screen..."

---

### Feature 2: OCR + Semantic Reading

**What it does:** Extracts and understands text from any image, screenshot, or document photo.

**Use cases:**
- "Read this note"
- "What does this image say?"
- "Extract the key points from this receipt"
- "Read the terminal output"

**Why it fits:**
- Replaces brittle traditional OCR with semantic understanding
- VLMs are surprisingly effective at reading handwritten text, receipts, and code terminal output
- Single-image, on-demand

**Implementation:**

```python
"name": "read_text_from_image",
"description": "Extract and read text from an image, screenshot, or photo. Works on handwritten notes, receipts, terminal outputs, code screenshots.",
"context_terms": ["read", "extract text", "ocr", "what does this say", "text from image"],
```

The VLM prompt instructs it to output clean extracted text followed by a brief interpretation.

---

### Feature 3: Screen Summarizer

**What it does:** Takes a screenshot and gives a high-level summary of what the user is currently doing.

**Use cases:**
- "Summarize my current screen"
- "What am I looking at?"
- "Give me a quick overview of this page"
- "What is important here?"

**Why it fits:**
- Single screenshot, single inference pass
- Useful for dashboards, articles, presentations, PDF pages
- Very easy to implement — same pipeline as Screenshot Explainer with a different prompt

```python
"name": "summarize_screen",
"description": "Summarize what is currently on the screen. Good for dashboards, articles, presentations, and long documents.",
"context_terms": ["summarize screen", "what am I looking at", "overview", "summary of my screen"],
```

---

### Feature 4: Clipboard Image Analyzer

**What it does:** When the user copies an image to clipboard, FRIDAY can explain or analyze it on request.

**Use cases:**
- User copies a chart, diagram, or screenshot
- "Explain this"
- "Summarize this image"
- "What is in the clipboard?"

**Why it fits:**
- Event-driven: triggered by user request, not continuous monitoring
- Removes copy-paste friction significantly
- Cross-platform clipboard access via `pyperclip` / `PIL.ImageGrab`

**Implementation:**

```python
"name": "analyze_clipboard_image",
"description": "Analyze or explain the image currently copied in the clipboard.",
"context_terms": ["clipboard", "analyze this", "explain the image", "what did I copy"],
```

Handler checks `PIL.ImageGrab.grabclipboard()` for an image. If no image is in clipboard, returns a clear explanation to the user.

---

### Feature 5: Code Screenshot Debugger

**What it does:** Reads a screenshot of code, a terminal error, or a stack trace and explains what is wrong.

**Use cases:**
- "Explain this stack trace"
- "What is wrong in this code?"
- "Why is this terminal failing?"
- "Find the syntax error"

**Why it fits:**
- VLMs are particularly effective on code and terminal content
- High daily utility for a developer
- Single image, on-demand

**Implementation:**

```python
"name": "debug_code_screenshot",
"description": "Read a screenshot of code, a terminal error, or a stack trace and explain the issue.",
"context_terms": ["stack trace", "debug screenshot", "code error", "terminal error", "syntax error"],
```

Uses a specialized VLM prompt: "You are a debugging assistant. Read this code/terminal screenshot and explain exactly what the error is and how to fix it."

---

## Tier 2 — Implement After Tier 1 Stable (Medium Complexity)

---

### Feature 6: Screenshot Comparison

**What it does:** Compares two screenshots and describes what changed.

**Use cases:**
- "What changed between these?"
- "Did this value change?"
- "Compare these two screens"

**Implementation approach:** Send both images side-by-side (concatenated horizontally) in a single VLM call. The model receives "Image A" and "Image B" labels.

```python
"name": "compare_screenshots",
"description": "Compare two screenshots and explain what changed or is different.",
"context_terms": ["compare screenshots", "what changed", "difference between", "before and after"],
```

---

### Feature 7: UI Element Finder

**What it does:** Takes a screenshot and locates a described UI element, returning approximate coordinates.

**Use cases:**
- "Find the login button"
- "Where is the download option?"
- "Locate settings"

**Why this matters:** This is the foundation for future automation workflows. With coordinates, the system can trigger clicks.

**Implementation approach:** VLM returns bounding box description in structured format. A secondary pass normalizes coordinates. Integration with `xdotool` (Linux) for clicking.

**Complexity:** Medium — requires structured VLM output parsing. Worth implementing after simpler tools are stable.

---

### Feature 8: Smart Error Detector

**What it does:** Monitors for crash dialogs and known error patterns using cheap heuristics. Only invokes VLM when confidence of an error is high.

**Why the cheap-heuristics-first approach matters:**
- Window title detection via `wmctrl` or `xdotool` is near-zero cost
- Image hash differencing catches visual changes without VLM
- OCR keyword scan (no VLM) for "error", "failed", "exception" eliminates 90% of false positives before VLM is invoked

**Correct pipeline:**
```
Window title changed → check for "Error"|"Warning"|"Failed" keywords
→ If match: run lightweight OCR keyword scan
→ If keywords confirm error: invoke VLM for full explanation
→ Publish "assistant_progress" with explanation
```

VLM is invoked only when two cheap gates both pass.

---

## Tier 3 — Fun Features (Low Cost, High Personality)

These are easy, CPU-cheap (single image + simple prompt), and improve FRIDAY's character significantly.

---

### Feature 9: Meme Explainer

```python
"name": "explain_meme",
"description": "Explain a meme — the joke, context, and why it is funny.",
"context_terms": ["explain this meme", "why is this funny", "what is the joke", "explain meme"],
```

---

### Feature 10: Roast My Desktop

```python
"name": "roast_desktop",
"description": "Take a screenshot and make a humorous comment about the current desktop state — too many tabs, messy files, etc.",
"context_terms": ["roast my desktop", "roast my screen", "make fun of my desktop"],
```

VLM prompt: "You are a witty assistant. Look at this desktop screenshot and make a single funny, observational joke about what you see. Be playful, not mean."

---

### Feature 11: Design/UI Reviewer

```python
"name": "review_design",
"description": "Analyze a UI screenshot or design and give honest aesthetic and usability feedback.",
"context_terms": ["how does this look", "review this design", "rate this ui", "design feedback"],
```

---

## Features Excluded (With Reasoning)

| Feature | Reason Excluded |
|---|---|
| Continuous webcam analysis | Destroys CPU budget, impossible on integrated graphics |
| Continuous desktop streaming | Kills responsiveness, unnecessary for current use cases |
| Recursive autonomous vision agents | Re-analyze → re-plan → re-observe loops are CPU-prohibitive |
| Real-time gaming companion | Requires frame-by-frame analysis, not feasible on CPU |
| Workspace Focus Monitor (continuous) | Acceptable only as sparse event-triggered variant |

---

## Plugin Architecture

All VLM features live in a single `modules/vision/` plugin:

```
modules/vision/
├── __init__.py
├── plugin.py          # FridayPlugin — registers all capabilities
├── service.py         # VisionService — model loading, inference, preprocessing
├── screenshot.py      # Screen capture utilities
├── preprocess.py      # Image resizing, format normalization
└── prompts.py         # Per-feature VLM prompts
```

**`VisionService`** handles:
- Lazy VLM loading via `Llava16ChatHandler` + `Llama` (only on first call)
- `threading.Lock()` for safe concurrent access (matching `LocalModelManager` pattern)
- Auto-unload after `idle_timeout_s` (default: 300 seconds) via a watchdog timer
- Image resizing to `max_width=1024` before inference (reduces visual token count ~4x)
- RAM guard: checks `ResourceMonitor.snapshot().ram_available_mb` before loading; refuses to load VLM if < 3 GB free

**`plugin.py`** registers each capability using `self.app.router.register_tool()`, same as all other plugins.

---

## Configuration

Add to `config.yaml`:

```yaml
vision:
  enabled: true
  model_path: "models/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf"
  mmproj_path: "models/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf"
  n_ctx: 2048
  max_image_width: 1024
  idle_timeout_s: 300
  features:
    screenshot_explainer: true
    ocr_reader: true
    screen_summarizer: true
    clipboard_analyzer: true
    code_debugger: true
    compare_screenshots: true
    ui_element_finder: false    # enable when xdotool integration is ready
    smart_error_detector: false # enable after Tier 1 stable
    fun_features: true
```

---

## Implementation Order

```
Week 1:
  - VisionService skeleton with lazy loading
  - Feature 1: analyze_screen
  - Feature 2: read_text_from_image
  - Feature 3: summarize_screen

Week 2:
  - Feature 4: analyze_clipboard_image
  - Feature 5: debug_code_screenshot
  - Feature 9-11: fun features (very low effort)

Week 3:
  - Feature 6: compare_screenshots
  - Feature 7: ui_element_finder
  - Feature 8: smart_error_detector (heuristics first)
```

---

## Latency Expectations

SmolVLM2-2.2B at Q4_K_M on i5-12th Gen (CPU-only, no GPU offload):

| Feature | Typical Response Length | Estimated Time | Voice Ack |
|---|---|---|---|
| Screenshot explainer | 60–80 tokens | 6–16 s | "Analyzing your screen..." |
| OCR reader | 40–60 tokens | 4–12 s | "Reading that..." |
| Screen summarizer | 50–80 tokens | 5–16 s | "Summarizing..." |
| Clipboard analyzer | 50–80 tokens | 5–16 s | "Looking at your clipboard..." |
| Code debugger | 80–120 tokens | 8–24 s | "Reading the error..." |
| Meme explainer | 40–60 tokens | 4–12 s | "Let me look at this..." |

**All latency is acceptable because:**
1. These are explicit user requests — the user chose to invoke visual analysis
2. Voice ack fires immediately via `TurnFeedbackRuntime.emit_ack()` before VLM inference starts
3. VLM runs behind a dedicated `"vision"` inference lock — it cannot block the chat or tool model
4. VLM is never invoked during a normal conversational turn

**First-load penalty:** SmolVLM2 takes 3–6 seconds to load from disk (mmproj + decoder). This happens once per idle timeout cycle. After that, subsequent calls within the timeout window have no load delay.

**To reduce response length and improve latency:** All VLM prompts in `prompts.py` end with the instruction "Be brief. Maximum 2 sentences." This keeps typical responses under 60 tokens and inference under 12 seconds on this hardware.
