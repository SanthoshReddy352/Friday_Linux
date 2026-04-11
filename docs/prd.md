# FRIDAY — Product Requirements Document (PRD)

> **Project Name**: FRIDAY (Free, Responsive, Intelligent Digital Assistant for You)
> **Version**: 0.1 (Initial Planning)
> **Date**: April 2026

---

## 1. Overview

FRIDAY is a modular, offline, AI-powered personal assistant for desktop — inspired by the FRIDAY AI from the Iron Man series. It is designed to run entirely **free of cost**, with **no external API dependencies**, and be lightweight enough for mid-range consumer laptops.

### 1.1 Goals

- Provide a voice-and-text-driven assistant for everyday laptop tasks
- Run 100% offline — no cloud services, no paid APIs
- Modular architecture so features can be added/removed independently
- Cross-platform support (Linux & Windows)
- Polished PyQt5 GUI with a sci-fi / cyberpunk aesthetic

### 1.2 Non-Goals (for now)

- Mobile/web interface
- Cloud/online features (weather, web search)
- GPU-accelerated inference (no discrete GPU available)

---

## 2. Target Hardware

| Spec | Value |
|---|---|
| **Device** | Lenovo IdeaPad Slim 3i |
| **CPU** | Intel i5-13th Gen (H-series, 12 threads) |
| **RAM** | 16 GB |
| **GPU** | Intel UHD (integrated) — CPU-only inference |
| **OS** | Dual-boot: Linux + Windows |

> [!NOTE]
> With 16GB RAM and a 13th-gen i5 H-series, we can comfortably run small LLMs (1-3B params) via `llama-cpp-python` on CPU threads. Expect ~5-15 tokens/sec for TinyLlama 1.1B.

---

## 3. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.10+ | User preference, rich ecosystem |
| **GUI** | PyQt5 | Native desktop feel, cross-platform |
| **Speech-to-Text** | Vosk | Lightweight offline STT (~50MB models) |
| **Text-to-Speech** | pyttsx3 (initial), Piper TTS (upgrade) | Offline, zero cost |
| **Local LLM** | llama-cpp-python + GGUF models | CPU-friendly, no GPU required |
| **System Control** | subprocess, psutil, pyautogui | App launching, system info, automation |
| **Scheduling** | APScheduler | Reminders, timed tasks |
| **Data Storage** | SQLite | Local, zero-config, lightweight |
| **Packaging** | PyInstaller (optional) | Single executable distribution |

---

## 4. Feature Requirements

### 4.1 Core Framework (Phase 1)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| C1 | Plugin System | High | Load/unload feature modules dynamically |
| C2 | Command Router | High | Parse user input → route to correct module |
| C3 | Config Manager | High | YAML/JSON config, per-module settings |
| C4 | Logging | Medium | Structured logging to file + console |
| C5 | Event Bus | Medium | Modules communicate via events |

### 4.2 GUI (Phase 1)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| G1 | Chat Interface | High | Scrollable chat with user/assistant bubbles |
| G2 | Text Input | High | Type commands, press Enter to send |
| G3 | Status Indicators | Medium | Mic status, listening state, processing |
| G4 | System Tray | Medium | Minimize to tray, quick access |
| G5 | Theme | Medium | Dark/sci-fi theme inspired by Iron Man HUD |

### 4.3 System Commands (Phase 2)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| S1 | App Launcher | High | Open apps by name ("open Firefox") |
| S2 | System Info | High | CPU, RAM, battery, disk usage |
| S3 | File Search | Medium | Find files by name/extension |
| S4 | Volume Control | Medium | Set/get system volume |
| S5 | Brightness Control | Medium | Adjust screen brightness |
| S6 | Screenshot | Low | Capture screen and save |

### 4.4 Voice I/O (Phase 3)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| V1 | Speech-to-Text | High | Continuous listening with wake word |
| V2 | Text-to-Speech | High | Speak responses aloud |
| V3 | Wake Word | Medium | Activate with "Hey Friday" |
| V4 | Mic Selector | Low | Choose input device |

### 4.5 Conversational AI (Phase 4)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| A1 | Local LLM Chat | High | General Q&A via small local model |
| A2 | Context Memory | Medium | Remember conversation within session |
| A3 | Persona | Medium | FRIDAY personality in responses |
| A4 | Intent Extraction | Medium | LLM extracts structured commands from natural speech |

### 4.6 Task Automation (Phase 5)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| T1 | Reminders | High | "Remind me to X in 30 minutes" |
| T2 | Clipboard Manager | Medium | History of copied text |
| T3 | Quick Notes | Medium | Save/retrieve text notes |
| T4 | Scheduled Tasks | Low | Run commands at set times |

### 4.7 Advanced Features (Phase 6)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| X1 | Window Manager | Low | Move/resize/close windows by voice |
| X2 | Media Control | Low | Play/pause/next on media players |
| X3 | Custom Macros | Low | User-defined command chains |

---

## 5. Non-Functional Requirements

| Requirement | Target |
|---|---|
| **Startup Time** | < 3 seconds to usable GUI |
| **Memory Usage** | < 500MB idle (without LLM loaded) |
| **LLM Memory** | < 2GB when LLM is active |
| **Response Latency** | < 1s for system commands, < 10s for LLM |
| **Cross-Platform** | Works on both Linux and Windows |
| **Offline** | 100% functional without internet |
| **Extensibility** | New modules addable without modifying core |

---

## 6. Architecture Overview

```
┌──────────────────────────────────────────┐
│              PyQt5 GUI                   │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Chat View│  │ Status   │  │ Tray   │ │
│  └────┬─────┘  └──────────┘  └────────┘ │
│       │                                  │
├───────┴──────────────────────────────────┤
│           Command Router                 │
│   (text input → intent → module)         │
├──────────────────────────────────────────┤
│              Event Bus                   │
├─────┬─────┬──────┬──────┬───────┬────────┤
│Voice│Sys  │LLM   │Tasks │Notes  │  ...   │
│ IO  │Ctrl │Chat  │Sched │Mgr    │Plugins │
├─────┴─────┴──────┴──────┴───────┴────────┤
│         Config  │  Logger  │  DB (SQLite) │
└──────────────────────────────────────────┘
```

---

## 7. Constraints & Risks

| Risk | Mitigation |
|---|---|
| LLM may be slow on CPU | Use quantized GGUF models (Q4_K_M), start with TinyLlama 1.1B |
| Vosk accuracy may be limited | Allow text fallback, tunable language models |
| Cross-platform system commands differ | Abstract OS-specific code behind interfaces |
| 16GB RAM limits model size | Stay within 1-3B param models, lazy-load LLM |
| No internet by default | Clearly separate online/offline modules |

---

## 8. Project Structure (Planned)

```
FRIDAY/
├── main.py                   # Entry point
├── config.yaml               # Global configuration
├── requirements.txt
├── core/
│   ├── __init__.py
│   ├── app.py                # Application lifecycle
│   ├── router.py             # Command routing
│   ├── event_bus.py          # Inter-module events
│   ├── config.py             # Config loader
│   ├── logger.py             # Logging setup
│   └── plugin_manager.py     # Plugin loading
├── gui/
│   ├── __init__.py
│   ├── main_window.py        # Main PyQt5 window
│   ├── chat_widget.py        # Chat display
│   ├── input_widget.py       # Text input bar
│   ├── status_bar.py         # Status indicators
│   ├── tray.py               # System tray
│   └── styles/
│       └── dark_theme.qss    # Stylesheet
├── modules/
│   ├── __init__.py
│   ├── system_control/       # Phase 2
│   ├── voice_io/             # Phase 3
│   ├── llm_chat/             # Phase 4
│   ├── task_manager/         # Phase 5
│   └── advanced/             # Phase 6
├── data/
│   └── friday.db             # SQLite database
├── models/                   # Downloaded model files
│   ├── vosk-model-small/
│   └── tinyllama.gguf
└── tests/
    ├── test_router.py
    ├── test_plugins.py
    └── ...
```
