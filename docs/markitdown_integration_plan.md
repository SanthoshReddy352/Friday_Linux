# FRIDAY MarkItDown Integration — Validated Strategy and Implementation Plan

## What the Strategy Documents Got Right

The three strategy documents (`friday_markitdown_rag_strategy.md`, `friday_markitdown_phasewise_implementation_plan.md`, `friday_markitdown_final_strategic_decision.md`) describe a sound approach. The architectural direction is correct:

- Lightweight local RAG, not enterprise-scale
- Conversational responses, not search-engine dumps
- Background indexing, not inline blocking
- Voice-UX optimized retrieval

**However**, the documents were written without knowledge of the current codebase state. Several major assumptions are outdated.

---

## What Already Exists (Critical Discoveries)

The MarkItDown integration strategy recommends building infrastructure that is **already partially present**:

### 1. Chroma Vector Store — Already Running

`ContextStore` (`core/context_store.py:L778`) already initializes a ChromaDB collection at `data/chroma/`. The vector store the strategy recommends building from scratch already exists and is used for semantic memory recall.

**Implication:** Document chunks can be added to an additional collection in the **same Chroma instance** with zero new infrastructure.

### 2. `all-MiniLM-L6-v2` — Already Downloaded and Used

`core/embedding_router.py` already loads `sentence-transformers/all-MiniLM-L6-v2` (22M params, ~90 MB, 384-dim). This is exactly the embedding model the strategy recommends.

**Implication:** The embedding model is already available, already cached, and already has a warmup path. The document indexer reuses it via the same `sentence-transformers` library.

### 3. `MemoryBroker.build_context_bundle()` — Already the Injection Point

`MemoryBroker` (`core/memory_broker.py:L22`) already builds per-turn context bundles. Document retrieval results slot directly into this bundle without any architectural change.

### 4. `CapabilityRegistry` — Already the Extension Point

All new document capabilities register through the existing `CapabilityRegistry`. No new plugin loading system is needed.

### 5. SQLite — Already the Metadata Store

`data/friday.db` is already the project's SQLite database. Document metadata goes into a new table in the same file.

---

## Revised Architecture

The strategy documents proposed building parallel infrastructure. The correct approach is to **slot into what exists**:

```
User Request
→ RouteScorer detects document intent
→ CapabilityBroker selects document capability
→ DocumentService queries existing Chroma instance (new collection)
→ Top 3-4 chunks retrieved
→ MemoryBroker injects chunks into context_bundle
→ Chat model responds conversationally
→ TTS delivers voice-optimized response
```

Document indexing (background path):
```
File path provided (or workspace folder watched)
→ MarkItDown converts to Markdown
→ Chunker splits by heading/paragraph
→ Existing all-MiniLM-L6-v2 embeds chunks
→ Stored in Chroma "friday_documents" collection
→ Metadata (path, hash, modified_at) in existing SQLite friday.db
```

---

## MarkItDown Usage

Install:
```bash
pip install 'markitdown[all]'
```

Usage in `DocumentPipeline`:
```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False)
result = md.convert(file_path)
markdown_text = result.text_content
```

**`enable_plugins=False`** is important for CPU-first systems — it disables any network-dependent plugin behavior and keeps conversion deterministic and offline.

Supported formats (no extra parsers needed): PDF, DOCX, PPTX, XLSX, HTML, CSV, TXT, MD.

---

## Validated Feature Set

Only features that fit the latency and hardware constraints are included.

---

## Feature 1 — Ask Questions About Any File

**Priority: Highest**

**User flow:**
```
"Summarize this PDF"
"What are the main points in this presentation?"
"Search this spreadsheet for revenue numbers"
"Explain section 3 of this document"
```

**Why it has high conversion:** Users immediately understand this capability. It converts FRIDAY from a voice assistant into a personal document intelligence layer.

**Implementation:**

```python
# modules/document_intel/plugin.py
self.app.router.register_tool({
    "name": "query_document",
    "description": "Ask a question about a document file (PDF, DOCX, PPTX, XLSX, TXT, MD). Summarizes or retrieves specific information.",
    "parameters": {
        "file_path": "string — path to the document",
        "question": "string — what to find or summarize",
    },
    "context_terms": ["summarize", "what does", "explain", "search document", "read file", "key points"],
})
```

Handler flow:
1. Check if file is already indexed (hash match in SQLite)
2. If not: convert with MarkItDown, chunk, embed, store (blocks synchronously only on first access — acceptable)
3. Embed the question with the same `all-MiniLM-L6-v2` model
4. Query Chroma `friday_documents` collection, retrieve top 3 chunks
5. Return chunks as context to `CapabilityExecutionResult.output`
6. `MemoryBroker` injects context into bundle
7. Chat model generates conversational response

**Hard limits (mandatory):**
```python
MAX_RETRIEVAL_CHUNKS = 4
MAX_CONTEXT_TOKENS = 1500
MAX_CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 80
```

---

## Feature 2 — Workspace Semantic Memory

**Priority: Highest**

**User flow:**
```
"What did I decide about model routing?"
"Search my architecture notes"
"What were the deployment steps I wrote down?"
"Find anything about memory management"
```

**Why it converts:** Creates the illusion (and reality) of persistent intelligence. The assistant feels like it genuinely remembers project context.

**Implementation:**

```python
"name": "search_workspace",
"description": "Search across all indexed documents and notes in the workspace. Finds relevant content from any previously indexed file.",
"parameters": {
    "query": "string — what to search for",
    "workspace": "string — optional workspace filter (default: all)",
},
"context_terms": ["search my notes", "find in docs", "what did I write", "search workspace", "find anything about"],
```

**Workspace indexing:** A background file watcher monitors configured folders (specified in `config.yaml`). Uses file hash + modified timestamp to avoid re-embedding unchanged files. New/changed files are queued and processed by a daemon thread during idle periods.

```yaml
document_intel:
  workspace_folders:
    - ~/Documents/friday-notes
    - ~/Friday_Linux/docs
    - ~/projects
  auto_index: true
  index_extensions: [".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt"]
```

---

## Feature 3 — Conversational Document Follow-Up

**Priority: High**

**User flow:**
```
"Summarize this paper"
→ "What were the limitations?"
→ "Explain that further"
→ "What was the methodology?"
```

**Implementation:**

Track the `active_document` in the reference registry (from the architecture validation plan — Allegation 4 fix). When `IntentRecognizer` detects a follow-up reference without a new file path, it resolves to `reference_registry["active_document"]` and re-queries with the new question.

This slots into the Working Artifact Memory infrastructure (Allegation 1 fix). The indexed document becomes a `WorkingArtifact` of type `"document"`.

---

## Feature 4 — Project Intelligence Layer (Codebase Memory)

**Priority: High for developers**

**User flow:**
```
"How does capability routing work?"
"Find the memory broker logic"
"What calls what in the workflow orchestrator?"
"Where is the TTS handled?"
```

FRIDAY's own codebase (`~/Friday_Linux/`) is indexed as a workspace. This makes the assistant useful for its own development, daily.

**Technical note:** Python source files are indexed as plain text (`.py` extension mapped to text converter in MarkItDown). The semantic chunking by heading/function definition works well on Python docstrings and class structures.

---

## Feature 5 — Research Paper Companion

**Priority: Medium**

**User flow:**
```
"Explain this paper simply"
"Summarize the methodology"
"What are the main contributions?"
"What did they find in section 4?"
```

**Why valuable:** Academic PDFs are one of the hardest formats for general-purpose assistants. MarkItDown handles PDF structure well, preserving section headers for heading-based chunking.

---

## Features Deferred (With Reasoning)

| Feature | Reason Deferred |
|---|---|
| Graph RAG | Too heavy for CPU; high indexing cost; retrieval latency > 1s |
| Multi-agent retrieval | Multiplies inference cost; incompatible with voice-first latency |
| Recursive summarization | Double/triple inference passes; poor voice UX |
| Large embedding models | bge-large-en would be ~500MB and 3x slower than MiniLM |
| Full document injection | Hard limit: never inject >1500 tokens of retrieved context |
| Real-time workspace sync | Continuous re-embedding on every file change is wasteful |
| Meeting transcription | Phase 2 priority — STT already exists, just needs indexing hook |

---

## Module Structure

```
modules/document_intel/
├── __init__.py
├── plugin.py           # FridayPlugin — registers all capabilities
├── service.py          # DocumentIntelService — orchestrates pipeline
├── converter.py        # MarkItDown wrapper with error handling
├── chunker.py          # Heading-first, paragraph-second, token-limit chunker
├── embedder.py         # Wraps the existing all-MiniLM-L6-v2 from embedding_router
├── document_store.py   # Chroma collection + SQLite metadata management
├── retriever.py        # Query → embed → Chroma → top-k chunks
└── workspace_watcher.py  # inotify/watchdog-based background indexer
```

---

## Database Schema

New table in existing `data/friday.db`:

```sql
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
);
```

Chroma collection name: `"friday_documents"` — separate from the existing memory collection to avoid collision.

---

## Chunking Strategy

**Heading-first chunking** preserves document structure for better retrieval:

```python
def chunk_markdown(text: str, max_tokens: int = 400, overlap: int = 80) -> list[str]:
    # 1. Split on markdown headings (## Section, ### Subsection)
    # 2. If section > max_tokens: split on paragraph boundaries
    # 3. If paragraph > max_tokens: hard token-count split with overlap
    # 4. Prepend parent heading to each chunk for context
    ...
```

Heading-prefixed chunks:
- "## Architecture > ### CapabilityBroker > [chunk text]"

This dramatically improves retrieval quality because the model can match "how does routing work?" to chunks labeled with routing-related headings.

---

## Retrieval Pipeline

```python
class DocumentRetriever:
    def query(self, question: str, top_k: int = 4, workspace: str | None = None) -> list[dict]:
        # 1. Embed question with all-MiniLM-L6-v2 (10-20ms, same model already warmed up)
        query_embedding = self.embedder.embed(question)
        
        # 2. Query Chroma with optional workspace filter
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, MAX_RETRIEVAL_CHUNKS),
            where={"workspace": workspace} if workspace else None,
        )
        
        # 3. Return chunks with source metadata
        return [
            {
                "text": doc,
                "source_file": meta["path"],
                "chunk_index": meta["chunk_index"],
                "score": float(dist),
            }
            for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
        ]
```

**Retrieval budget enforcement:**
```python
MAX_RETRIEVAL_CHUNKS = 4
MAX_CONTEXT_TOKENS = 1500

def build_context_for_llm(chunks: list[dict]) -> str:
    context_parts = []
    token_count = 0
    for chunk in chunks:
        chunk_tokens = len(chunk["text"].split()) * 1.3  # rough token estimate
        if token_count + chunk_tokens > MAX_CONTEXT_TOKENS:
            break
        context_parts.append(f"[From {chunk['source_file']}]\n{chunk['text']}")
        token_count += chunk_tokens
    return "\n\n---\n\n".join(context_parts)
```

---

## Latency Profile

| Operation | Estimated Latency | Notes |
|---|---|---|
| Question embedding | 10–20 ms | all-MiniLM-L6-v2, already warmed up |
| Chroma query (top 4) | 5–15 ms | Local SQLite-backed Chroma |
| Context injection into bundle | < 1 ms | String concatenation |
| Total retrieval overhead | **15–35 ms** | Well within interactive budget |

**First-time indexing** (file not yet in Chroma):
- PDF (10 pages): ~2–5 seconds for MarkItDown + chunking + embedding
- This blocks only on first access; subsequent queries are fast
- Long documents can be indexed asynchronously if first-access blocking is unacceptable

---

## Implementation Order

### Phase 1 — Foundation (Highest Priority)

```
1. modules/document_intel/ skeleton
2. converter.py (MarkItDown wrapper)
3. chunker.py (heading-first chunking)
4. embedder.py (wraps existing all-MiniLM-L6-v2)
5. document_store.py (Chroma + SQLite)
6. retriever.py (query pipeline)
7. plugin.py registers: query_document, search_workspace
```

Delivers Feature 1 (File QA) and Feature 2 (Workspace Search).

### Phase 2 — Conversational Intelligence

```
8. Active document tracking via WorkingArtifact (ties into architecture plan)
9. Follow-up query resolution via reference_registry
10. Voice-optimized response post-processing in DialogueManager
```

Delivers Feature 3 (Follow-up QA).

### Phase 3 — Workspace Integration

```
11. workspace_watcher.py with inotify/watchdog
12. Background incremental indexing daemon
13. config.yaml workspace_folders support
14. register: index_workspace capability
```

Delivers Feature 4 (Project Intelligence Layer).

### Phase 4 — Optimization

```
15. Query result caching (repeated question → cached chunks)
16. Adaptive chunk count (simple query → 2 chunks, complex → 4)
17. Response compression for voice output
```

---

## Configuration

```yaml
document_intel:
  enabled: true
  
  # Retrieval limits (mandatory — do not raise these)
  max_chunks: 4
  max_context_tokens: 1500
  chunk_size_tokens: 400
  chunk_overlap_tokens: 80
  
  # Chroma collection
  collection_name: "friday_documents"
  
  # Workspace auto-indexing
  auto_index: false           # start false; enable after Phase 1 stable
  workspace_folders: []       # e.g. ["~/Documents", "~/projects"]
  index_extensions:
    - ".pdf"
    - ".docx"
    - ".pptx"
    - ".xlsx"
    - ".md"
    - ".txt"
  
  # Background indexer
  index_idle_only: true       # only index when no active voice turn
  index_batch_size: 3         # files per background batch
```

---

## Critical Rules (From the Strategy Documents — Verified as Correct)

1. **Never inject full documents.** Always retrieve small relevant chunks.
2. **Never index synchronously during a voice turn.** All indexing is background-only.
3. **Never use more than 4 chunks / 1500 tokens per retrieval.** This is the hard budget.
4. **Always preprocess offline.** MarkItDown converts once; embeddings stored permanently.
5. **Voice response must be concise.** The chat model's system prompt specifies spoken-language output when document context is injected.
6. **Retrieval must feel invisible.** The user asks a question; they get an answer. They should not feel like they are operating a search engine.
