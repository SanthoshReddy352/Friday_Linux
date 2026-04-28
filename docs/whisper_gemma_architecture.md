# Architecture Document: Voice-First Local Conversation + MCP-Compatible Capability Layer

## 1. Overview

FRIDAY now targets a voice-first architecture where conversation quality is the primary control plane and tool usage is a capability of that conversation loop. The system keeps reasoning local, uses internal MCP-compatible capability descriptors for tool access, and relies on SQLite + Chroma as a neural-link memory layer.

This replaces the older mental model of:

`audio -> transcript -> intent parser -> tool`

with:

`audio -> session-aware turn manager -> conversation agent -> tool / delegation / reply`

## 2. Core Runtime Components

### 2.1 TurnManager

Owns the active turn lifecycle:
- open or continue session
- track pending online permission
- hand the turn to the conversation agent

### 2.2 ConversationAgent

The single user-facing reasoning agent.

Responsibilities:
- decide whether the turn is chat, local tool use, online proposal, delegation, or clarification
- keep one visible identity and reply style
- remain the only agent the user “talks to”

### 2.3 CapabilityRegistry and CapabilityExecutor

Expose tools through an MCP-compatible internal contract.

Each capability carries:
- connectivity (`local` or `online`)
- latency class
- permission mode
- side-effect level
- schemas and metadata

This lets FRIDAY scale its automation library without hard-coding tool policy into the conversation loop.

### 2.4 DelegationManager

Coordinates specialist agents selectively:
- Planner Agent
- Workflow Agent
- Research Agent
- Memory Curator Agent
- Persona Stylist Agent

Delegation stays off the critical path for ordinary turns.

### 2.5 PersonaManager and MemoryBroker

These services build the context bundle for each turn.

- `PersonaManager` loads the active persona and custom persona definitions
- `MemoryBroker` composes structured and semantic memory from SQLite + Chroma

## 3. Voice and Turn-Taking

The existing voice stack remains local, but it now feeds a richer conversation control plane.

Key direction:
- local STT remains the speech entrypoint
- spoken replies remain local
- follow-up turns should feel session-based rather than like isolated commands
- interruption should preserve conversational continuity instead of forcing command-only behavior

The architecture is ready for a more advanced future split into dedicated audio frontend, wake-word, VAD, ASR, barge-in, and persistent TTS services.

## 4. Local Models and Tool Use

FRIDAY continues to use local models for reasoning and language generation.

Guiding rules:
- hosted reasoning models are out of scope
- tools and online skills are capabilities, not separate assistant identities
- the conversation layer decides when capabilities are needed

Simple requests should resolve directly.
Complex multi-step requests may be delegated internally, but the user still hears one coherent FRIDAY voice.

## 5. Neural-Link Memory Design

### SQLite

Used for:
- personas
- conversation session state
- structured profile facts
- workflow state
- online permission history

### Chroma

Used for:
- semantic recall
- episodic memories
- persona style examples
- prior response examples

### Retrieval Flow

For each turn:
1. load active persona
2. load structured session/profile state from SQLite
3. retrieve semantic and episodic recall from Chroma
4. build a compact context bundle for the conversation agent
5. curate long-term memories after the response

## 6. Online Capability Policy

FRIDAY is now local-model-first, not offline-only.

Policy:
- local reasoning remains mandatory
- online skills are allowed
- online capabilities are tagged explicitly in the capability registry
- ask-before-online is the default behavior unless the user explicitly requested online access

Examples:
- browser automation
- current weather
- web lookup
- future online automations

## 7. Implementation Notes

The current codebase now includes:
- `CapabilityRegistry`
- `CapabilityExecutor`
- `ConversationAgent`
- `TurnManager`
- `DelegationManager`
- `PersonaManager`
- `MemoryBroker`

These run alongside the existing router and workflow system so FRIDAY can evolve incrementally instead of requiring a destructive rewrite.

## 8. Why This Architecture

This design improves FRIDAY in two ways at once:

### Better conversational flow
- one visible assistant identity
- turn-aware behavior
- persona-guided responses
- lower architectural pressure to expose routing machinery

### Better automation scale
- cleaner tool metadata
- ask-before-online policy
- capability discovery
- easier future support for large skill libraries and real MCP-style providers
