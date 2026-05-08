# FRIDAY — MarkItDown Phase-Wise Implementation Plan

# Objective

This document defines the detailed implementation roadmap for integrating MarkItDown-powered conversational document intelligence into FRIDAY.

The roadmap is optimized for:

- low inference overhead
- CPU-only execution
- conversational responsiveness
- modular architecture
- local-first operation
- voice-first workflows
- high user retention features

The implementation strategy intentionally avoids:

- enterprise RAG complexity
- heavy orchestration
- expensive retrieval pipelines
- GPU assumptions
- high-latency workflows

---

# Core Design Philosophy

The goal is NOT:

```text
"Build a generic RAG platform"
```

The goal IS:

```text
"Make FRIDAY feel intelligent during real conversations"
```

Therefore:

- retrieval must remain invisible
- interactions must remain conversational
- inference count must remain controlled
- retrieval must feel instant
- indexing must happen in the background

---

# Global Architecture Roadmap

```text
Phase 1 → Document Ingestion
Phase 2 → Retrieval Engine
Phase 3 → Conversational Retrieval
Phase 4 → Workspace Intelligence
Phase 5 → Voice-First Intelligence
Phase 6 → Persistent Workspace Memory
Phase 7 → Meeting + Research Intelligence
Phase 8 → Optimization + Compression
```

---

# Phase 1 — Lightweight Document Ingestion

# Goal

Create the foundational ingestion pipeline.

Convert documents into markdown and store them for future retrieval.

---

# Primary Outcome

FRIDAY can:

```text
- import files
- convert files to markdown
- chunk documents
- generate embeddings
- store searchable chunks
```

---

# Features

## Feature 1 — File Import

Supported:

- PDF
- DOCX
- PPTX
- XLSX
- TXT
- MD
- HTML

---

## Feature 2 — MarkItDown Conversion

Pipeline:

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert(file_path)
markdown = result.text_content
```

---

## Feature 3 — Markdown Cleaning

Normalize:

- whitespace
- repeated line breaks
- malformed headings
- noisy OCR sections

Avoid:

- aggressive cleaning
- semantic rewriting

---

## Feature 4 — Chunking Engine

Initial Strategy:

```text
chunk_size = 500 tokens
overlap = 100 tokens
```

Chunk by:

- headings first
- paragraphs second
- hard token fallback

---

## Feature 5 — Metadata Storage

Store:

```text
file_id
path
hash
created_at
modified_at
document_type
title
chunk_count
```

Database:

```text
SQLite
```

---

## Feature 6 — Vector Storage

Initial recommendation:

```text
Chroma
```

Reason:

- lightweight
- local-first
- simple integration
- CPU friendly

---

# Required Components

## New Modules

```text
core/document_pipeline/
```

Inside:

```text
converter.py
chunker.py
embedder.py
document_store.py
retriever.py
```

---

# New Capabilities

Register:

```text
index_document
index_workspace
```

---

# Integration Points

## CapabilityRegistry

Register ingestion capabilities.

---

## ConversationAgent

Allow:

```text
"Index this document"
```

---

## ContextStore

Extend for:

- document metadata
- chunk references
- embedding references

---

# Constraints To Preserve

DO NOT:

- retrieve during ingestion
- summarize during indexing
- perform recursive analysis
- block conversations during indexing

---

# Complexity

LOW

---

# Expected Value

VERY HIGH

---

# Phase 2 — Lightweight Retrieval Engine

# Goal

Enable semantic document retrieval.

---

# Primary Outcome

FRIDAY can:

```text
- search indexed documents
- retrieve relevant chunks
- answer document questions
```

---

# Features

## Feature 1 — Semantic Search

Examples:

```text
"Search my notes for model routing"
"Find deployment instructions"
```

---

## Feature 2 — Top-K Retrieval

Recommended:

```text
Top 3–4 chunks only
```

Hard limits preserve latency.

---

## Feature 3 — Metadata Filtering

Filter by:

- file name
- document type
- workspace
- creation date

---

## Feature 4 — Context Injection

Inject only:

```text
relevant retrieved chunks
```

Avoid:

```text
full documents
```

---

# Retrieval Pipeline

```text
User Query
    ↓
Embedding
    ↓
Vector Search
    ↓
Top Chunks
    ↓
LLM Context
    ↓
Response
```

---

# New Capabilities

```text
query_document
search_workspace
retrieve_document_context
```

---

# Important Constraints

Hard limits:

```text
max_chunks = 4
max_context_tokens = 1500
```

---

# Complexity

LOW-MEDIUM

---

# Expected Value

EXTREMELY HIGH

---

# Phase 3 — Conversational Document Intelligence

# Goal

Make retrieval conversational.

The user should feel:

```text
"FRIDAY understands my documents"
```

instead of:

```text
"I am using a search engine"
```

---

# Primary Outcome

FRIDAY can:

```text
- summarize naturally
- answer conversationally
- explain sections
- maintain conversational continuity
```

---

# Features

## Feature 1 — Conversational Summaries

Examples:

```text
"Summarize this paper"
"What is section 4 about?"
```

---

## Feature 2 — Follow-Up Questioning

Examples:

```text
"Explain that further"
"What were the limitations?"
```

Requires:

- retrieval continuity
- chunk reference tracking

---

## Feature 3 — Context-Aware Retrieval

Use:

- previous document
- previous retrieved chunks
- active workflow state

---

# Integration Points

## MemoryBroker

Inject retrieved chunks into:

```text
context_bundle
```

---

## ConversationAgent

Track:

- active document
- retrieval history
- follow-up references

---

## DialogueManager

Optimize responses for:

- spoken summaries
- concise answers
- conversational pacing

---

# Important Constraints

Avoid:

- long summaries
- multi-page outputs
- recursive retrieval

Keep:

```text
response length conversational
```

---

# Complexity

MEDIUM

---

# Expected Value

VERY HIGH

---

# Phase 4 — Workspace Intelligence Layer

# Goal

Turn FRIDAY into a persistent workspace intelligence assistant.

---

# Primary Outcome

FRIDAY can:

```text
- understand project folders
- search architecture docs
- retrieve codebase notes
- answer workspace questions
```

---

# Features

## Feature 1 — Workspace Indexing

Index:

- project folders
- notes folders
- documentation folders
- research directories

---

## Feature 2 — Incremental Sync

Track:

- file hashes
- modified timestamps
- deleted files

Avoid:

```text
full reindexing
```

---

## Feature 3 — Workspace Profiles

Examples:

```text
FRIDAY/
Research/
College/
Portfolio/
```

---

## Feature 4 — Workspace Search

Examples:

```text
"Search the FRIDAY architecture"
"Find memory management logic"
```

---

# Required Components

## Workspace Watcher

Background file monitoring.

---

## Incremental Index Scheduler

Runs asynchronously.

---

# Important Constraints

Workspace indexing must:

- run in background
- avoid blocking voice processing
- avoid repeated embedding generation

---

# Complexity

MEDIUM

---

# Expected Value

VERY HIGH

---

# Phase 5 — Voice-First Document Intelligence

# Goal

Make document interaction feel like a real voice assistant.

---

# Primary Outcome

FRIDAY supports:

```text
hands-free document interaction
```

---

# Features

## Feature 1 — Voice Document Queries

Examples:

```text
"Open the AI paper and summarize section 4"
"Search my architecture notes"
```

---

## Feature 2 — Spoken Summaries

Responses optimized for TTS.

Good:

```text
"The paper proposes a compressed retrieval system using lightweight embeddings."
```

Bad:

```text
large paragraph dumps
```

---

## Feature 3 — Conversational Continuity

Examples:

```text
"Explain that more"
"What happened after that?"
```

---

# Required Integration

## SpeechCoordinator

Coordinate:

- interruptions
- pauses
- long summaries
- response pacing

---

## TurnManager

Maintain:

- active document context
- active retrieval state

---

# Important Constraints

Voice interactions must remain:

- low latency
- concise
- interruptible

---

# Complexity

MEDIUM

---

# Expected Value

EXTREMELY HIGH

---

# Phase 6 — Persistent Semantic Workspace Memory

# Goal

Create long-term conversational workspace memory.

---

# Primary Outcome

FRIDAY remembers:

- previous discussions
- architecture decisions
- workflows
- research findings
- project notes

---

# Features

## Feature 1 — Cross-Document Recall

Examples:

```text
"What did I decide about routing last week?"
```

---

## Feature 2 — Semantic Project Memory

Examples:

```text
"What were the unresolved issues in the architecture notes?"
```

---

## Feature 3 — Workspace Knowledge Linking

Link:

- notes
- docs
- architecture
- meeting transcripts

---

# Important Constraints

Avoid:

- giant memory injection
- excessive historical retrieval

Use:

```text
small focused recall
```

---

# Complexity

MEDIUM-HIGH

---

# Expected Value

EXTREMELY HIGH

---

# Phase 7 — Meeting + Research Intelligence

# Goal

Expand FRIDAY into a research and meeting assistant.

---

# Features

## Feature 1 — Meeting Intelligence

Pipeline:

```text
Audio
 ↓
STT
 ↓
Transcript
 ↓
Markdown
 ↓
Indexing
```

---

## Feature 2 — Action Item Extraction

Examples:

```text
"What are the action items from yesterday's meeting?"
```

---

## Feature 3 — Research Paper Assistant

Examples:

```text
"Explain this paper simply"
"Summarize methodology"
```

---

# Important Constraints

Keep:

- retrieval lightweight
- summaries concise
- indexing background-only

---

# Complexity

MEDIUM-HIGH

---

# Expected Value

VERY HIGH

---

# Phase 8 — Optimization + Compression Phase

# Goal

Reduce latency and improve scalability.

---

# Features

## Feature 1 — Embedding Cache

Avoid repeated embeddings.

---

## Feature 2 — Retrieval Cache

Cache:

- repeated searches
- frequent retrievals

---

## Feature 3 — Adaptive Retrieval Budgeting

Dynamic retrieval count:

```text
simple query → fewer chunks
complex query → more chunks
```

---

## Feature 4 — Response Compression

Compress:

- verbose outputs
- repetitive summaries

---

# Important Constraints

Optimization should NOT:

- increase orchestration complexity
- add inference-heavy rerankers
- introduce large retrieval chains

---

# Complexity

MEDIUM

---

# Expected Value

HIGH

---

# Recommended Development Order

# Highest Priority

Implement first:

```text
Phase 1
Phase 2
Phase 3
```

These alone provide massive value.

---

# Second Priority

Implement after stabilization:

```text
Phase 4
Phase 5
```

These create FRIDAY's identity.

---

# Long-Term Expansion

Implement later:

```text
Phase 6
Phase 7
Phase 8
```

These improve retention and intelligence depth.

