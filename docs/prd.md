# FRIDAY — Product Requirements Document

> **Project Name**: FRIDAY (Free, Responsive, Intelligent Digital Assistant for You)  
> **Version**: 0.2  
> **Date**: April 2026

## 1. Product Overview

FRIDAY is a voice-first desktop assistant that prioritizes natural conversation, local-model reasoning, and scalable automation. It runs its reasoning stack locally, keeps a persistent neural-link memory using SQLite and Chroma, and uses an MCP-compatible capability layer so FRIDAY can grow into a large skill ecosystem without losing conversational flow.

FRIDAY is not designed as a “tool bot” that happens to chat. The main product goal is a human-feeling assistant that can:
- talk naturally through short, smooth turns
- remember preferences and context
- execute local tasks reliably
- selectively use online skills for live/current information
- scale into many automations without becoming architecturally messy

## 2. Goals

- Deliver a voice-first assistant with low-friction conversational turn-taking.
- Keep all planning and language generation on local models.
- Support both local and online skills through a unified MCP-compatible capability interface.
- Preserve a single visible assistant identity even when internal specialist agents are used.
- Use SQLite + Chroma as a layered neural-link memory for user profile, persona, episodic recall, and style guidance.
- Support fully custom personas while keeping one active persona visible at a time.
- Keep the system modular enough for large-scale automation growth.

## 3. Non-Goals

- Hosted reasoning models as a required dependency.
- Always-on multi-agent fan-out for every user turn.
- Replacing the main conversational identity with tool- or agent-specific voices.
- Day-one requirement that every skill be a standalone external MCP server.

## 4. Experience Targets

### 4.1 Conversational Flow

- FRIDAY should feel like one continuous assistant, not a router exposing internal machinery.
- Short spoken acknowledgements should be available before slow actions.
- Simple requests should not trigger visible over-planning or multi-agent chatter.
- Clarifying questions should be short and specific.

### 4.2 Automation

- Local automations should remain fast and deterministic.
- Online skills should be available for current information, browser actions, and live services.
- Online access should be mediated by capability metadata and ask-before-online policy by default.

### 4.3 Memory and Persona

- FRIDAY should persist structured user preferences and facts in SQLite.
- FRIDAY should retrieve episodic and stylistic memories from Chroma.
- Personas should affect acknowledgements, chat tone, and tool-result phrasing.

## 5. Architecture Requirements

### 5.1 Main Conversational Agent

FRIDAY must expose one main voice-facing agent that:
- owns tone, persona, and surface replies
- manages the active conversation session
- decides among chat, tool execution, clarification, online proposal, or delegation
- remains the only visible identity the user speaks with

### 5.2 MCP-Compatible Capability Layer

FRIDAY must use an internal MCP-compatible capability model for tools, skills, and automations.

Every capability should expose:
- name
- description
- connectivity: `local | online`
- latency class
- permission policy
- side-effect level
- streaming support
- input schema
- output schema

The initial implementation may remain in-process, but the interfaces must be compatible with future external MCP-style providers.

### 5.3 Selective Specialist Agents

FRIDAY may use specialist agents behind the main agent, but only selectively.

Planned specialist roles:
- Planner Agent
- Workflow Agent
- Research Agent
- Memory Curator Agent
- Persona Stylist Agent

Rules:
- simple chat stays single-agent
- simple local actions stay single-agent
- complex workflows or long-running tasks may delegate
- the main agent always produces the user-facing reply

### 5.4 Neural-Link Memory

Use SQLite + Chroma as a layered memory system.

SQLite responsibilities:
- user profile
- persona definitions
- conversation session state
- structured long-term facts
- workflow/task state
- online-permission history

Chroma responsibilities:
- semantic recall
- episodic memory
- persona style examples
- prior good assistant responses
- automation summaries

## 6. Runtime Flow

1. Voice stack captures and transcribes speech locally.
2. `TurnManager` opens or continues the active session.
3. `ConversationAgent` builds a turn plan.
4. The plan may choose:
   - conversational reply
   - local tool execution
   - online skill proposal
   - specialist-agent delegation
   - clarification
5. `CapabilityExecutor` runs MCP-compatible capabilities when needed.
6. `DelegationManager` coordinates specialist agents only for complex cases.
7. `MemoryCuratorAgent` writes durable memory candidates back to SQLite + Chroma.

## 7. Core Interfaces

### 7.1 CapabilityDescriptor

- `name`
- `description`
- `connectivity`
- `latency_class`
- `permission_mode`
- `side_effect_level`
- `streaming`
- `input_schema`
- `output_schema`

### 7.2 TurnPlan

- `mode`
- `tool_calls`
- `delegation`
- `online_required`
- `user_ack`
- `final_response_style`

### 7.3 DelegationRequest

- `agent_type`
- `task`
- `context_bundle`
- `timeout_ms`

### 7.4 DelegationResult

- `summary`
- `structured_output`
- `memory_candidates`
- `confidence`

## 8. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Startup usability | < 3 seconds to usable UI |
| Local action latency | ~instant to low-latency |
| Conversation feel | no robotic route-announcing for simple turns |
| Offline usefulness | core assistant remains useful without internet |
| Online consent | ask first by default for online capabilities |
| Extensibility | new capabilities added without rewriting the conversation core |

## 9. Implementation Status in This Repo

The current implementation now includes:
- internal MCP-compatible capability registry and executor
- main conversation agent and turn manager
- selective delegation manager with planner, workflow, research, memory-curation, and persona-styling roles
- persona management backed by SQLite
- neural-link memory helpers backed by SQLite + Chroma
- online ask-before-consent flow

## 10. Future Extensions

- external MCP server adapters
- richer wake-word session handling
- persistent streaming TTS runtime
- UI for persona creation and selection
- more online capabilities with explicit permission tiers
