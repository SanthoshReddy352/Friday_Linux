# FRIDAY — MarkItDown Integration Strategy

## Overview

This document defines how Microsoft MarkItDown can be integrated into FRIDAY to create high-value conversational capabilities while respecting the system constraints of the project.

The goal is not to build a generic enterprise RAG platform.
The goal is to build:

- fast local document intelligence
- low-latency conversational retrieval
- CPU-friendly semantic memory
- voice-first document workflows
- high-frequency daily-use capabilities

The implementation strategy is optimized specifically for:

- local inference
- CPU-only environments
- limited RAM
- conversational responsiveness
- offline-first architecture
- modular capability execution
- low orchestration overhead

---

# Why MarkItDown Matters For FRIDAY

MarkItDown converts complex file formats into clean markdown.

Supported inputs include:

- PDF
- DOCX
- PPTX
- XLSX
- HTML
- CSV
- images (OCR-supported)
- web exports
- plain text

Instead of building separate parsers for every document type, FRIDAY can standardize all ingestion into:

```text
Document → Markdown → Chunk → Retrieve
```

This dramatically reduces:

- parser maintenance
- preprocessing complexity
- token cleanup logic
- document-specific pipelines
- ingestion bugs

Most importantly:

Markdown is highly LLM-friendly.

The markdown representation preserves:

- headings
- sections
- tables
- lists
- formatting hierarchy
- code blocks
- semantic structure

This improves retrieval quality while reducing prompt noise.

---

# System Constraints That MUST Be Preserved

## Constraint 1 — Low Inference Latency

FRIDAY is a conversational assistant.
Slow response time destroys conversational realism.

Therefore:

- retrieval must be lightweight
- chunk count must remain small
- retrieval depth must remain shallow
- context injection must be minimal
- document parsing must happen offline/preprocessing time

Avoid:

- large retrieval chains
- multi-agent retrieval
- recursive summarization
- rerankers initially
- graph RAG
- multi-hop retrieval

---

## Constraint 2 — CPU-Only Execution

Target hardware:

- integrated graphics
- 16GB RAM
- local GGUF inference
- llama.cpp

Therefore:

- embedding models must remain small
- chunk sizes must remain controlled
- vector DB must remain lightweight
- retrieval operations must stay memory efficient

Recommended:

### Embedding Models

- all-MiniLM-L6-v2
- bge-small-en
- nomic-embed-text

Avoid:

- large embedding models
- cross-encoder rerankers
- transformer-heavy retrieval stacks

---

## Constraint 3 — Voice-First UX

FRIDAY is not just a chatbot.
It is a conversational voice assistant.

Therefore:

- document retrieval must sound conversational
- responses must remain concise
- long documents should not dump massive summaries
- responses should feel interactive

Preferred:

```text
"I found three action items in the meeting notes."
```

Not:

```text
10-page generated summaries.
```

---

## Constraint 4 — Local-First Architecture

The system should work offline.

Therefore:

- ingestion should happen locally
- embeddings should be generated locally
- retrieval should be local
- document memory should remain local

Online enhancement should remain optional.

---

# High Conversion Features

These are features that provide:

- immediate user value
- repeated usage frequency
- conversational stickiness
- strong perceived intelligence
- realistic implementation scope

---

# Tier 1 — Highest ROI Features

These features should be implemented first.

---

## Feature 1 — Ask Questions About Any File

### User Flow

```text
"Summarize this PDF"
"What are the main points in this PPT?"
"Search this Excel for revenue trends"
"Read my resume"
```

### Why This Has High Conversion

This is instantly understandable.
Users immediately recognize the value.

This turns FRIDAY from:

```text
voice assistant
```

into:

```text
personal document intelligence assistant
```

### Implementation Difficulty

LOW

### Architecture

```text
File
  ↓
MarkItDown
  ↓
Markdown
  ↓
Chunk
  ↓
Embedding
  ↓
Vector Store
  ↓
Retrieval
  ↓
LLM Context
```

### Recommended Limits

- max retrieval chunks: 4
- max chunk size: 500 tokens
- overlap: 80 tokens
- injected context max: 1500 tokens

---

## Feature 2 — Conversational Workspace Memory

### User Flow

```text
"What did I decide about model routing?"
"Search my architecture notes"
"What were the deployment steps?"
```

### Why This Has High Conversion

This creates:

- persistence
- continuity
- assistant intelligence illusion
- emotional attachment

This is one of the strongest retention features.

### Core Idea

FRIDAY continuously indexes:

- notes
- project docs
- markdown files
- architecture documents
- meeting notes
- research papers

Then retrieves semantically.

### Important Constraint

Do NOT continuously re-embed entire folders.

Use:

- file hash checking
- incremental indexing
- modified-time tracking

---

## Feature 3 — Voice-Based Document Assistant

### User Flow

```text
"Open the AI paper and summarize section 4"
"Search all my notes for vector databases"
"Read the latest meeting notes"
```

### Why This Has High Conversion

This directly aligns with:

- voice-first UX
- Jarvis-style interaction
- hands-free workflow

This is a major identity feature for FRIDAY.

### Important Design Rule

Responses should remain spoken-language optimized.

Good:

```text
"The paper proposes a lightweight retrieval pipeline using compressed embeddings."
```

Bad:

```text
Massive paragraph dumps.
```

---

## Feature 4 — Project Intelligence Layer

### User Flow

```text
"Search the FRIDAY architecture"
"How does capability routing currently work?"
"Find the memory broker logic"
```

### Why This Has High Conversion

This makes FRIDAY useful for developers daily.

Daily-use features have the highest retention.

### Ideal Sources

- markdown docs
- source code
- architecture notes
- roadmaps
- changelogs
- TODO files

### High Value Outcome

FRIDAY becomes:

```text
codebase memory assistant
```

instead of:

```text
basic desktop assistant
```

---

# Tier 2 — Medium Complexity High Value Features

---

## Feature 5 — Auto Meeting Notes Intelligence

### Workflow

- user records meeting
- STT generates transcript
- transcript converted to markdown
- indexed automatically

### Capabilities

```text
"What were the action items from yesterday's meeting?"
"Who mentioned deployment issues?"
```

### Why This Is Valuable

This creates continuous memory.

Extremely sticky feature.

---

## Feature 6 — Smart Resume + Portfolio Assistant

### User Flow

```text
"Improve my resume"
"Tailor my resume for AI roles"
"Generate portfolio summaries from my projects"
```

### Why This Converts

Very practical.
High perceived intelligence.
High repeat usage.

---

## Feature 7 — Research Paper Companion

### User Flow

```text
"Explain this paper simply"
"Summarize the methodology"
"What are the limitations?"
```

### Why Valuable

High educational utility.
Perfect for local document intelligence.

---

# Features That Should NOT Be Implemented Initially

Avoid these during early stages.

---

## Graph RAG

Too heavy.
Too complex.
Low ROI for local hardware.

---

## Agentic Retrieval Pipelines

Too much inference overhead.
Conversation latency increases.

---

## Multi-Step Recursive Summarization

Large latency cost.
Weak conversational UX.

---

## Full Document Injection

Never inject whole documents.

Always:

```text
retrieve small relevant chunks
```

---

## Large Embedding Models

Bad for CPU systems.

---

# Recommended Architecture

## New Capability Layer

Add new capabilities:

```text
index_document
query_document
search_workspace
summarize_document
retrieve_document_context
```

Register through:

- CapabilityRegistry
- CapabilityBroker
- ConversationAgent

---

# Proposed Storage Architecture

## Metadata Store

SQLite

Store:

```text
file_id
path
hash
modified_time
title
document_type
indexed_at
```

---

## Vector Store

Recommended:

- Chroma
- SQLite-vss
- LanceDB

Preferred initially:

```text
Chroma
```

because your ContextStore already aligns with lightweight local semantic retrieval.

---

# Recommended Chunking Strategy

## Chunk Size

```text
400–700 tokens
```

## Overlap

```text
80–120 tokens
```

## Retrieval Count

```text
Top 3–4 chunks
```

## Injection Budget

```text
< 1500 tokens
```

---

# Recommended Retrieval Pipeline

## Step 1 — Intent Detection

Detect whether retrieval is required.

Examples:

```text
"summarize this pdf"
"search my notes"
"what did the document say"
```

---

## Step 2 — Retrieve Minimal Context

Retrieve:

- only relevant chunks
- only top semantic matches
- only required sections

---

## Step 3 — Inject Context

Inject retrieved chunks into:

- chat model
- summarizer
- workflow execution

---

## Step 4 — Generate Conversational Response

Keep responses:

- concise
- spoken-language optimized
- contextual

---

# Integration Points Inside FRIDAY

---

## ContextStore Integration

Existing semantic memory system already exists.

Can be extended for:

- document chunks
- embeddings
- retrieval metadata
- workspace indexing

---

## MemoryBroker Integration

MemoryBroker can dynamically include:

```text
retrieved document chunks
```

inside:

```text
context_bundle
```

---

## CapabilityBroker Integration

CapabilityBroker should decide:

```text
chat only
chat + memory
chat + document retrieval
online search
```

This preserves inference efficiency.

---

## ConversationAgent Integration

ConversationAgent can orchestrate:

- indexing workflows
- retrieval workflows
- summarization workflows

without requiring architectural rewrites.

---

# Latency Optimization Techniques

These are mandatory.

---

## Technique 1 — Preprocessing

Convert and embed once.

Never repeatedly parse files.

---

## Technique 2 — Incremental Indexing

Use:

- file hashes
- modified timestamps

Avoid:

- full workspace reindexing

---

## Technique 3 — Retrieval Budgeting

Hard-limit:

- chunk count
- context tokens
- retrieval depth

---

## Technique 4 — Background Indexing

Index documents asynchronously.

Never block conversation execution.

---

## Technique 5 — Response Compression

Prefer:

```text
concise answers
```

instead of:

```text
large summaries
```

---

# Recommended Initial Stack

## Parsing

```python
from markitdown import MarkItDown
```

---

## Embeddings

```text
all-MiniLM-L6-v2
```

---

## Vector Database

```text
Chroma
```

---

## Inference

Existing local GGUF stack.

```te
```
