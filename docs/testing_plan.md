# Comprehensive FRIDAY Testing Plan

This robust testing plan covers every possible routing path, intent, fallback mechanism, and dialogue state transition managed by `core/router.py`, `core/intent_recognizer.py`, and the workflow orchestrator. Execute these tests to validate the assistant's logic comprehensively.

## Phase 1: Core System & Fallback Routing
**Validating `router.process_text` flow, transcript cleaning, and fallbacks.**

1. **Transcript Cleaning Test**
   - **Action:** Say "Tell me tell me what is the time".
   - **Expected:** Stutters are removed. Matches `get_time`.
2. **Compound Actions (Multi-Clause)**
   - **Action:** "Take a screenshot and then check the battery."
   - **Expected:** `IntentRecognizer` splits on `and then`. Calls `take_screenshot` followed by `get_battery`.
3. **LLM Tool Routing Fallback**
   - **Action:** Ask something ambiguous that requires tool args, e.g., "Add 5 apples to my shopping list" (Assuming a generic note/file tool exists).
   - **Expected:** Fails deterministic fast-path -> Routes to Qwen Tool LLM (`get_tool_llm`) -> Extracts JSON args -> Executes tool.
4. **Conversational LLM Chat Fallback**
   - **Action:** Say "What is the meaning of life?"
   - **Expected:** Fails all tool checks -> Drops to final fallback -> `llm_chat` responds using Gemma.
5. **Fuzzy Matching / Alias Fallback**
   - **Action:** Say a slight typo or alias of an existing tool (if aliases are defined).
   - **Expected:** Matches via `difflib.get_close_matches` in `_keyword_fallback`.

## Phase 2: Dialogue State & Clarifications
**Validating stateful routing (`RoutingState`, pending selections).**

6. **Pending Clarification (Meant / Did you mean)**
   - **Action:** Trigger an ambiguous command where the assistant asks "Is that what you meant?"
   - **Action (Follow-up):** Say "No" (`confirm_no`).
   - **Expected:** Triggers cancel message "Okay. Please say it again in a different way."
7. **Pending Clarification (YouTube search)**
   - **Action:** Trigger the prompt "Would you like me to search for X on YouTube?"
   - **Action (Follow-up):** Say "Yes" (`confirm_yes`).
   - **Expected:** Automatically formats routing as `play X in youtube` and routes to `play_youtube`.
8. **File Candidate Selection**
   - **Action:** Search for a file with multiple results (e.g. "Find report"). Assistant says "I found multiple... which one?"
   - **Action (Follow-up):** Say "Option 2" or "The PDF one" or "That one".
   - **Expected:** `_parse_pending_selection` resolves to `select_file_candidate`.

## Phase 3: All Intent Recognizer Domains
**Testing all deterministic regex parsing defined in `intent_recognizer.py`.**

### 3.1 Browser & Media Control
9. **Direct URL / Application**
   - **Action:** "Open YouTube" -> Routes to `open_browser_url` (youtube.com).
   - **Action:** "Open YouTube Music" -> Routes to `open_browser_url` (music.youtube.com).
10. **Play Music / Video**
    - **Action:** "Play Lo-Fi Girl on YouTube" -> `play_youtube`
    - **Action:** "Play The Beatles in YouTube Music" -> `play_youtube_music`
    - **Action:** "Open YouTube and play Interstellar theme" -> Splits -> `play_youtube`
11. **Contextual Media Control**
    - **Action:** While media is playing, say "Next", "Skip", "Forward 10 seconds", "Rewind 5 seconds", "Pause", "Stop".
    - **Expected:** Maps to `browser_media_control` with args (`next`, `forward`, `backward`, `pause`).
    - **Action:** Say "Music instead".
    - **Expected:** Switches active workflow query to `play_youtube_music`.

### 3.2 Volume Control
12. **Absolute vs Relative Volume**
    - **Action:** "Set the volume to 50 percent" -> `set_volume` (percent=50).
    - **Action:** "Increase volume by 3 steps" -> `set_volume` (direction=up, steps=3).
    - **Action:** "Mute" / "Unmute" -> `set_volume` (direction=mute/unmute).

### 3.3 System & Hardware
13. **Status Checks**
    - **Action:** "System info" or "System health" -> `get_system_status`
    - **Action:** "Battery status" -> `get_battery`
    - **Action:** "Check CPU usage" -> `get_cpu_ram`

### 3.4 Time, Date, & Reminders
14. **Time & Reminders**
    - **Action:** "What time is it?" -> `get_time`
    - **Action:** "Today's date" -> `get_date`
    - **Action:** "Set a reminder" -> `set_reminder`

### 3.5 Screen & Camera
15. **Vision**
    - **Action:** "Take a screenshot" -> `take_screenshot`
    - **Action:** "What do you see through the camera?" -> Should invoke `vision_skill` or `camera_skill`.

### 3.6 Application Launching
16. **App Extraction**
    - **Action:** "Launch Firefox" or "Open Calculator" -> `launch_app` (args: [firefox/calculator]).
    - **Action:** "Launch Firefox and Calculator" -> `launch_app` (multi-app).

### 3.7 Voice & Mic Control
17. **Voice Modes**
    - **Action:** "Set voice mode to always on" -> `set_voice_mode` (persistent).
    - **Action:** "Set voice mode to manual" -> `set_voice_mode` (manual).
    - **Action:** "Disable the mic" -> `disable_voice`.
    - **Action:** "Friday wake up" -> `enable_voice` (wake_up=True).

### 3.8 Notes & Helpers
18. **Notes Management**
    - **Action:** "Save note" or "Remember this" -> `save_note`
    - **Action:** "Read my notes" -> `read_notes`
19. **Greeting & Help**
    - **Action:** "Hello Friday" -> `greet`
    - **Action:** "What else can you do?" -> `show_help`
    - **Action:** "Goodbye" -> `shutdown_assistant`

## Phase 4: Complex File Management Routings
**Testing advanced contextual file operations.**

20. **Search & Open**
    - **Action:** "Search for config file" -> `search_file`.
    - **Action:** "Open the config.yaml file" -> `open_file`.
    - **Action:** "Open the folder" -> `open_folder`.
21. **Contextual Read/Summarize**
    - **Action:** While a file is selected/active, say "Read it" -> `read_file` (auto-passes active filename).
    - **Action:** "Summarize it" -> `summarize_file`.
22. **Manage File (Creation & Writing)**
    - **Action:** "Create a file called log.txt" -> `manage_file` (action=create, filename=log.txt).
    - **Action:** "Write to the log.txt file" -> `manage_file` (action=write, filename=log.txt).
    - **Action:** "Append to the file" (while active context exists) -> `manage_file` (action=append, filename=[active]).

## Phase 5: Additional Skills & Tools
**Testing all individual skill modules.**

### 5.1 Weather & Location
23. **Weather Operations** (`skills/weather_ops.py`)
    - **Action:** "What is the weather like in London?" -> `get_weather`
    - **Action:** "What's the weather here?" -> `get_current_location_weather`

### 5.2 Memory Management
24. **Memory Operations** (`skills/memory_ops.py`)
    - **Action:** "Remember that my passport is in the top drawer." -> `remember_fact`
    - **Action:** "Where is my passport?" -> `retrieve_memory`
    - **Action:** "What do you remember?" -> `list_all_memories`
    - **Action:** "Forget the fact about my passport." -> `forget_fact`

### 5.3 Web & Search
25. **Web Search** (`skills/web_ops.py`)
    - **Action:** "Google search for the latest tech news." -> `google_search`

### 5.4 Communication
26. **WhatsApp** (`skills/whatsapp_skill.py`)
    - **Action:** "Send a WhatsApp message to Alice saying I will be late." -> `send_whatsapp_message`

### 5.5 Advanced Vision & Camera
27. **Photos & Live Vision** (`skills/camera_skill.py`, `skills/gemini_live_skill.py`, `skills/vision_skill.py`)
    - **Action:** "Take a photo of me." -> `take_photo`
    - **Action:** "Start live vision." -> `start_live_vision`

### 5.6 Object Detection & Environment Monitoring
28. **Background Monitoring** (`skills/detection_skill.py`, `skills/clap_control_skill.py`, `modules/world_monitor/`)
    - **Action:** "Detect objects in the room." -> `detect_objects`
    - **Action:** "Toggle the clap trigger." -> `toggle_clap_trigger`
    - **Action:** Simulate a world event -> System auto-announces via `get_world_monitor_news`

## Phase 6: Workspace Agent & Integration Suites
**Testing GSuite, Email, and Calendar integrations.**

29. **Email Processing** (`modules/workspace_agent/`, `skills/email_ops.py`)
    - **Action:** "Check my unread emails." -> `check_unread_emails`
    - **Action:** "Read my latest email." -> `read_email` / `get_recent_emails`
30. **Calendar Management** (`modules/workspace_agent/`, `modules/task_manager/`)
    - **Action:** "What's on my calendar today?" -> `get_calendar_today` / `list_calendar_events`
    - **Action:** "Create an event called Team Meeting for tomorrow at 2 PM." -> `create_calendar_event`
    - **Action:** "Show my calendar for the week." -> `get_calendar_week`
    - **Action:** "What's my agenda?" -> `get_calendar_agenda`
31. **Google Drive Integration** (`modules/workspace_agent/`)
    - **Action:** "Search drive for Q3 Report." -> `search_drive`
32. **Daily Briefing**
    - **Action:** "Give me my daily briefing." -> `daily_briefing`

## Phase 7: Workflow Orchestrator & Agents
**Validating multi-step delegation.**

33. **Delegation / Long-running tasks**
    - **Action:** "Research Python 3.13 and write a summary to file."
    - **Expected:** Routed to workspace agent / task manager. Workflow orchestrator should store `session_id`, loop through tools without breaking the routing chain, and return final output upon task completion.
