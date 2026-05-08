# FRIDAY — System Constraints, Deferred Architectural Decisions, and Latency-Aware Engineering Strategy

# Context

FRIDAY is fundamentally designed as:

```text
A local-first voice-native adaptive AI assistant
```

The most important architectural requirement is:

# Conversational Responsiveness

For voice assistants:

- latency is intelligence
- responsiveness is personality
- interruption handling is realism

A technically advanced system that responds slowly will feel significantly less intelligent than a lightweight system that responds quickly.

This document defines:

- hardware constraints
- inference constraints
- architectural limitations
- deferred architectural systems
- approved architectural upgrades
- low-latency engineering patterns
- inference-preserving implementation strategies

---

# Current Hardware Constraints

## User Hardware

### CPU

Intel i5 12th Gen H-Series Processor

### GPU

Intel UHD Integrated Graphics

No dedicated GPU.

### RAM

16 GB RAM

### Inference Stack

- llama.cpp
- GGUF quantized inference
- Qwen3 4B Abliterated
- Q4_K_M quantization

---

# Core Architectural Constraint

The assistant is:

```text
voice-first
```

NOT:

```text
chat-first
```

This changes the entire architectural philosophy.

---

# Voice Assistant Latency Requirements

## Human Conversational Thresholds

### Ideal

```text
< 700ms
```

Feels immediate and natural.

---

### Acceptable

```text
700ms – 1.5s
```

Still conversational.

---

### Poor

```text
2s – 4s
```

Feels computational.

---

### Unnatural

```text
> 4s
```

Feels broken or robotic.

---

# Important Engineering Reality

For local voice assistants:

# Inference management matters more than raw intelligence.

A highly optimized 4B assistant:

- with fast routing
- low latency
- interruption support
- continuity
- strong execution

will feel significantly smarter than:

- a slow 14B reasoning-heavy assistant.

---

# Architectural Principle Going Forward

The architecture MUST evolve toward:

# Reactive Core + Escalating Cognition

Meaning:

```text
simple tasks stay simple
complex tasks activate deeper cognition
```

NOT:

```text
all tasks go through deep reasoning
```

---

# The Wrong Architectural Direction

The following architecture style is intentionally avoided:

```text
input
 → planner
 → semantic search
 → memory ranking
 → reflection loop
 → multi-agent orchestration
 → execution
 → summarization
 → response
```

This style:

- destroys responsiveness
- increases CPU contention
- increases latency variance
- feels robotic
- scales poorly on local hardware

---

# Architectural Systems Being Deferred / Skipped

# 1. Always-On Multi-Agent Reasoning

## Status

Deferred / intentionally avoided.

---

## Reason

Multi-agent systems:

- multiply inference cost
- create cascading latency
- increase context overhead
- introduce orchestration complexity
- cause unpredictable runtime spikes

On CPU-only systems:

```text
multi-agent orchestration becomes impractical for voice interaction
```

---

## Why Skipping Is Correct

FRIDAY should prioritize:

- deterministic execution
- predictable latency
- stable responsiveness

rather than:

- excessive reasoning depth

---

# 2. Reflection Loops / Self-Critique Per Turn

## Status

Skipped.

---

## Reason

Reflection architectures:

```text
response → evaluate → rewrite → finalize
```

double or triple inference cost.

This is unacceptable for:

- voice-first systems
- low-latency interaction
- CPU-only inference

---

## Why Skipping Is Correct

Voice assistants require:

```text
fast enough + coherent
```

NOT:

```text
academically optimal responses
```

---

# 3. Heavy Embedding Retrieval Every Turn

## Status

Strongly minimized.

---

## Reason

Continuous retrieval:

- increases latency
- increases RAM usage
- creates retrieval overhead
- becomes unnecessary for simple turns

---

## Why Skipping Is Correct

Most voice interactions are:

- short
- local
- deterministic
- immediate

Examples:

- "open chrome"
- "pause music"
- "volume up"
- "write this down"

These should NEVER trigger semantic pipelines.

---

# 4. Planner Activation For Every Turn

## Status

Skipped.

---

## Reason

Planning systems are expensive.

Always-on planning:

- increases inference time
- reduces responsiveness
- harms conversational flow

---

## Why Skipping Is Correct

Incremental planning should activate ONLY for:

- explicit multi-step tasks
- research tasks
- complex workflows
- long-running operations

---

# 5. Giant Unified Context Injection

## Status

Avoided.

---

## Reason

Massive prompts:

- increase token processing
- slow inference dramatically
- increase hallucination risk
- waste CPU cycles

---

## Why Skipping Is Correct

Voice assistants benefit from:

```text
small fast context windows
```

not:

```text
massive conversation dumps
```

---

# 6. Cloud-Dependent Cognition

## Status

Rejected architecturally.

---

## Reason

Cloud cognition:

- destroys offline capability
- introduces unpredictable latency
- creates dependency risks
- introduces cost scaling
- breaks local ownership philosophy

---

# Architectural Systems Approved For Implementation

The following systems provide:

- massive UX improvement
- low inference overhead
- strong continuity gains
- minimal latency impact

---

# 1. Working Artifact Memory

## Status

Strongly recommended.

---

## Why It Is Safe

Artifact memory is:

- lightweight
- deterministic
- in-memory
- O(1) lookup

No semantic search required.

---

## Good Inference Handling Technique

# Passive Memory

DO:

```python
assistant_context.active_artifact
```

DO NOT:

```text
vector search all artifacts every turn
```

---

## Correct Runtime Behavior

Simple pronoun resolution:

```text
"save that"
```

maps directly to:

```text
last_artifact
```

No additional inference required.

---

# 2. Goal Continuity Layer

## Status

Recommended.

---

## Why It Is Safe

Goals are:

- small structured objects
- deterministic
- session-local

---

## Good Inference Handling Technique

# Heuristic Goal Tracking

DO:

```text
maintain explicit active goal state
```

DO NOT:

```text
infer goals through LLM reasoning every turn
```

---

## Correct Runtime Behavior

Use:

```python
active_goal
```

only for:

- continuity
- follow-up interpretation
- workflow consistency

No planner required.

---

# 3. Incremental Planning

## Status

Conditionally recommended.

---

## Why It Is Safe

Planning only activates for:

- multi-step tasks
- explicit workflow requests
- research operations

NOT:

- normal interaction

---

## Good Inference Handling Technique

# Cognitive Escalation

Routing path:

```text
simple task
 → deterministic execution
```

Complex path:

```text
complex task
 → planner activation
```

---

## Correct Runtime Behavior

Planner should remain:

```text
dormant by default
```

---

# 4. Unified Runtime Blackboard

## Status

Recommended.

---

## Why It Is Safe

A runtime blackboard:

- reduces synchronization overhead
- simplifies state access
- avoids duplicated reasoning

This is a state optimization system.

NOT an inference-heavy system.

---

## Good Inference Handling Technique

# Shared Runtime State

Use:

```python
runtime_state
```

instead of repeatedly rebuilding context.

This REDUCES inference overhead.

---

# 5. Streaming Cognitive Feedback

## Status

Strongly recommended.

---

## Why It Is Safe

Streaming improves:

- perceived responsiveness
- conversational realism
- voice interaction quality

without increasing inference cost significantly.

---

## Good Inference Handling Technique

# Parallel Streaming Pipelines

Correct:

```text
STT streaming
while
LLM generating
while
TTS warming
```

Incorrect:

```text
STT complete
 → LLM complete
 → TTS start
```

---

## Correct Runtime Behavior

Emit:

- partial thoughts
- execution updates
- progress signals

through EventBus.

---

# 6. Failure Recovery Intelligence

## Status

Recommended.

---

## Why It Is Safe

Recovery systems are mostly:

- deterministic
- rule-based
- lightweight

---

## Good Inference Handling Technique

# Deterministic Recovery First

DO:

```text
fallback browser
retry execution
repair arguments
```

DO NOT:

```text
invoke planner for every failure
```

---

# 7. Resource-Aware Scheduling

## Status

Strongly recommended.

---

## Why It Is Safe

This IMPROVES responsiveness.

It does not increase inference.

---

## Good Inference Handling Technique

# Dynamic Runtime Policies

Examples:

```text
If CPU overloaded:
   delay background tasks

If voice active:
   prioritize low-latency paths

If RAM pressure high:
   unload secondary models
```

---

# 8. Self-Optimization Feedback Loop

## Status

Partially recommended.

---

## Important Constraint

Optimization must remain:

- asynchronous
- background-only
- low-priority

NEVER:

```text
inline during active conversation
```

---

## Good Inference Handling Technique

# Deferred Optimization

Collect:

- metrics
- failures
- latency data

Analyze later:

- idle state
- background execution
- post-session optimization

---

# Recommended Runtime Architecture

# Fast Path (Default)

This path should handle:

```text
80–90% of interactions
```

Pipeline:

```text
STT
 → deterministic router
 → direct execution
 → TTS
```

Characteristics:

- minimal memory
- no planner
- no semantic retrieval
- low latency
- interruption-safe

---

# Deep Path (Conditional)

Only activate for:

- research
- summarization
- coding
- multi-step workflows
- complex reasoning

Pipeline:

```text
memory
 → planner
 → workflow graph
 → reasoning
 → execution
```

Characteristics:

- slower
- deeper cognition
- user expects delay

---

# Most Important Engineering Principle

For local-first voice assistants:

# Architectural Intelligence > Model Size

A responsive 4B assistant with:

- excellent routing
- interruption handling
- continuity
- low latency
- adaptive execution

will feel significantly smarter than:

- a slow reasoning-heavy system.

---

# Final Architectural Direction

FRIDAY should evolve toward:

# Reactive Deterministic Core

plus

# Conditional Cognitive Escalation

NOT:

# Always-On Heavy Cognition

The assistant should:

- stay fast by default
- become intelligent when necessary
- preserve conversational responsiveness
- maintain offline reliability
- adapt dynamically to hardware constraints

This is the correct architectural direction for:

- CPU-first local inference
- llama.cpp execution
- Qwen3 4B class models
- integrated graphics systems
- voice-native assistants

