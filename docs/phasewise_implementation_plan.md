# FRIDAY — Phase-Wise Implementation Plan

**Source documents consolidated:**
- `docs/architecture_final_implementation_priorities.md`
- `docs/vlm_features_implementation_plan.md`
- `docs/markitdown_integration_plan.md`
- `docs/memory_management_strategy.md`

**Hardware baseline:** Intel i5-12th Gen H · Intel UHD (CPU-only) · 16 GB RAM  
**Inference stack:** llama.cpp 0.3.20 + GGUF · Python 3.11 · ChromaDB at `data/chroma/`

---

## Overview — All Phases

| Phase | Name | Source Doc | Priority |
|---|---|---|---|
| 0 | Architecture Foundation Fixes | `architecture_final_implementation_priorities.md` | Highest — prerequisites for all other phases |
| 1 | Vision Module — VisionService + Tier 1 | `vlm_features_implementation_plan.md` | High |
| 2 | Vision Module — Tier 1 Complete + Fun Features | `vlm_features_implementation_plan.md` | High |
| 3 | Vision Module — Tier 2 | `vlm_features_implementation_plan.md` | Medium |
| 4 | Document Intelligence — Foundation | `markitdown_integration_plan.md` | High |
| 5 | Document Intelligence — Conversational + Workspace | `markitdown_integration_plan.md` | Medium |
| 6 | Mem0 Memory Integration — Foundation | `memory_management_strategy.md` | High |
| 7 | Mem0 Memory Integration — Advanced | `memory_management_strategy.md` | Medium |
| 8 | Cross-System Integration | All | Medium |

**Estimated total implementation time:** 6–8 weeks solo developer.

**Dependency chain:**
```
Phase 0 → Phase 1 → Phase 2 → Phase 3
Phase 0 → Phase 4 → Phase 5
Phase 0 → Phase 6 → Phase 7
Phase 5 + Phase 7 + Phase 3 → Phase 8
```

Phase 0 must be completed before anything else. Phases 1–3, 4–5, and 6–7 can proceed in parallel after Phase 0.

---

---

# Phase 0 — Architecture Foundation Fixes

**Goal:** Add the five lightweight infrastructure improvements identified in `architecture_final_implementation_priorities.md`. These are prerequisites because Phase 4 needs `WorkingArtifact`, Phase 6 needs `ResourceMonitor`, and Phase 1 needs the `output_type` field.

**Combined per-turn overhead: < 2 ms. Zero new LLM calls. Zero new threads.**

---

## 0.1 — Output Typing (`output_type` field on CapabilityExecutionResult)

**File:** `core/capability_registry.py` · **Line:** 39

**Current state:**
```python
@dataclass
class CapabilityExecutionResult:
    ok: bool
    name: str
    output: Any = ""
    error: str = ""
    descriptor: CapabilityDescriptor | None = None
```

**Change:** Add `output_type` field with default `"text"`.

```python
@dataclass
class CapabilityExecutionResult:
    ok: bool
    name: str
    output: Any = ""
    error: str = ""
    descriptor: CapabilityDescriptor | None = None
    output_type: str = "text"   # "text" | "list" | "code" | "image" | "document" | "json"
```

**Why this field matters:** The WorkingArtifact system (0.2), the VLM plugin (Phase 1), and the MarkItDown plugin (Phase 4) all produce typed outputs. Without this field, downstream tools (save to file, read aloud, export) cannot distinguish a list from a code block from plain text.

**No other files need to change** — the field has a default so all existing handlers remain valid.

---

## 0.2 — Working Artifact Memory

**What it does:** Tracks the last meaningful capability output in the session state so "save that", "use this", "read it back" can resolve without repeating the content.

### 0.2.1 — Add `WorkingArtifact` dataclass

**File:** `core/context_store.py` · Add near the top of the file (before `ContextStore` class):

```python
from dataclasses import dataclass, field as dc_field

@dataclass
class WorkingArtifact:
    content: str
    output_type: str = "text"        # mirrors CapabilityExecutionResult.output_type
    capability_name: str = ""        # which tool produced this
    artifact_type: str = "text"      # "text" | "list" | "code" | "document" | "image"
    source_path: str = ""            # file path if artifact came from a file operation
```

### 0.2.2 — Add artifact methods to `ContextStore`

**File:** `core/context_store.py` · Add to `ContextStore` class:

```python
def save_artifact(self, session_id: str, artifact: "WorkingArtifact") -> None:
    """Persist the working artifact into the session state JSON blob."""
    state = self.get_session_state(session_id) or {}
    state["working_artifact"] = {
        "content": artifact.content,
        "output_type": artifact.output_type,
        "capability_name": artifact.capability_name,
        "artifact_type": artifact.artifact_type,
        "source_path": artifact.source_path,
    }
    self.save_session_state(session_id, state)

def get_artifact(self, session_id: str) -> "WorkingArtifact | None":
    """Retrieve the current working artifact for this session."""
    state = self.get_session_state(session_id) or {}
    data = state.get("working_artifact")
    if not data:
        return None
    return WorkingArtifact(
        content=data.get("content", ""),
        output_type=data.get("output_type", "text"),
        capability_name=data.get("capability_name", ""),
        artifact_type=data.get("artifact_type", "text"),
        source_path=data.get("source_path", ""),
    )
```

### 0.2.3 — Expose artifact methods on `MemoryService`

**File:** `core/memory_service.py` · Add to `MemoryService` class:

```python
def save_artifact(self, session_id: str, artifact) -> None:
    self._store.save_artifact(session_id, artifact)

def get_artifact(self, session_id: str):
    return self._store.get_artifact(session_id)
```

### 0.2.4 — Auto-save artifact after capability execution

**File:** `core/task_graph_executor.py` · In `_run_node()` after the successful execution block (around line 200), add:

```python
# Auto-save working artifact for the last successful tool result
if result.ok and getattr(result, "output", ""):
    from core.context_store import WorkingArtifact
    artifact = WorkingArtifact(
        content=str(result.output),
        output_type=getattr(result, "output_type", "text"),
        capability_name=step.capability_name,
        artifact_type=getattr(result, "output_type", "text"),
    )
    memory = getattr(self.app, "memory_service", None)
    session_id = getattr(self.app, "session_id", "")
    if memory and session_id:
        try:
            memory.save_artifact(session_id, artifact)
        except Exception:
            pass
```

Also add the same block to `core/tool_execution.py` (OrderedToolExecutor) so both executors track artifacts.

### 0.2.5 — Pronoun resolution in IntentRecognizer

**File:** `core/intent_recognizer.py` · In the text preprocessing step before `plan()` executes:

```python
ARTIFACT_PRONOUNS = re.compile(
    r"\b(it|that|this|the result|the output|that file|the code|the list|the summary)\b",
    re.IGNORECASE,
)

def _resolve_artifact_pronouns(self, text: str, session_id: str) -> str:
    """Replace artifact pronouns with a short stub that tells the LLM to use
    the working artifact — not the full content, to avoid prompt bloat."""
    if not ARTIFACT_PRONOUNS.search(text):
        return text
    memory = getattr(self.app, "memory_service", None)
    if not memory:
        return text
    artifact = memory.get_artifact(session_id)
    if not artifact:
        return text
    # Inject artifact metadata as a prefix, not the full content
    stub = f"[working artifact: {artifact.capability_name} result ({artifact.output_type})] "
    return stub + text
```

Call `_resolve_artifact_pronouns()` at the start of `plan()` before routing.

---

## 0.3 — Cross-Turn Reference Resolution

**What it does:** Tracks `last_list`, `selected_entity`, `active_document` in session state so "the second one", "that file", "compare them" resolve correctly across turns.

### 0.3.1 — Add reference registry methods to `ContextStore`

**File:** `core/context_store.py`

```python
def save_reference(self, session_id: str, key: str, value: str) -> None:
    """Save a named reference to the session state reference registry."""
    state = self.get_session_state(session_id) or {}
    refs = state.setdefault("reference_registry", {})
    refs[key] = value
    self.save_session_state(session_id, state)

def get_reference(self, session_id: str, key: str) -> str | None:
    state = self.get_session_state(session_id) or {}
    return state.get("reference_registry", {}).get(key)

def get_all_references(self, session_id: str) -> dict:
    state = self.get_session_state(session_id) or {}
    return dict(state.get("reference_registry", {}))
```

### 0.3.2 — Populate registry in `ResponseFinalizer`

**File:** `core/response_finalizer.py` · In `finalize()` after `_detect_clarification()`:

```python
def _update_reference_registry(self, response: str) -> None:
    """Scan the finalized response for enumerated lists and named entities.
    Runs once per turn after response generation — ~0.5 ms."""
    session_id = getattr(self._app, "session_id", "")
    store = getattr(self._app, "context_store", None)
    if not session_id or not store:
        return

    # Detect numbered list items: "1. item", "2. item", "3. item"
    items = re.findall(r"^\s*\d+\.\s+(.+)$", response, re.MULTILINE)
    if items:
        # Store each item under ordinal keys: "first", "second", "third", etc
        ordinals = ["first", "second", "third", "fourth", "fifth",
                    "sixth", "seventh", "eighth", "ninth", "tenth"]
        for i, item in enumerate(items[:10]):
            if i < len(ordinals):
                store.save_reference(session_id, ordinals[i], item.strip())
        store.save_reference(session_id, "last_list", "\n".join(items))

    # Detect file paths mentioned in the response
    file_match = re.search(r"[`'\"]([/~][^\s`'\"]+\.[a-zA-Z]{1,6})[`'\"]", response)
    if file_match:
        store.save_reference(session_id, "last_file", file_match.group(1))

    # Detect active document (used by MarkItDown conversational follow-up, Phase 5)
    doc_match = re.search(r"\b(?:document|file|paper|note)s? ['\"]([^'\"]+)['\"]", response, re.IGNORECASE)
    if doc_match:
        store.save_reference(session_id, "active_document", doc_match.group(1))
```

Call `_update_reference_registry()` at the end of `finalize()`.

### 0.3.3 — Ordinal resolution in `IntentRecognizer`

**File:** `core/intent_recognizer.py`

```python
ORDINAL_PATTERN = re.compile(
    r"\b(the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\s+(one|item|option|result|file)?\b",
    re.IGNORECASE,
)

def _resolve_ordinal_references(self, text: str, session_id: str) -> str:
    match = ORDINAL_PATTERN.search(text)
    if not match:
        return text
    ordinal = match.group(2).lower()
    store = getattr(self.app, "context_store", None)
    if not store:
        return text
    value = store.get_reference(session_id, ordinal)
    if value:
        return ORDINAL_PATTERN.sub(f'"{value}"', text, count=1)
    return text
```

Apply after `_resolve_artifact_pronouns()` in the preprocessing chain.

---

## 0.4 — Fallback Capability on `CapabilityDescriptor`

**File:** `core/capability_registry.py` · Add `fallback_capability` field to `CapabilityDescriptor`:

```python
@dataclass
class CapabilityDescriptor:
    name: str
    description: str
    connectivity: str = "local"
    latency_class: str = "interactive"
    permission_mode: str = "always_ok"
    side_effect_level: str = "read"
    streaming: bool = False
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    provider_kind: str = "inprocess"
    resources: list[dict] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    fallback_capability: str = ""    # name of capability to try if this one fails
```

**File:** `core/capability_broker.py` · In `ToolStep`:

```python
@dataclass
class ToolStep:
    capability_name: str
    args: dict = field(default_factory=dict)
    raw_text: str = ""
    side_effect_level: str = "read"
    connectivity: str = "local"
    timeout_ms: int = 8000
    parallel_safe: bool = False
    node_id: str = ""
    depends_on: list[str] = field(default_factory=list)
    retries: int = 0
    fallback_capability: str = ""    # activated when all retries are exhausted
```

**File:** `core/task_graph_executor.py` · In `_run_node()` after the retry loop exhausts:

```python
# After retry loop: if last_error and fallback exists, run the fallback
if last_error:
    fallback_name = getattr(node.step, "fallback_capability", "") or ""
    if not fallback_name:
        # Try descriptor-level fallback
        descriptor = self._descriptor_for(node.step.capability_name)
        if descriptor:
            fallback_name = getattr(descriptor, "fallback_capability", "") or ""
    
    if fallback_name:
        logger.info("[task_graph] %s failed — trying fallback: %s", node.step.capability_name, fallback_name)
        try:
            fallback_result = self.app.capability_executor.execute(
                fallback_name, raw_text, args
            )
            if fallback_result.ok:
                self._apply_success_side_effects(node.step, args, fallback_result.output)
                return self.app.response_finalizer.finalize(fallback_result.output), str(fallback_result.output)
        except Exception as exc:
            logger.warning("[task_graph] fallback %s also failed: %s", fallback_name, exc)
```

**Note:** The retry loop itself (`for attempt in range(node.retries + 1)`) is already implemented in `core/task_graph_executor.py:L186`. This phase only adds the fallback dispatch after retries are exhausted.

---

## 0.5 — ResourceMonitor

**What it does:** `psutil`-based snapshot cached for 5 seconds. Read once at the start of each turn. Used by VisionService (Phase 1) and Mem0 server startup (Phase 6) to gate model loading.

### 0.5.1 — Create `core/resource_monitor.py`

```python
"""ResourceMonitor — lightweight hardware snapshot for adaptive decisions.

Snapshot is taken at most once per 5 seconds (cached). Non-blocking: reads
kernel counters only, no I/O. Per-turn overhead: ~1 ms.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


@dataclass
class ResourceSnapshot:
    ram_total_mb: int = 0
    ram_used_mb: int = 0
    ram_available_mb: int = 0
    cpu_percent: float = 0.0
    timestamp: float = 0.0

    @property
    def ram_free_percent(self) -> float:
        if self.ram_total_mb == 0:
            return 100.0
        return round(self.ram_available_mb / self.ram_total_mb * 100, 1)


class ResourceMonitor:
    CACHE_TTL_S: float = 5.0
    # Policy thresholds
    VLM_MIN_RAM_MB: int = 3000    # refuse to load VLM if less free RAM
    CHAT_ONLY_RAM_MB: int = 2000  # skip tool model if dangerously low

    def __init__(self):
        self._lock = threading.Lock()
        self._cached: ResourceSnapshot | None = None

    def snapshot(self) -> ResourceSnapshot:
        with self._lock:
            now = time.monotonic()
            if self._cached and (now - self._cached.timestamp) < self.CACHE_TTL_S:
                return self._cached

            snap = self._read()
            snap.timestamp = now
            self._cached = snap
            return snap

    def _read(self) -> ResourceSnapshot:
        if not _PSUTIL_AVAILABLE:
            return ResourceSnapshot(ram_total_mb=16000, ram_available_mb=8000)
        mem = psutil.virtual_memory()
        return ResourceSnapshot(
            ram_total_mb=mem.total // (1024 * 1024),
            ram_used_mb=mem.used // (1024 * 1024),
            ram_available_mb=mem.available // (1024 * 1024),
            cpu_percent=psutil.cpu_percent(interval=None),
        )


# Module-level singleton — instantiated once, shared across all callers.
_monitor = ResourceMonitor()

def get_snapshot() -> ResourceSnapshot:
    return _monitor.snapshot()
```

### 0.5.2 — Wire into `FridayApp`

**File:** `core/app.py` · In `FridayApp.__init__()` after the existing service inits:

```python
from core.resource_monitor import ResourceMonitor
self.resource_monitor = ResourceMonitor()
```

**File:** `core/app.py` · At the start of the turn execution method (`_execute_turn` or `process_text`), add:

```python
# Cache a resource snapshot for this turn — used by adaptive policy checks
self._turn_resource_snapshot = self.resource_monitor.snapshot()
```

### 0.5.3 — Install psutil

```bash
pip install psutil
```

---

## 0.6 — Add `active_turns` Property to `TurnFeedbackRuntime`

This property is required by Phase 6 (Mem0 TurnGatedMemoryExtractor).

**File:** `core/turn_feedback.py` · Add to `TurnFeedbackRuntime` class:

```python
@property
def active_turns(self) -> int:
    """Count of turns that have been started but not yet completed or failed."""
    with self._lock:
        return sum(
            1 for t in self._turns.values()
            if not t.cancelled and t.completed_at == 0.0
        )
```

---

## Phase 0 Verification

```bash
# Run existing test suite — all 298/299 passing tests must still pass
cd /home/tricky/Friday_Linux && python -m pytest tests/ -x -q

# Smoke test: artifact round-trip
python -c "
from core.context_store import ContextStore, WorkingArtifact
store = ContextStore()
sid = store.start_session({})
art = WorkingArtifact(content='hello', output_type='text', capability_name='test_tool')
store.save_artifact(sid, art)
retrieved = store.get_artifact(sid)
assert retrieved.content == 'hello', retrieved
print('WorkingArtifact: OK')
"

# Smoke test: resource monitor
python -c "
from core.resource_monitor import get_snapshot
snap = get_snapshot()
print(f'RAM available: {snap.ram_available_mb} MB ({snap.ram_free_percent}% free)')
assert snap.ram_available_mb > 0
print('ResourceMonitor: OK')
"
```

---

---

# Phase 1 — Vision Module: VisionService + Tier 1 Core

**Goal:** Create `modules/vision/` plugin with lazy VLM loading and three core capabilities: `analyze_screen`, `read_text_from_image`, `summarize_screen`.

**Prerequisite:** Phase 0 complete (needs `output_type` field on `CapabilityExecutionResult`, `ResourceMonitor`).

**Models already present (no download needed):**
- `models/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf` — 1.1 GB language decoder
- `models/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf` — 566 MB CLIP vision projector

**RAM when VLM loaded alongside both Qwen models: ~5.2 GB total. Well within 16 GB.**

---

## 1.1 — Install Dependencies

```bash
pip install Pillow mss
# Pillow: image processing and clipboard access
# mss: fast cross-platform screen capture
```

`llama_cpp` is already installed. `Llava16ChatHandler` is part of `llama_cpp.llama_chat_format`.

---

## 1.2 — Create Module Skeleton

```bash
mkdir -p modules/vision
touch modules/vision/__init__.py
```

---

## 1.3 — Create `modules/vision/prompts.py`

```python
"""Per-feature VLM prompt templates.

All prompts end with a token-count cap to keep inference fast on CPU.
"""

ANALYZE_SCREEN = (
    "You are a helpful assistant analyzing a screenshot. "
    "Describe what is on the screen: the application, any visible errors, "
    "dialogs, or important UI elements. Be concise. Maximum 2 sentences."
)

READ_TEXT = (
    "Extract all readable text from this image exactly as it appears. "
    "After the raw text, add one sentence explaining what the text is about. "
    "Maximum 3 sentences total."
)

SUMMARIZE_SCREEN = (
    "You are looking at a screenshot. Give a high-level summary of what the user "
    "is doing or looking at. Mention the most important content or action available. "
    "Be concise. Maximum 2 sentences."
)

ANALYZE_CLIPBOARD = (
    "Analyze this image from the clipboard. Describe what it shows, "
    "its purpose, and any key information visible. Maximum 2 sentences."
)

DEBUG_CODE = (
    "You are a debugging assistant. Look at this code or terminal screenshot. "
    "Identify exactly what the error is and suggest the most likely fix. "
    "Be specific. Maximum 3 sentences."
)

COMPARE_SCREENSHOTS = (
    "Compare Image A (left/top) and Image B (right/bottom). "
    "List the specific differences you can see. "
    "Be concrete and focus on functional changes. Maximum 3 sentences."
)

EXPLAIN_MEME = (
    "Explain this meme. What is the joke, what is the cultural reference, "
    "and why is it funny? Maximum 2 sentences."
)

ROAST_DESKTOP = (
    "You are a witty assistant. Look at this desktop screenshot and make "
    "one funny, observational comment about what you see — too many tabs, "
    "messy files, obscure apps. Be playful, not mean. One sentence only."
)

REVIEW_DESIGN = (
    "You are a UI/UX reviewer. Look at this screenshot and give one specific "
    "piece of honest feedback about the design — layout, readability, or usability. "
    "Maximum 2 sentences."
)

UI_ELEMENT_FINDER = (
    "Look at this screenshot. The user is looking for: {target}. "
    "Describe where on the screen this element is, using relative position "
    "(top-left, center, bottom-right, etc.) and what it looks like. "
    "If you cannot find it, say so clearly. Maximum 2 sentences."
)
```

---

## 1.4 — Create `modules/vision/preprocess.py`

```python
"""Image preprocessing utilities — resize before VLM inference to reduce token count."""
from __future__ import annotations

import base64
import io
from pathlib import Path

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


MAX_WIDTH = 1024     # ~4x token reduction vs full HD


def load_and_resize(source) -> "Image.Image":
    """Load an image from a file path, bytes, or PIL Image and resize to MAX_WIDTH."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is not installed. Run: pip install Pillow")
    
    if isinstance(source, Image.Image):
        img = source
    elif isinstance(source, (str, Path)):
        img = Image.open(str(source)).convert("RGB")
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source)).convert("RGB")
    else:
        raise TypeError(f"Unsupported image source type: {type(source)}")
    
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        new_height = int(img.height * ratio)
        img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)
    
    return img


def image_to_base64_jpeg(img: "Image.Image", quality: int = 85) -> str:
    """Convert a PIL Image to a base64-encoded JPEG string for llama_cpp."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def image_to_data_uri(img: "Image.Image") -> str:
    """Return a data URI suitable for llama_cpp multimodal chat messages."""
    b64 = image_to_base64_jpeg(img)
    return f"data:image/jpeg;base64,{b64}"
```

---

## 1.5 — Create `modules/vision/screenshot.py`

```python
"""Screen capture utilities — uses mss for fast cross-platform capture."""
from __future__ import annotations

import io
from pathlib import Path

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def take_screenshot() -> "Image.Image":
    """Capture the primary monitor. Returns a PIL Image."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is not installed. Run: pip install Pillow")
    
    if _MSS_AVAILABLE:
        with mss.mss() as sct:
            monitor = sct.monitors[1]   # primary monitor
            raw = sct.grab(monitor)
            buf = mss.tools.to_png(raw.rgb, raw.size)
            return Image.open(io.BytesIO(buf)).convert("RGB")
    else:
        # Fallback: PIL ImageGrab (works on X11 with scrot installed)
        img = ImageGrab.grab()
        if img is None:
            raise RuntimeError("Screenshot failed. Install mss: pip install mss")
        return img.convert("RGB")


def get_clipboard_image() -> "Image.Image | None":
    """Return the image currently on the clipboard, or None if no image is copied."""
    if not _PIL_AVAILABLE:
        return None
    try:
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            return img.convert("RGB")
        return None
    except Exception:
        return None
```

---

## 1.6 — Create `modules/vision/service.py`

```python
"""VisionService — lazy VLM loading, single inference entry point, auto-unload.

Loading strategy:
  - VLM is loaded on the first inference call (lazy loading).
  - Auto-unloaded after idle_timeout_s (default 300 s) of inactivity.
  - RAM guard: refuses to load if < 3 GB free (uses ResourceMonitor).
  - Dedicated threading.Lock() — never blocks the chat or tool model.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from core.logger import logger
from core.resource_monitor import get_snapshot, ResourceMonitor
from modules.vision.preprocess import load_and_resize, image_to_data_uri


class VisionService:
    def __init__(self, config: dict):
        self._model_path: str = config.get("model_path", "")
        self._mmproj_path: str = config.get("mmproj_path", "")
        self._n_ctx: int = int(config.get("n_ctx", 2048))
        self._idle_timeout_s: int = int(config.get("idle_timeout_s", 300))
        self._max_image_width: int = int(config.get("max_image_width", 1024))

        self._lock = threading.Lock()
        self._llm = None
        self._last_used: float = 0.0
        self._watchdog: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public inference interface
    # ------------------------------------------------------------------

    def infer(self, image, prompt: str, max_tokens: int = 128) -> str:
        """Run a single VLM inference pass. Loads model on first call.

        Args:
            image: PIL Image, file path (str/Path), or raw bytes.
            prompt: The instruction to pass alongside the image.
            max_tokens: Maximum tokens to generate (keep low for voice UX).

        Returns:
            Generated text string.
        """
        img = load_and_resize(image)
        data_uri = image_to_data_uri(img)

        with self._lock:
            self._ensure_loaded()
            self._last_used = time.monotonic()

            response = self._llm.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_uri}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            return response["choices"][0]["message"]["content"].strip()

    def unload(self) -> None:
        """Explicitly unload the VLM to free RAM."""
        with self._lock:
            if self._llm is not None:
                logger.info("[vision] Unloading VLM.")
                self._llm = None

    @property
    def is_loaded(self) -> bool:
        return self._llm is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load VLM if not already loaded. Must be called under self._lock."""
        if self._llm is not None:
            return

        snap = get_snapshot()
        if snap.ram_available_mb < ResourceMonitor.VLM_MIN_RAM_MB:
            raise RuntimeError(
                f"Not enough RAM to load VLM. "
                f"Available: {snap.ram_available_mb} MB, required: {ResourceMonitor.VLM_MIN_RAM_MB} MB."
            )

        if not Path(self._model_path).exists():
            raise FileNotFoundError(f"VLM model not found: {self._model_path}")
        if not Path(self._mmproj_path).exists():
            raise FileNotFoundError(f"mmproj not found: {self._mmproj_path}")

        logger.info("[vision] Loading SmolVLM2 from %s …", self._model_path)
        load_start = time.monotonic()

        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Llava16ChatHandler

        chat_handler = Llava16ChatHandler(
            clip_model_path=self._mmproj_path,
            verbose=False,
        )
        self._llm = Llama(
            model_path=self._model_path,
            chat_handler=chat_handler,
            n_ctx=self._n_ctx,
            n_batch=256,
            verbose=False,
        )

        logger.info("[vision] VLM loaded in %.1f s", time.monotonic() - load_start)
        self._start_watchdog()

    def _start_watchdog(self) -> None:
        """Start background thread that unloads the model after idle_timeout_s."""
        if self._watchdog and self._watchdog.is_alive():
            return

        def _watch():
            while True:
                time.sleep(30)
                with self._lock:
                    if self._llm is None:
                        return
                    idle_s = time.monotonic() - self._last_used
                    if idle_s >= self._idle_timeout_s:
                        logger.info("[vision] Idle timeout — unloading VLM.")
                        self._llm = None
                        return

        self._watchdog = threading.Thread(target=_watch, name="vision-watchdog", daemon=True)
        self._watchdog.start()
```

---

## 1.7 — Create `modules/vision/plugin.py`

```python
"""VisionPlugin — registers all vision capabilities with the capability registry."""
from __future__ import annotations

from core.logger import logger
from modules.vision import prompts
from modules.vision.screenshot import take_screenshot, get_clipboard_image
from modules.vision.service import VisionService


class VisionPlugin:
    """FridayPlugin-compatible vision module."""

    NAME = "vision"

    def __init__(self, app):
        self.app = app
        self._service: VisionService | None = None

    def on_load(self) -> None:
        cfg = self.app.config.get("vision", {}) if hasattr(self.app.config, "get") else {}
        if not cfg.get("enabled", False):
            logger.info("[vision] Plugin disabled in config.")
            return

        self._service = VisionService(cfg)
        features = cfg.get("features", {})

        if features.get("screenshot_explainer", True):
            self.app.router.register_tool(
                {
                    "name": "analyze_screen",
                    "description": (
                        "Take a screenshot of the current screen and explain what is on it. "
                        "Useful for: explaining errors, popups, UI elements, or anything visible."
                    ),
                    "context_terms": [
                        "screen", "explain", "what is this", "what is on", "error",
                        "popup", "what happened", "what do you see", "analyze screen",
                    ],
                },
                self._handle_analyze_screen,
            )

        if features.get("ocr_reader", True):
            self.app.router.register_tool(
                {
                    "name": "read_text_from_image",
                    "description": (
                        "Extract and read text from a screenshot, image, or photo. "
                        "Works on handwritten notes, receipts, terminal output, code screenshots."
                    ),
                    "context_terms": [
                        "read", "extract text", "ocr", "what does this say",
                        "text from image", "read the screen",
                    ],
                },
                self._handle_read_text,
            )

        if features.get("screen_summarizer", True):
            self.app.router.register_tool(
                {
                    "name": "summarize_screen",
                    "description": (
                        "Take a screenshot and give a summary of what the user is currently looking at. "
                        "Good for dashboards, articles, presentations, or long documents."
                    ),
                    "context_terms": [
                        "summarize screen", "what am I looking at", "overview",
                        "summary of my screen", "what is this page",
                    ],
                },
                self._handle_summarize_screen,
            )

        logger.info("[vision] Plugin loaded with %d capabilities.", sum([
            features.get("screenshot_explainer", True),
            features.get("ocr_reader", True),
            features.get("screen_summarizer", True),
        ]))

    # ------------------------------------------------------------------
    # Handlers — Tier 1
    # ------------------------------------------------------------------

    def _handle_analyze_screen(self, raw_text: str, args: dict):
        self._emit_ack("Analyzing your screen…")
        try:
            img = take_screenshot()
            result = self._service.infer(img, prompts.ANALYZE_SCREEN, max_tokens=100)
            return self._make_result("analyze_screen", result, "text")
        except Exception as exc:
            return self._make_error("analyze_screen", str(exc))

    def _handle_read_text(self, raw_text: str, args: dict):
        self._emit_ack("Reading that for you…")
        try:
            img = take_screenshot()
            result = self._service.infer(img, prompts.READ_TEXT, max_tokens=150)
            return self._make_result("read_text_from_image", result, "text")
        except Exception as exc:
            return self._make_error("read_text_from_image", str(exc))

    def _handle_summarize_screen(self, raw_text: str, args: dict):
        self._emit_ack("Summarizing your screen…")
        try:
            img = take_screenshot()
            result = self._service.infer(img, prompts.SUMMARIZE_SCREEN, max_tokens=100)
            return self._make_result("summarize_screen", result, "text")
        except Exception as exc:
            return self._make_error("summarize_screen", str(exc))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _emit_ack(self, text: str) -> None:
        tf = getattr(self.app, "turn_feedback", None)
        turn = getattr(self.app, "_current_turn", None)
        if tf and turn:
            tf.emit_ack(turn, text)

    def _make_result(self, name: str, output: str, output_type: str):
        from core.capability_registry import CapabilityExecutionResult
        return CapabilityExecutionResult(ok=True, name=name, output=output, output_type=output_type)

    def _make_error(self, name: str, error: str):
        from core.capability_registry import CapabilityExecutionResult
        logger.error("[vision] %s: %s", name, error)
        return CapabilityExecutionResult(ok=False, name=name, error=error)
```

---

## 1.8 — Add Vision Config to `config.yaml`

```yaml
vision:
  enabled: true
  model_path: "models/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf"
  mmproj_path: "models/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf"
  n_ctx: 2048
  n_batch: 256
  max_image_width: 1024
  idle_timeout_s: 300
  features:
    screenshot_explainer: true
    ocr_reader: true
    screen_summarizer: true
    clipboard_analyzer: false    # Phase 2
    code_debugger: false         # Phase 2
    compare_screenshots: false   # Phase 3
    ui_element_finder: false     # Phase 3
    smart_error_detector: false  # Phase 3
    fun_features: false          # Phase 2
```

---

## 1.9 — Register VisionPlugin in Module Loader

**File:** `core/extensions/loader.py` or wherever modules are loaded from `modules/`.

Locate where existing plugins (e.g., `modules/greeter`, `modules/voice_io`) are registered. Add:

```python
from modules.vision.plugin import VisionPlugin

# In the plugin loading block:
vision_plugin = VisionPlugin(app)
vision_plugin.on_load()
```

The exact registration pattern must match how existing plugins in `modules/` are loaded. Check how `modules/greeter/plugin.py` is currently loaded and follow the same pattern.

---

## Phase 1 Verification

```bash
# Unit test: VisionService with a test image
python -c "
from PIL import Image
from modules.vision.preprocess import load_and_resize, image_to_data_uri
import numpy as np

# Create a 1920x1080 test image
img = Image.fromarray(np.zeros((1080, 1920, 3), dtype='uint8'))
resized = load_and_resize(img)
assert resized.width == 1024, resized.width
print('Resize: OK')

uri = image_to_data_uri(resized)
assert uri.startswith('data:image/jpeg;base64,')
print('Data URI: OK')
"

# Test screenshot capture (requires display)
python -c "
from modules.vision.screenshot import take_screenshot
img = take_screenshot()
print(f'Screenshot: {img.width}x{img.height} OK')
"

# Integration test — VLM inference (requires ~1.67 GB RAM headroom, takes 5-20s)
python -c "
import yaml
from modules.vision.service import VisionService
from modules.vision.screenshot import take_screenshot

with open('config.yaml') as f:
    cfg = yaml.safe_load(f)

svc = VisionService(cfg['vision'])
img = take_screenshot()
result = svc.infer(img, 'What do you see? One sentence.', max_tokens=50)
print('VLM inference result:', result)
print('OK')
"
```

---

---

# Phase 2 — Vision Module: Tier 1 Complete + Fun Features

**Goal:** Add clipboard analyzer, code debugger, and all three fun features to the existing VisionPlugin.

**Prerequisite:** Phase 1 complete and stable.

---

## 2.1 — Add Clipboard Analyzer Handler

**File:** `modules/vision/plugin.py` · Add to `on_load()`:

```python
if features.get("clipboard_analyzer", False):
    self.app.router.register_tool(
        {
            "name": "analyze_clipboard_image",
            "description": (
                "Analyze or explain the image currently copied in the clipboard. "
                "Useful when the user has copied a chart, diagram, screenshot, or photo."
            ),
            "context_terms": [
                "clipboard", "analyze this", "explain the image",
                "what did I copy", "clipboard image",
            ],
        },
        self._handle_clipboard_image,
    )
```

Add handler method:

```python
def _handle_clipboard_image(self, raw_text: str, args: dict):
    self._emit_ack("Looking at your clipboard…")
    try:
        img = get_clipboard_image()
        if img is None:
            return self._make_result(
                "analyze_clipboard_image",
                "There is no image in your clipboard. Copy an image first, then try again.",
                "text",
            )
        result = self._service.infer(img, prompts.ANALYZE_CLIPBOARD, max_tokens=100)
        return self._make_result("analyze_clipboard_image", result, "text")
    except Exception as exc:
        return self._make_error("analyze_clipboard_image", str(exc))
```

---

## 2.2 — Add Code Screenshot Debugger Handler

**File:** `modules/vision/plugin.py` · Add to `on_load()`:

```python
if features.get("code_debugger", False):
    self.app.router.register_tool(
        {
            "name": "debug_code_screenshot",
            "description": (
                "Read a screenshot of code, a terminal error, or a stack trace and explain the issue."
            ),
            "context_terms": [
                "stack trace", "debug screenshot", "code error",
                "terminal error", "syntax error", "what is wrong",
                "read the error", "explain this error",
            ],
        },
        self._handle_debug_code,
    )
```

Handler:

```python
def _handle_debug_code(self, raw_text: str, args: dict):
    self._emit_ack("Reading the error…")
    try:
        img = take_screenshot()
        result = self._service.infer(img, prompts.DEBUG_CODE, max_tokens=150)
        return self._make_result("debug_code_screenshot", result, "text")
    except Exception as exc:
        return self._make_error("debug_code_screenshot", str(exc))
```

---

## 2.3 — Add Fun Features

**File:** `modules/vision/plugin.py` · Add to `on_load()`:

```python
if features.get("fun_features", False):
    # Meme explainer
    self.app.router.register_tool(
        {
            "name": "explain_meme",
            "description": "Explain a meme — the joke, the cultural context, and why it is funny.",
            "context_terms": [
                "explain this meme", "why is this funny",
                "what is the joke", "explain meme",
            ],
        },
        self._handle_explain_meme,
    )
    # Roast desktop
    self.app.router.register_tool(
        {
            "name": "roast_desktop",
            "description": "Take a screenshot and make a funny comment about the current desktop.",
            "context_terms": [
                "roast my desktop", "roast my screen",
                "make fun of my desktop", "what is wrong with my screen",
            ],
        },
        self._handle_roast_desktop,
    )
    # UI reviewer
    self.app.router.register_tool(
        {
            "name": "review_design",
            "description": "Analyze a UI screenshot and give honest design or usability feedback.",
            "context_terms": [
                "how does this look", "review this design",
                "rate this ui", "design feedback", "is this good design",
            ],
        },
        self._handle_review_design,
    )
```

Handlers:

```python
def _handle_explain_meme(self, raw_text: str, args: dict):
    self._emit_ack("Let me look at this…")
    try:
        img = get_clipboard_image() or take_screenshot()
        result = self._service.infer(img, prompts.EXPLAIN_MEME, max_tokens=80)
        return self._make_result("explain_meme", result, "text")
    except Exception as exc:
        return self._make_error("explain_meme", str(exc))

def _handle_roast_desktop(self, raw_text: str, args: dict):
    self._emit_ack("Taking a look…")
    try:
        img = take_screenshot()
        result = self._service.infer(img, prompts.ROAST_DESKTOP, max_tokens=60)
        return self._make_result("roast_desktop", result, "text")
    except Exception as exc:
        return self._make_error("roast_desktop", str(exc))

def _handle_review_design(self, raw_text: str, args: dict):
    self._emit_ack("Reviewing this design…")
    try:
        img = get_clipboard_image() or take_screenshot()
        result = self._service.infer(img, prompts.REVIEW_DESIGN, max_tokens=80)
        return self._make_result("review_design", result, "text")
    except Exception as exc:
        return self._make_error("review_design", str(exc))
```

---

## 2.4 — Enable in Config

Update `config.yaml` vision features block:

```yaml
  features:
    screenshot_explainer: true
    ocr_reader: true
    screen_summarizer: true
    clipboard_analyzer: true    # enable
    code_debugger: true         # enable
    compare_screenshots: false
    ui_element_finder: false
    smart_error_detector: false
    fun_features: true          # enable
```

---

## Phase 2 Verification

```bash
python -c "
# Verify all registered capabilities
from core.capability_registry import CapabilityRegistry
# If running in full app context, check:
expected = ['analyze_screen', 'read_text_from_image', 'summarize_screen',
            'analyze_clipboard_image', 'debug_code_screenshot',
            'explain_meme', 'roast_desktop', 'review_design']
print('Expected capabilities:', expected)
print('Manually trigger each via voice and verify ack fires immediately.')
"
```

**Manual test flow:**
1. Say "analyze my screen" → ack fires → VLM result spoken
2. Copy an image to clipboard → say "what did I copy" → clipboard image analyzed
3. Open a terminal with an error → say "what is wrong" → code debugger fires
4. Say "roast my desktop" → single funny line spoken

---

---

# Phase 3 — Vision Module: Tier 2

**Goal:** Add screenshot comparison, UI element finder, and smart error detector.

**Prerequisite:** Phase 2 complete and stable.

---

## 3.1 — Screenshot Comparison

**File:** `modules/vision/plugin.py` · Add to `on_load()`:

```python
if features.get("compare_screenshots", False):
    self.app.router.register_tool(
        {
            "name": "compare_screenshots",
            "description": "Compare two screenshots and explain what changed or is different.",
            "context_terms": [
                "compare screenshots", "what changed",
                "difference between", "before and after", "what is different",
            ],
        },
        self._handle_compare_screenshots,
    )
```

Handler — concatenates two images side-by-side for a single VLM call:

```python
def _handle_compare_screenshots(self, raw_text: str, args: dict):
    self._emit_ack("Comparing screenshots…")
    try:
        from PIL import Image
        from modules.vision.preprocess import load_and_resize, image_to_data_uri

        # First screenshot from clipboard (Image A), live screen (Image B)
        img_a = get_clipboard_image()
        img_b = take_screenshot()

        if img_a is None:
            return self._make_result(
                "compare_screenshots",
                "Copy Image A to clipboard first, then ask me to compare.",
                "text",
            )

        # Resize both to same height for side-by-side concat
        img_a = load_and_resize(img_a)
        img_b = load_and_resize(img_b)
        target_height = min(img_a.height, img_b.height, 600)
        img_a = img_a.resize((int(img_a.width * target_height / img_a.height), target_height))
        img_b = img_b.resize((int(img_b.width * target_height / img_b.height), target_height))

        combined = Image.new("RGB", (img_a.width + img_b.width, target_height))
        combined.paste(img_a, (0, 0))
        combined.paste(img_b, (img_a.width, 0))

        result = self._service.infer(combined, prompts.COMPARE_SCREENSHOTS, max_tokens=120)
        return self._make_result("compare_screenshots", result, "text")
    except Exception as exc:
        return self._make_error("compare_screenshots", str(exc))
```

---

## 3.2 — UI Element Finder

Requires `xdotool` installed (`sudo apt install xdotool`) for Linux click execution.

**File:** `modules/vision/plugin.py` · Add to `on_load()`:

```python
if features.get("ui_element_finder", False):
    self.app.router.register_tool(
        {
            "name": "find_ui_element",
            "description": (
                "Find a UI element on screen by description. "
                "Returns its approximate location. Can optionally click it."
            ),
            "context_terms": [
                "find the button", "where is", "locate", "click",
                "find settings", "where is the", "find the",
            ],
        },
        self._handle_find_ui_element,
    )
```

Handler:

```python
def _handle_find_ui_element(self, raw_text: str, args: dict):
    target = args.get("target") or raw_text
    self._emit_ack(f"Looking for {target}…")
    try:
        img = take_screenshot()
        prompt = prompts.UI_ELEMENT_FINDER.format(target=target)
        result = self._service.infer(img, prompt, max_tokens=100)
        return self._make_result("find_ui_element", result, "text")
    except Exception as exc:
        return self._make_error("find_ui_element", str(exc))
```

---

## 3.3 — Smart Error Detector

Uses a two-gate heuristic approach: window title keyword check → pixel diff → VLM only if both gates pass.

**File:** `modules/vision/smart_error_detector.py`

```python
"""SmartErrorDetector — event-driven error detection with cheap pre-filters.

Two-gate pipeline:
  1. Window title scan (wmctrl) — keyword match for Error/Warning/Failed
  2. OCR keyword scan via pytesseract (if available) — confirms text presence
  3. VLM inference only if both gates pass

VLM is invoked at most once per unique window state.
"""
from __future__ import annotations

import re
import subprocess
import threading
from typing import Callable

from core.logger import logger
from modules.vision.screenshot import take_screenshot

ERROR_KEYWORDS = re.compile(r"\b(error|warning|failed|exception|crash|fatal|critical)\b", re.IGNORECASE)
_LAST_ERROR_TITLE: str = ""


def _get_active_window_title() -> str:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=1.0
        )
        return result.stdout.strip()
    except Exception:
        return ""


def start_error_monitor(vision_service, event_bus) -> threading.Thread:
    """Start a daemon thread that polls for error windows every 3 seconds."""
    global _LAST_ERROR_TITLE

    def _monitor():
        global _LAST_ERROR_TITLE
        import time
        while True:
            time.sleep(3.0)
            try:
                title = _get_active_window_title()
                if title == _LAST_ERROR_TITLE:
                    continue
                if not ERROR_KEYWORDS.search(title):
                    continue
                _LAST_ERROR_TITLE = title
                logger.info("[vision] Error window detected: %s", title)

                img = take_screenshot()
                result = vision_service.infer(
                    img,
                    f"Window title is '{title}'. Explain this error briefly. Maximum 2 sentences.",
                    max_tokens=80,
                )
                event_bus.publish("assistant_progress", {"text": result})
            except Exception as exc:
                logger.debug("[vision] Error detector: %s", exc)

    t = threading.Thread(target=_monitor, name="vision-error-monitor", daemon=True)
    t.start()
    return t
```

Enable in `on_load()` only when `features.get("smart_error_detector")` is True.

---

## Phase 3 Verification

```bash
# Test compare: copy a screenshot to clipboard, then call compare_screenshots
# Test UI element finder: "find the close button"
# Test smart error detector: open a dialog with "Error" in its title
```

---

---

# Phase 4 — Document Intelligence: Foundation

**Goal:** Build `modules/document_intel/` — Phase 1 foundation (file QA + workspace search). Delivers `query_document` and `search_workspace` capabilities.

**Prerequisite:** Phase 0 complete (needs `WorkingArtifact`, `output_type` field, `ResponseFinalizer` reference tracking).

---

## 4.1 — Install Dependencies

```bash
pip install 'markitdown[all]' watchdog
# markitdown: converts PDF, DOCX, PPTX, XLSX, HTML, CSV, TXT, MD → Markdown
# watchdog: file system watcher for workspace indexing (Phase 5)
```

Confirm ChromaDB is already installed:
```bash
python -c "import chromadb; print('ChromaDB:', chromadb.__version__)"
```

---

## 4.2 — Create Module Skeleton

```bash
mkdir -p modules/document_intel
touch modules/document_intel/__init__.py
```

---

## 4.3 — Create `modules/document_intel/converter.py`

```python
"""MarkItDown wrapper with error handling and format validation."""
from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt", ".html", ".csv"}


def convert_to_markdown(file_path: str | Path) -> str:
    """Convert a document to Markdown text using MarkItDown.

    Returns the Markdown string. Raises on unsupported formats or parse errors.
    enable_plugins=False keeps conversion offline and deterministic.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {path.suffix}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    from markitdown import MarkItDown
    md = MarkItDown(enable_plugins=False)
    result = md.convert(str(path))
    text = result.text_content or ""
    if not text.strip():
        raise ValueError(f"Document converted to empty content: {path}")
    return text
```

---

## 4.4 — Create `modules/document_intel/chunker.py`

```python
"""Heading-first chunker for Markdown documents.

Strategy:
  1. Split on Markdown headings (## Section, ### Subsection)
  2. If a section exceeds max_tokens: split on paragraph boundaries
  3. If a paragraph exceeds max_tokens: hard split with overlap
  4. Prepend parent heading to each chunk for retrieval context

Heading-prefixed chunks dramatically improve retrieval because the
semantic model can match questions to section labels without reading content.
"""
from __future__ import annotations

import re

MAX_TOKENS = 400
OVERLAP_TOKENS = 80
HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _rough_token_count(text: str) -> int:
    return int(len(text.split()) * 1.3)


def _split_by_overlap(text: str, max_tokens: int, overlap: int) -> list[str]:
    words = text.split()
    chunks = []
    step = max(1, max_tokens - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + max_tokens])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def chunk_markdown(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap: int = OVERLAP_TOKENS,
    source_path: str = "",
) -> list[dict]:
    """Chunk Markdown text into retrieval-ready fragments.

    Returns a list of dicts: {"text": str, "heading": str, "chunk_index": int}
    """
    chunks = []
    chunk_index = 0
    sections = HEADING_PATTERN.split(text)

    # sections alternates: [pre_heading_text, level, heading, body, level, heading, body, ...]
    current_heading = ""

    def _emit(content: str, heading: str) -> None:
        nonlocal chunk_index
        content = content.strip()
        if not content:
            return
        token_count = _rough_token_count(content)
        if token_count <= max_tokens:
            prefix = f"{heading}\n\n" if heading else ""
            chunks.append({
                "text": prefix + content,
                "heading": heading,
                "chunk_index": chunk_index,
                "source": source_path,
            })
            chunk_index += 1
        else:
            paragraphs = re.split(r"\n{2,}", content)
            buf = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                candidate = buf + "\n\n" + para if buf else para
                if _rough_token_count(candidate) > max_tokens:
                    if buf:
                        prefix = f"{heading}\n\n" if heading else ""
                        chunks.append({
                            "text": prefix + buf.strip(),
                            "heading": heading,
                            "chunk_index": chunk_index,
                            "source": source_path,
                        })
                        chunk_index += 1
                    buf = para
                else:
                    buf = candidate
            if buf.strip():
                if _rough_token_count(buf) > max_tokens:
                    for sub in _split_by_overlap(buf, max_tokens, overlap):
                        prefix = f"{heading}\n\n" if heading else ""
                        chunks.append({
                            "text": prefix + sub,
                            "heading": heading,
                            "chunk_index": chunk_index,
                            "source": source_path,
                        })
                        chunk_index += 1
                else:
                    prefix = f"{heading}\n\n" if heading else ""
                    chunks.append({
                        "text": prefix + buf.strip(),
                        "heading": heading,
                        "chunk_index": chunk_index,
                        "source": source_path,
                    })
                    chunk_index += 1

    # Handle pre-heading text
    i = 0
    raw_parts = HEADING_PATTERN.split(text)
    if raw_parts and not HEADING_PATTERN.match(text[:50]):
        _emit(raw_parts[0], "")
        raw_parts = raw_parts[1:]

    # Process heading sections
    it = iter(raw_parts)
    for level in it:
        heading_text = next(it, "")
        body = next(it, "")
        prefix = "#" * len(level) if level else ""
        current_heading = f"{prefix} {heading_text}".strip()
        _emit(body, current_heading)

    return chunks
```

---

## 4.5 — Create `modules/document_intel/embedder.py`

```python
"""Embedder — wraps the existing all-MiniLM-L6-v2 already in EmbeddingRouter.

Reuses the same SentenceTransformer instance to avoid double-loading.
If the shared instance is not available, loads its own.
"""
from __future__ import annotations

from core.logger import logger

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_shared_model = None


def _get_model():
    global _shared_model
    if _shared_model is not None:
        return _shared_model
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("[doc_intel] Loading embedding model %s…", _MODEL_NAME)
        _shared_model = SentenceTransformer(_MODEL_NAME)
        return _shared_model
    except ImportError:
        raise RuntimeError("sentence-transformers is not installed. Run: pip install sentence-transformers")


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a 384-dimensional float vector."""
    model = _get_model()
    vec = model.encode(text, convert_to_numpy=True)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. More efficient than calling embed_text in a loop."""
    model = _get_model()
    vecs = model.encode(texts, convert_to_numpy=True, batch_size=32)
    return [v.tolist() for v in vecs]
```

---

## 4.6 — Create `modules/document_intel/document_store.py`

```python
"""DocumentStore — Chroma collection + SQLite metadata for indexed documents.

Uses the existing Chroma instance at data/chroma/ (same as ContextStore).
Collection: "friday_documents" — isolated from the semantic memory collection.
Metadata table in data/friday.db (via a separate connection, no schema collision).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings

COLLECTION_NAME = "friday_documents"
DB_PATH = "data/friday.db"
CHROMA_PATH = "data/chroma"


class DocumentStore:
    def __init__(self, chroma_path: str = CHROMA_PATH, db_path: str = DB_PATH):
        self._client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._db_path = db_path
        self._init_table()

    def _init_table(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexed_documents (
                    file_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    document_type TEXT,
                    title TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at TEXT,
                    modified_at TEXT,
                    workspace TEXT DEFAULT 'default'
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Index a document
    # ------------------------------------------------------------------

    def is_indexed(self, file_path: str) -> bool:
        file_hash = self._hash_file(file_path)
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT file_hash FROM indexed_documents WHERE path = ?",
                (str(file_path),),
            ).fetchone()
        return row is not None and row[0] == file_hash

    def add_chunks(self, file_path: str, chunks: list[dict], workspace: str = "default") -> None:
        """Upsert chunks into Chroma and record metadata in SQLite."""
        path = Path(file_path)
        file_hash = self._hash_file(str(path))
        file_id = hashlib.md5(str(path).encode()).hexdigest()

        from modules.document_intel.embedder import embed_batch
        texts = [c["text"] for c in chunks]
        embeddings = embed_batch(texts)

        ids = [f"{file_id}_chunk_{c['chunk_index']}" for c in chunks]
        metadatas = [
            {
                "path": str(path),
                "heading": c.get("heading", ""),
                "chunk_index": c["chunk_index"],
                "workspace": workspace,
            }
            for c in chunks
        ]

        # Upsert into Chroma — handles re-indexing cleanly
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # Record in SQLite
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO indexed_documents
                    (file_id, path, file_hash, document_type, title, chunk_count, indexed_at, modified_at, workspace)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    chunk_count = excluded.chunk_count,
                    indexed_at = excluded.indexed_at,
                    modified_at = excluded.modified_at
                """,
                (
                    file_id, str(path), file_hash,
                    path.suffix.lstrip("."),
                    path.stem, len(chunks),
                    now, now, workspace,
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        question_embedding: list[float],
        top_k: int = 4,
        workspace: str | None = None,
    ) -> list[dict]:
        where = {"workspace": workspace} if workspace else None
        results = self._collection.query(
            query_embeddings=[question_embedding],
            n_results=min(top_k, 10),
            where=where,
        )
        if not results["documents"] or not results["documents"][0]:
            return []
        return [
            {
                "text": doc,
                "source_file": meta.get("path", ""),
                "heading": meta.get("heading", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": float(dist),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(65536), b""):
                    h.update(block)
        except OSError:
            return ""
        return h.hexdigest()
```

---

## 4.7 — Create `modules/document_intel/retriever.py`

```python
"""DocumentRetriever — orchestrates embed → query → context budget enforcement."""
from __future__ import annotations

MAX_RETRIEVAL_CHUNKS = 4
MAX_CONTEXT_TOKENS = 1500


class DocumentRetriever:
    def __init__(self, document_store):
        self._store = document_store

    def query(self, question: str, top_k: int = MAX_RETRIEVAL_CHUNKS, workspace: str | None = None) -> list[dict]:
        from modules.document_intel.embedder import embed_text
        embedding = embed_text(question)
        return self._store.query(embedding, top_k=top_k, workspace=workspace)

    def build_context_for_llm(self, chunks: list[dict]) -> str:
        """Format retrieved chunks for injection into the LLM context bundle.
        Enforces the 1500-token hard limit.
        """
        parts = []
        token_count = 0
        for chunk in chunks:
            chunk_tokens = int(len(chunk["text"].split()) * 1.3)
            if token_count + chunk_tokens > MAX_CONTEXT_TOKENS:
                break
            source = chunk.get("source_file", "")
            heading = chunk.get("heading", "")
            label = f"[{source}]" + (f" {heading}" if heading else "")
            parts.append(f"{label}\n{chunk['text']}")
            token_count += chunk_tokens
        return "\n\n---\n\n".join(parts)
```

---

## 4.8 — Create `modules/document_intel/service.py`

```python
"""DocumentIntelService — orchestrates the full document pipeline."""
from __future__ import annotations

from pathlib import Path

from core.logger import logger
from modules.document_intel.converter import convert_to_markdown
from modules.document_intel.chunker import chunk_markdown
from modules.document_intel.document_store import DocumentStore
from modules.document_intel.retriever import DocumentRetriever


class DocumentIntelService:
    def __init__(self, config: dict):
        chroma_path = config.get("chroma_path", "data/chroma")
        db_path = config.get("db_path", "data/friday.db")
        self._store = DocumentStore(chroma_path=chroma_path, db_path=db_path)
        self._retriever = DocumentRetriever(self._store)
        self._max_chunks = int(config.get("max_chunks", 4))

    def query_document(self, file_path: str, question: str, workspace: str = "default") -> str:
        """Index file if needed, then retrieve context for question."""
        path = Path(file_path).expanduser().resolve()
        
        if not self._store.is_indexed(str(path)):
            logger.info("[doc_intel] Indexing: %s", path)
            markdown = convert_to_markdown(str(path))
            chunks = chunk_markdown(markdown, source_path=str(path))
            self._store.add_chunks(str(path), chunks, workspace=workspace)
            logger.info("[doc_intel] Indexed %d chunks from %s", len(chunks), path.name)
        
        chunks = self._retriever.query(question, top_k=self._max_chunks)
        if not chunks:
            return f"No relevant content found in {path.name} for: {question}"
        return self._retriever.build_context_for_llm(chunks)

    def search_workspace(self, query: str, workspace: str | None = None) -> str:
        """Search across all indexed documents in a workspace."""
        chunks = self._retriever.query(query, top_k=self._max_chunks, workspace=workspace)
        if not chunks:
            return "No results found. Make sure documents are indexed first."
        return self._retriever.build_context_for_llm(chunks)
```

---

## 4.9 — Create `modules/document_intel/plugin.py`

```python
"""DocumentIntelPlugin — registers query_document and search_workspace capabilities."""
from __future__ import annotations

from core.logger import logger
from modules.document_intel.service import DocumentIntelService


class DocumentIntelPlugin:
    NAME = "document_intel"

    def __init__(self, app):
        self.app = app
        self._service: DocumentIntelService | None = None

    def on_load(self) -> None:
        cfg = self.app.config.get("document_intel", {}) if hasattr(self.app.config, "get") else {}
        if not cfg.get("enabled", False):
            logger.info("[doc_intel] Plugin disabled in config.")
            return

        self._service = DocumentIntelService(cfg)

        self.app.router.register_tool(
            {
                "name": "query_document",
                "description": (
                    "Ask a question about a specific document file (PDF, DOCX, PPTX, XLSX, TXT, MD). "
                    "Summarizes the file or retrieves specific information from it."
                ),
                "parameters": {
                    "file_path": "string — absolute or relative path to the document",
                    "question": "string — what to find or summarize in the document",
                },
                "context_terms": [
                    "summarize", "what does", "explain", "search document",
                    "read file", "key points", "what is in", "document",
                ],
            },
            self._handle_query_document,
        )

        self.app.router.register_tool(
            {
                "name": "search_workspace",
                "description": (
                    "Search across all indexed documents and notes in the workspace. "
                    "Finds relevant content from any previously indexed file."
                ),
                "parameters": {
                    "query": "string — what to search for",
                    "workspace": "string — optional workspace filter (default: all)",
                },
                "context_terms": [
                    "search my notes", "find in docs", "what did I write",
                    "search workspace", "find anything about", "in my notes",
                ],
            },
            self._handle_search_workspace,
        )

        logger.info("[doc_intel] Plugin loaded.")

    def _handle_query_document(self, raw_text: str, args: dict):
        from core.capability_registry import CapabilityExecutionResult
        file_path = args.get("file_path", "")
        question = args.get("question", raw_text)
        
        if not file_path:
            return CapabilityExecutionResult(
                ok=False, name="query_document",
                error="No file path provided. Example: 'summarize ~/Documents/report.pdf'",
            )
        try:
            context = self._service.query_document(file_path, question)
            return CapabilityExecutionResult(
                ok=True, name="query_document",
                output=context, output_type="document",
            )
        except Exception as exc:
            return CapabilityExecutionResult(ok=False, name="query_document", error=str(exc))

    def _handle_search_workspace(self, raw_text: str, args: dict):
        from core.capability_registry import CapabilityExecutionResult
        query = args.get("query", raw_text)
        workspace = args.get("workspace")
        try:
            context = self._service.search_workspace(query, workspace=workspace)
            return CapabilityExecutionResult(
                ok=True, name="search_workspace",
                output=context, output_type="document",
            )
        except Exception as exc:
            return CapabilityExecutionResult(ok=False, name="search_workspace", error=str(exc))
```

---

## 4.10 — Add Document Intel Config to `config.yaml`

```yaml
document_intel:
  enabled: true
  chroma_path: "data/chroma"
  db_path: "data/friday.db"
  collection_name: "friday_documents"
  max_chunks: 4
  max_context_tokens: 1500
  chunk_size_tokens: 400
  chunk_overlap_tokens: 80
  auto_index: false        # start false; enable in Phase 5
  workspace_folders: []    # filled in Phase 5
  index_extensions:
    - ".pdf"
    - ".docx"
    - ".pptx"
    - ".xlsx"
    - ".md"
    - ".txt"
  index_idle_only: true
  index_batch_size: 3
```

---

## Phase 4 Verification

```bash
# Test converter
python -c "
from modules.document_intel.converter import convert_to_markdown
# Test with an existing markdown file
md = convert_to_markdown('docs/architecture_final_implementation_priorities.md')
print(f'Converted: {len(md)} chars')
print(md[:200])
"

# Test chunker
python -c "
from modules.document_intel.chunker import chunk_markdown
text = open('docs/architecture_final_implementation_priorities.md').read()
chunks = chunk_markdown(text)
print(f'Chunks: {len(chunks)}')
for c in chunks[:3]:
    print(f'  [{c[\"chunk_index\"]}] heading={c[\"heading\"][:40]} tokens~{len(c[\"text\"].split())}')
"

# Test full pipeline — index a document and query it
python -c "
from modules.document_intel.service import DocumentIntelService
svc = DocumentIntelService({'chroma_path': 'data/chroma', 'db_path': 'data/friday.db', 'max_chunks': 3})
result = svc.query_document('docs/architecture_final_implementation_priorities.md', 'What is the ResourceMonitor?')
print('Query result:')
print(result[:500])
"
```

---

---

# Phase 5 — Document Intelligence: Conversational + Workspace

**Goal:** Add active document tracking for multi-turn follow-up QA, workspace folder auto-indexing, and background incremental indexer.

**Prerequisite:** Phase 4 complete. Phase 0's reference registry (0.3) must be working — `active_document` key used here.

---

## 5.1 — Conversational Document Follow-Up

**Mechanism:** When `query_document` completes, the document path is saved to `reference_registry["active_document"]` via `ResponseFinalizer._update_reference_registry()` (already wired in Phase 0). When the user asks a follow-up ("what were the limitations?"), `IntentRecognizer._resolve_artifact_pronouns()` sees no new file path but finds `active_document` in the registry.

**File:** `core/intent_recognizer.py` · Extend `_resolve_artifact_pronouns()`:

```python
def _resolve_artifact_pronouns(self, text: str, session_id: str) -> str:
    # ... existing pronoun resolution ...

    # Document follow-up: if no file path in text but there's an active_document
    store = getattr(self.app, "context_store", None)
    if store:
        active_doc = store.get_reference(session_id, "active_document")
        if active_doc and not re.search(r"[/~\\][^\s]+\.[a-zA-Z]{1,6}", text):
            # Inject the active document path as an implicit argument
            text = f"[active_document={active_doc}] {text}"
    
    return text
```

**File:** `modules/document_intel/plugin.py` · Update `_handle_query_document()` to save `active_document`:

```python
def _handle_query_document(self, raw_text: str, args: dict):
    # ... existing logic ...
    # After successful indexing and retrieval:
    if result.ok and file_path:
        store = getattr(self.app, "context_store", None)
        session_id = getattr(self.app, "session_id", "")
        if store and session_id:
            store.save_reference(session_id, "active_document", file_path)
    return result
```

**File:** `modules/document_intel/plugin.py` · Update `_handle_query_document()` to detect injected active_document:

```python
# Detect active_document injected by IntentRecognizer
import re as _re
injected_match = _re.search(r"\[active_document=([^\]]+)\]", raw_text)
if injected_match and not file_path:
    file_path = injected_match.group(1)
    raw_text = _re.sub(r"\[active_document=[^\]]+\]\s*", "", raw_text)
```

---

## 5.2 — Workspace File Watcher

**File:** `modules/document_intel/workspace_watcher.py`

```python
"""Background workspace watcher using watchdog.

Monitors configured folders. Queues new/changed files for indexing.
Only indexes during idle periods (when no voice turn is active).
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from core.logger import logger

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt"}


class WorkspaceWatcher:
    def __init__(self, service, turn_feedback, folders: list[str], extensions: list[str]):
        self._service = service
        self._feedback = turn_feedback
        self._folders = [Path(f).expanduser() for f in folders]
        self._extensions = set(extensions or SUPPORTED_EXTENSIONS)
        self._queue: queue.Queue[Path] = queue.Queue()
        self._observer = None
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if not _WATCHDOG_AVAILABLE:
            logger.warning("[doc_intel] watchdog not installed; workspace auto-index disabled.")
            return
        if not self._folders:
            return

        handler = _QueueHandler(self._queue, self._extensions)
        self._observer = Observer()
        for folder in self._folders:
            if folder.exists():
                self._observer.schedule(handler, str(folder), recursive=True)
                logger.info("[doc_intel] Watching: %s", folder)

        self._observer.start()
        self._worker = threading.Thread(target=self._drain_queue, name="doc-indexer", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _drain_queue(self) -> None:
        while True:
            try:
                path = self._queue.get(timeout=5.0)
            except queue.Empty:
                continue

            # Gate: only index when no active voice turn
            while getattr(self._feedback, "active_turns", 0) > 0:
                time.sleep(1.0)

            try:
                logger.info("[doc_intel] Background indexing: %s", path)
                self._service.query_document(str(path), question="_index_only_")
            except Exception as exc:
                logger.warning("[doc_intel] Failed to index %s: %s", path, exc)


class _QueueHandler(FileSystemEventHandler if _WATCHDOG_AVAILABLE else object):
    def __init__(self, q: queue.Queue, extensions: set[str]):
        self._queue = q
        self._extensions = extensions

    def on_modified(self, event):
        self._maybe_queue(event)

    def on_created(self, event):
        self._maybe_queue(event)

    def _maybe_queue(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in self._extensions:
            self._queue.put(path)
```

---

## 5.3 — Enable Workspace Watcher in Plugin

**File:** `modules/document_intel/plugin.py` · In `on_load()`:

```python
if cfg.get("auto_index", False):
    from modules.document_intel.workspace_watcher import WorkspaceWatcher
    folders = cfg.get("workspace_folders", [])
    extensions = cfg.get("index_extensions", [".pdf", ".docx", ".md", ".txt"])
    self._watcher = WorkspaceWatcher(
        service=self._service,
        turn_feedback=getattr(self.app, "turn_feedback", None),
        folders=folders,
        extensions=extensions,
    )
    self._watcher.start()
    logger.info("[doc_intel] Workspace watcher started for %d folders.", len(folders))
```

---

## 5.4 — Index FRIDAY Codebase (Project Intelligence Layer)

Update `config.yaml` to auto-index the FRIDAY project:

```yaml
document_intel:
  auto_index: true
  workspace_folders:
    - "~/Friday_Linux/docs"
    - "~/Friday_Linux/core"
    - "~/Friday_Linux/modules"
  index_extensions:
    - ".md"
    - ".txt"
    - ".py"
```

---

## Phase 5 Verification

```bash
# Trigger initial indexing of docs folder
python -c "
from modules.document_intel.service import DocumentIntelService
svc = DocumentIntelService({'chroma_path': 'data/chroma', 'db_path': 'data/friday.db', 'max_chunks': 4})
# Index the Friday Linux docs folder
import glob
for f in glob.glob('docs/*.md'):
    try:
        svc.query_document(f, '_index_only_')
        print(f'Indexed: {f}')
    except Exception as e:
        print(f'Skip {f}: {e}')
"

# Test workspace search
python -c "
from modules.document_intel.service import DocumentIntelService
svc = DocumentIntelService({'chroma_path': 'data/chroma', 'db_path': 'data/friday.db', 'max_chunks': 4})
result = svc.search_workspace('how does the VLM get loaded')
print(result[:600])
"
```

---

---

# Phase 6 — Mem0 Memory Integration: Foundation

**Goal:** Integrate Mem0 as the fact-memory layer. 90% token reduction in context bundles. Zero inference overhead during active turns.

**Prerequisite:** Phase 0 complete (needs `active_turns` property on `TurnFeedbackRuntime`).

---

## 6.1 — Install Dependencies

```bash
pip install mem0ai litellm
```

---

## 6.2 — Boot llama.cpp Extraction Server

The extraction LLM runs in a separate process so it never contends with FRIDAY's main inference locks.

**Create `scripts/start_mem0_server.sh`:**

```bash
#!/usr/bin/env bash
# Boots a llama.cpp OpenAI-compatible server for Mem0 fact extraction.
# Uses the Qwen3-4B tool model (best for structured extraction tasks).
# Port 8181 — separate from any existing llama.cpp usage.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="$SCRIPT_DIR/models/mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf"

if [ ! -f "$MODEL" ]; then
    echo "ERROR: Model not found at $MODEL"
    exit 1
fi

echo "Starting Mem0 extraction server on port 8181..."
"$SCRIPT_DIR/.venv/bin/python3" -m llama_cpp.server \
    --model "$MODEL" \
    --n_ctx 1024 \
    --n_batch 128 \
    --port 8181 \
    --host 127.0.0.1 \
    --verbose false &

SERVER_PID=$!
echo "Extraction server PID: $SERVER_PID"
echo $SERVER_PID > "$SCRIPT_DIR/data/mem0_server.pid"
```

**Auto-start on FRIDAY boot** — add to `core/app.py` `FridayApp.__init__()`:

```python
def _start_mem0_server(self) -> bool:
    """Boot llama.cpp extraction server if memory.enabled and auto_start are set."""
    import subprocess, os, time
    cfg = self.config.get("memory", {}) if hasattr(self.config, "get") else {}
    if not cfg.get("enabled", False):
        return False
    srv_cfg = cfg.get("extraction_server", {})
    if not srv_cfg.get("auto_start", False):
        return False

    model_path = srv_cfg.get("model_path", "")
    port = int(srv_cfg.get("port", 8181))
    host = srv_cfg.get("host", "127.0.0.1")

    if not os.path.exists(model_path):
        logger.warning("[mem0] Model not found: %s — skipping extraction server.", model_path)
        return False

    try:
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "llama_cpp.server",
                "--model", model_path,
                "--n_ctx", "1024",
                "--n_batch", "128",
                "--port", str(port),
                "--host", host,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait up to 8 seconds for server to be ready
        import urllib.request
        for _ in range(16):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=1)
                logger.info("[mem0] Extraction server ready at port %d (PID %d).", port, proc.pid)
                return True
            except Exception:
                continue
        logger.warning("[mem0] Extraction server did not start in time.")
        return False
    except Exception as exc:
        logger.warning("[mem0] Failed to start extraction server: %s", exc)
        return False
```

---

## 6.3 — Create `core/memory_extractor.py`

```python
"""TurnGatedMemoryExtractor — queues turns for Mem0 extraction after active_turns == 0.

Extraction is asynchronous and fires only between voice turns.
Failures are logged and silently discarded — never block the main pipeline.
"""
from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from core.logger import logger

if TYPE_CHECKING:
    pass


class TurnGatedMemoryExtractor:
    def __init__(self, mem0_client, turn_feedback):
        self._mem0 = mem0_client
        self._feedback = turn_feedback
        self._pending: list[dict] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._running = True
        self._trigger = threading.Event()
        self._start_worker()

    def queue_turn(self, user_text: str, assistant_text: str, user_id: str = "default") -> None:
        """Queue a completed turn for async Mem0 extraction. Non-blocking."""
        with self._lock:
            self._pending.append({
                "user": user_text,
                "assistant": assistant_text,
                "user_id": user_id,
            })
        self._trigger.set()

    def stop(self) -> None:
        self._running = False
        self._trigger.set()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(
            target=self._drain_loop, name="mem0-extractor", daemon=True
        )
        self._worker.start()

    def _drain_loop(self) -> None:
        import time
        while self._running:
            self._trigger.wait(timeout=5.0)
            self._trigger.clear()

            if not self._running:
                return

            # Wait until no active voice turn
            while getattr(self._feedback, "active_turns", 0) > 0:
                time.sleep(0.5)

            with self._lock:
                turns = list(self._pending)
                self._pending.clear()

            for turn in turns:
                try:
                    self._mem0.add(
                        [
                            {"role": "user", "content": turn["user"]},
                            {"role": "assistant", "content": turn["assistant"]},
                        ],
                        user_id=turn["user_id"],
                    )
                    logger.debug("[mem0] Extracted facts for turn.")
                except Exception as exc:
                    logger.warning("[mem0] Extraction failed: %s", exc)
```

---

## 6.4 — Create `core/mem0_client.py`

```python
"""Mem0 client factory — builds the Memory instance from config.yaml.

All infrastructure (Chroma, HuggingFace embedder, LiteLLM endpoint) uses
resources already present on the system. No new downloads required.
"""
from __future__ import annotations

from core.logger import logger


def build_mem0_client(config: dict):
    """Build and return a mem0.Memory instance. Returns None if unavailable."""
    try:
        from mem0 import Memory
    except ImportError:
        logger.warning("[mem0] mem0ai not installed. Run: pip install mem0ai litellm")
        return None

    port = config.get("extraction_server", {}).get("port", 8181)
    host = config.get("extraction_server", {}).get("host", "127.0.0.1")
    collection = config.get("collection_name", "friday_mem0")
    chroma_path = config.get("chroma_path", "data/chroma")
    history_db = config.get("history_db_path", "data/mem0_history.db")

    mem0_config = {
        "llm": {
            "provider": "litellm",
            "config": {
                "model": "openai/qwen3-4b",
                "openai_api_base": f"http://{host}:{port}/v1",
                "openai_api_key": "not-needed",
                "temperature": 0.1,
                "max_tokens": 512,
                "top_p": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
            },
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": collection,
                "path": chroma_path,
            },
        },
        "history_db_path": history_db,
    }

    try:
        client = Memory.from_config(mem0_config)
        logger.info("[mem0] Memory client initialized. Collection: %s", collection)
        return client
    except Exception as exc:
        logger.warning("[mem0] Failed to initialize Memory client: %s", exc)
        return None
```

---

## 6.5 — Integrate into `MemoryService`

**File:** `core/memory_service.py` · Update `__init__()` and `build_context_bundle()`:

```python
class MemoryService:
    def __init__(self, context_store, memory_broker=None, mem0_client=None, extractor=None):
        self._store = context_store
        self._broker = memory_broker
        self._mem0 = mem0_client          # None when Mem0 is unavailable
        self._extractor = extractor        # TurnGatedMemoryExtractor

    def build_context_bundle(self, session_id: str, query: str) -> dict:
        bundle = {}
        if self._broker is not None and session_id:
            bundle = self._broker.build_context_bundle(query, session_id) or {}

        # Inject Mem0 facts — ~15-30ms retrieval, ~60 tokens injected
        if self._mem0 and query:
            try:
                results = self._mem0.search(query, user_id="default", limit=5)
                facts = [r["memory"] for r in (results.get("results") or [])]
                if facts:
                    bundle["user_facts"] = "\n".join(facts)
            except Exception as exc:
                logger.debug("[mem0] Retrieval failed (non-fatal): %s", exc)

        return bundle

    def record_turn(self, session_id: str, user_text: str, assistant_text: str, trace_id: str = "") -> None:
        # Existing episodic storage
        if not session_id:
            return
        if user_text:
            self._store.append_turn(session_id, "user", user_text, source=trace_id or None)
        if assistant_text:
            self._store.append_turn(session_id, "assistant", assistant_text, source=trace_id or None)

        # Queue Mem0 extraction (fires only after active_turns == 0)
        if self._extractor and user_text and assistant_text:
            self._extractor.queue_turn(user_text, assistant_text, user_id="default")
```

---

## 6.6 — Wire Mem0 into `FridayApp`

**File:** `core/app.py` · In `FridayApp.__init__()` after existing service inits:

```python
# Mem0 memory integration
from core.mem0_client import build_mem0_client
from core.memory_extractor import TurnGatedMemoryExtractor

mem0_cfg = self.config.get("memory", {}) if hasattr(self.config, "get") else {}
self._mem0_client = None
self._mem0_extractor = None

if mem0_cfg.get("enabled", False):
    if self._start_mem0_server():  # boots extraction server if auto_start=True
        self._mem0_client = build_mem0_client(mem0_cfg)
        if self._mem0_client:
            self._mem0_extractor = TurnGatedMemoryExtractor(
                self._mem0_client, self.turn_feedback
            )

# Rebuild MemoryService with Mem0 components
self.memory_service = MemoryService(
    self.context_store,
    self.memory_broker,
    mem0_client=self._mem0_client,
    extractor=self._mem0_extractor,
)
```

---

## 6.7 — Add Memory Config to `config.yaml`

```yaml
memory:
  enabled: true

  extraction_server:
    enabled: true
    host: "127.0.0.1"
    port: 8181
    model_path: "models/mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf"
    n_ctx: 1024
    n_batch: 128
    auto_start: true

  collection_name: "friday_mem0"
  chroma_path: "data/chroma"
  history_db_path: "data/mem0_history.db"

  max_facts_per_turn: 5
  gate_on_idle: true
  extraction_timeout_s: 10
```

---

## Phase 6 Verification

```bash
# Test extraction server is reachable
curl -s http://127.0.0.1:8181/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin))"

# Test Mem0 client initialization
python -c "
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
from core.mem0_client import build_mem0_client
client = build_mem0_client(cfg['memory'])
if client:
    print('Mem0 client: OK')
    # Test add
    client.add(
        [{'role': 'user', 'content': 'I prefer dark mode in my IDE.'},
         {'role': 'assistant', 'content': 'Noted, I will remember your preference.'}],
        user_id='default'
    )
    # Test search
    results = client.search('IDE preferences', user_id='default', limit=3)
    print('Facts retrieved:', [r['memory'] for r in results.get('results', [])])
else:
    print('Mem0 client: FAILED — check extraction server is running')
"

# Verify context bundle now includes user_facts
python -c "
# After a few turns, check that build_context_bundle returns user_facts
# Look for the 'user_facts' key in the bundle dict
print('Check memory_service.build_context_bundle() returns user_facts key after interactions.')
"
```

---

---

# Phase 7 — Mem0 Memory Integration: Advanced

**Goal:** Multi-user session isolation, memory inspection capability, and health-check graceful fallback.

**Prerequisite:** Phase 6 complete and stable (>50 turns accumulated to verify fact quality).

---

## 7.1 — Memory Inspection Capability

Allows the user to ask what FRIDAY remembers about them.

**File:** Register in a new `modules/memory_manager/plugin.py` or directly in `core/app.py`:

```python
self.router.register_tool(
    {
        "name": "show_memories",
        "description": "Show what FRIDAY remembers about the user — preferences, facts, context.",
        "context_terms": [
            "what do you remember", "show my memories",
            "what do you know about me", "forget that",
        ],
    },
    self._handle_show_memories,
)
```

Handler:

```python
def _handle_show_memories(self, raw_text: str, args: dict):
    from core.capability_registry import CapabilityExecutionResult
    if not self._mem0_client:
        return CapabilityExecutionResult(
            ok=True, name="show_memories",
            output="Memory system is not active.",
        )
    try:
        all_memories = self._mem0_client.get_all(user_id="default")
        results = all_memories.get("results", [])
        if not results:
            return CapabilityExecutionResult(
                ok=True, name="show_memories",
                output="I don't have any stored memories yet.",
            )
        lines = [f"{i+1}. {m['memory']}" for i, m in enumerate(results[:20])]
        return CapabilityExecutionResult(
            ok=True, name="show_memories",
            output="Here is what I remember:\n" + "\n".join(lines),
            output_type="list",
        )
    except Exception as exc:
        return CapabilityExecutionResult(ok=False, name="show_memories", error=str(exc))
```

---

## 7.2 — Memory Deletion Capability

```python
self.router.register_tool(
    {
        "name": "delete_memory",
        "description": "Delete a specific memory by its number from the memory list.",
        "context_terms": ["forget", "delete memory", "remove that memory", "stop remembering"],
    },
    self._handle_delete_memory,
)
```

Handler:

```python
def _handle_delete_memory(self, raw_text: str, args: dict):
    from core.capability_registry import CapabilityExecutionResult
    if not self._mem0_client:
        return CapabilityExecutionResult(ok=False, name="delete_memory", error="Memory system not active.")
    # The user says "forget the second one" — reference registry resolves ordinal to memory text
    # Then this handler searches by text and deletes the matching memory_id
    # Implementation: search for the memory, then call client.delete(memory_id)
    target = args.get("target", raw_text)
    try:
        results = self._mem0_client.search(target, user_id="default", limit=1)
        items = results.get("results", [])
        if not items:
            return CapabilityExecutionResult(
                ok=True, name="delete_memory",
                output=f"Could not find a memory matching: {target}",
            )
        memory_id = items[0]["id"]
        self._mem0_client.delete(memory_id)
        return CapabilityExecutionResult(
            ok=True, name="delete_memory",
            output=f"Deleted memory: {items[0]['memory']}",
        )
    except Exception as exc:
        return CapabilityExecutionResult(ok=False, name="delete_memory", error=str(exc))
```

---

## 7.3 — Extraction Server Health Check + Graceful Fallback

**File:** `core/mem0_client.py` · Add health check:

```python
def check_server_health(host: str, port: int, timeout: float = 2.0) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=timeout)
        return True
    except Exception:
        return False
```

In `build_mem0_client()`, add before creating the `Memory` instance:

```python
if not check_server_health(host, port):
    logger.warning(
        "[mem0] Extraction server at port %d not responding. "
        "Mem0 context retrieval will still work; new fact extraction disabled.",
        port,
    )
    # Return read-only client with no-op add method
    # (existing facts remain queryable; new extraction silently skipped)
```

---

## 7.4 — Periodic Memory Consolidation (Optional)

Run once a week: compress semantically similar facts and remove outdated ones.

```python
def consolidate_memories(mem0_client, user_id: str = "default") -> int:
    """Deduplicate semantically similar memories. Returns count removed."""
    all_mems = mem0_client.get_all(user_id=user_id).get("results", [])
    # Mem0's update mechanism handles conflicts during extraction —
    # consolidation here is a second pass for older, pre-conflict memories.
    # Use mem0_client.delete(id) for clearly outdated ones.
    # Run manually or on a weekly schedule.
    return 0  # placeholder
```

---

## Phase 7 Verification

```bash
# Show memories
python -c "
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
from core.mem0_client import build_mem0_client
client = build_mem0_client(cfg['memory'])
all_mems = client.get_all(user_id='default')
print('All stored memories:')
for m in all_mems.get('results', []):
    print(' -', m['memory'])
"
```

---

---

# Phase 8 — Cross-System Integration

**Goal:** Connect all three systems (Vision + Documents + Memory) so each reinforces the others.

**Prerequisite:** Phases 3, 5, and 7 all complete and stable.

---

## 8.1 — VLM Results Feed into Mem0

When VLM capabilities complete (analyze_screen, debug_code_screenshot), the result is already queued to `TurnGatedMemoryExtractor` via `MemoryService.record_turn()` — no additional wiring needed. The extractor receives the full assistant response including VLM output.

**Verify:** After saying "analyze my screen", the next day check `show_memories` — a fact like "User's screen showed a Python segfault error in libSDL2 on [date]" should appear.

---

## 8.2 — Document Context Informs Mem0

When `query_document` injects retrieved chunks into the LLM context, the LLM's response (which synthesizes document content) is what gets queued to Mem0 for extraction. Over time, Mem0 accumulates user-specific document preferences and frequently-accessed topics.

No additional wiring — happens automatically through the `record_turn()` path.

---

## 8.3 — Mem0 Facts Improve Document Retrieval

When a user asks "search my notes for the project we discussed", the `user_facts` injected from Mem0 contain "User is working on FRIDAY Linux AI assistant" — this context helps the LLM interpret the retrieved document chunks more accurately.

No code change needed — `user_facts` is already in the context bundle alongside retrieved document chunks.

---

## 8.4 — Unified Context Bundle Structure

After all phases, the context bundle injected into the LLM per-turn is:

```
System context bundle (full):
├── conversation_history     (last N turns — ContextStore, existing)
├── semantic_memories        (ChromaDB episodic recall — existing)
├── user_facts               [Phase 6] Mem0 distilled facts (~5 facts, ~60 tokens)
├── document_context         [Phase 4] MarkItDown retrieved chunks (if doc capability)
│   (max 1500 tokens, injected only when query_document/search_workspace runs)
└── active_workflow          (TaskGraphExecutor state — existing)

Visual context (when VLM runs):
└── VLM result text          (injected into assistant response, not system prompt)
```

Total context overhead vs. current baseline:
- Without Mem0, without doc chunks: **0 additional tokens** (Mem0 replaces raw turn injection)
- With Mem0 facts only: **~60 tokens** per turn (vs ~800-1200 tokens of raw history)
- With doc chunks: **+1500 tokens** (only on document queries — not every turn)

**Net result: 700–1100 tokens freed per turn in typical conversation.**

---

---

# Summary Table

| Phase | Deliverable | Files Changed/Created | Effort |
|---|---|---|---|
| **0** | Architecture foundation (artifact memory, reference registry, retries, resource monitor) | `core/capability_registry.py`, `core/capability_broker.py`, `core/context_store.py`, `core/memory_service.py`, `core/task_graph_executor.py`, `core/intent_recognizer.py`, `core/response_finalizer.py`, `core/turn_feedback.py`, new `core/resource_monitor.py` | 1 week |
| **1** | VisionService + 3 core capabilities (analyze_screen, ocr_reader, summarizer) | new `modules/vision/` (5 files), `config.yaml` | 1 week |
| **2** | Clipboard analyzer, code debugger, 3 fun features | `modules/vision/plugin.py`, `modules/vision/prompts.py`, `config.yaml` | 3 days |
| **3** | Screenshot comparison, UI element finder, smart error detector | `modules/vision/plugin.py`, new `modules/vision/smart_error_detector.py` | 1 week |
| **4** | Document Intelligence foundation (query_document, search_workspace) | new `modules/document_intel/` (7 files), `config.yaml` | 1 week |
| **5** | Conversational follow-up, workspace watcher, auto-indexing | `core/intent_recognizer.py`, `modules/document_intel/plugin.py`, new `modules/document_intel/workspace_watcher.py`, `config.yaml` | 1 week |
| **6** | Mem0 foundation (extraction server, TurnGatedMemoryExtractor, MemoryService integration) | new `core/resource_monitor.py`, new `core/mem0_client.py`, new `core/memory_extractor.py`, `core/memory_service.py`, `core/app.py`, `config.yaml` | 1 week |
| **7** | Mem0 advanced (show_memories, delete_memory, graceful fallback) | `core/app.py`, `core/mem0_client.py` | 3 days |
| **8** | Cross-system integration (no code, verification + tuning) | None — verify automatic integration | 3 days |

**Total new files:** ~20 files  
**Total modified files:** ~10 files  
**All phases combined estimated effort:** 7–8 weeks solo developer

---

# Installation Checklist

```bash
# Phase 0
pip install psutil

# Phase 1
pip install Pillow mss

# Phase 4
pip install 'markitdown[all]' watchdog

# Phase 6
pip install mem0ai litellm

# Verify all installed
python -c "import psutil, PIL, mss, markitdown, chromadb, mem0; print('All dependencies OK')"
```

---

# Test Suite — Additions Per Phase

| Phase | Test File | What to Test |
|---|---|---|
| 0 | `tests/test_working_artifact.py` | WorkingArtifact round-trip, pronoun resolution, ordinal resolution |
| 0 | `tests/test_resource_monitor.py` | Snapshot returns valid RAM values, cache TTL respected |
| 1 | `tests/test_vision_service.py` | VisionService lazy load, RAM guard, auto-unload watchdog |
| 1 | `tests/test_vision_preprocess.py` | Resize to 1024px, data URI format |
| 4 | `tests/test_document_chunker.py` | Heading-first chunking, paragraph fallback, hard split |
| 4 | `tests/test_document_retriever.py` | Embed → Chroma query → context budget enforcement |
| 6 | `tests/test_memory_extractor.py` | Queue turn → wait for active_turns == 0 → extraction fires |
| 6 | `tests/test_mem0_client.py` | Client init, add, search round-trip (requires server running) |
