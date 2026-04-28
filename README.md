# FRIDAY - Local-Model-First Desktop Assistant

FRIDAY is a voice-first AI desktop assistant for Linux that keeps reasoning local while scaling automation through an internal MCP-compatible capability layer. The goal is not just “tool calling,” but a smooth assistant that can chat naturally, manage workflows, and selectively use online skills when the user wants current information or web-connected actions.

## Key Features

- **Natural conversation loop** powered by a main conversational agent, session-aware turn handling, and persona-guided replies.
- **Local model reasoning** for chat, planning, and tool use with no hosted reasoning dependency.
- **MCP-compatible capability registry** for clean tool metadata, permission policy, and future expansion to richer skill libraries.
- **Hybrid online skills** for browser automation and live information, with ask-before-online consent by default.
- **Neural-link memory** using SQLite for structured identity/session data and Chroma for semantic recall and persona style examples.
- **Custom personas** with persistent tone, behavior, and conversational examples.

## Architecture Snapshot

- `TurnManager` owns the turn lifecycle.
- `ConversationAgent` is the single user-facing identity.
- `CapabilityRegistry` and `CapabilityExecutor` expose tools as MCP-style capabilities.
- `DelegationManager` selectively invokes specialist agents for planning, workflows, research, memory curation, and persona styling.
- `PersonaManager` and `MemoryBroker` build the context bundle for each turn from SQLite + Chroma.

## Voice Runtime Notes

- STT now keeps a short wake-session window so natural follow-ups do not need the wake word every turn.
- Assistant-echo suppression is limited to a short post-TTS window instead of blocking repeated phrases indefinitely.
- TTS prefers PipeWire-native playback via `pw-cat` when available and falls back to `aplay`.
- You can tune `conversation.wake_session_timeout_s` and `conversation.assistant_echo_window_s` in [`config.yaml`](/home/tricky/Friday_Linux/config.yaml:5).

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/SanthoshReddy352/FRIDAY.git
   cd FRIDAY
   ```
2. Run setup:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
3. Download the local models described in [SETUP_GUIDE.md](SETUP_GUIDE.md).
4. Launch FRIDAY:
   ```bash
   source .venv/bin/activate
   python main.py
   ```

## Documentation

- [SETUP_GUIDE.md](SETUP_GUIDE.md)
- [docs/prd.md](docs/prd.md)
- [docs/whisper_gemma_architecture.md](docs/whisper_gemma_architecture.md)

## License

This project is licensed under the MIT License.
