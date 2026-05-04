# FRIDAY Automation Roadmap

A backlog of productivity tools and automations to grow FRIDAY from a voice
front-end into a daily driver. Items are grouped by leverage and ordered for
implementation. Each entry lists what it does, why it matters, and the rough
shape of the implementation on this codebase.

## Tier 1 — high daily leverage  *(✅ shipped)*

All five Tier 1 items are merged. Manual test cases live in
`docs/manual_testing_guide.md` sections 13a–13e.

### 1. Window / workspace control — `modules/window_manager` *(✅ done)*
- Tool: `window_action` (single tool, action arg).
- Actions shipped: `tile_left|right|top|bottom`, `maximize`, `unmaximize`,
  `minimize`, `restore`, `fullscreen`, `unfullscreen`, `close`, `focus`,
  `minimize_others`, `send_to_workspace`, `go_to_workspace`,
  `send_to_monitor`.
- Voice covered: "tile firefox to the left", "send this to monitor 2",
  "throw firefox to display 1", "go to workspace 3",
  "minimize everything but the editor", "fullscreen this", "switch to the
  editor window", "close this window".
- Backed by `wmctrl` (move/state/workspace), `xdotool` (active-window +
  minimize), and `xrandr --query` for monitor geometry. Falls back
  gracefully when any of the three is missing.
- Tests: `T-13a.1`–`T-13a.11` and the new monitor case in section 13a.

### 2. Dictation mode — `modules/dictation` *(✅ done)*
- Tools: `start_dictation`, `end_dictation`, `cancel_dictation`.
- During an active session the STT plugin skips wake-word / media-gate
  filters and routes raw transcripts into the in-memory buffer; only
  `end memo` / `cancel memo` phrases re-enter the normal pipeline.
- Memos saved to `~/Documents/friday-memos/<YYYY-MM-DD_HHMM>_<slug>.md`
  with a Markdown header, recorded timestamp, and normalized body.
- Tests: `T-13b.1`–`T-13b.7`.

### 3. Focus session / Pomodoro — `modules/focus_session` *(✅ done)*
- Tools: `start_focus_session`, `end_focus_session`,
  `focus_session_status`. Backed by the upgraded
  `core/reasoning/workflows/focus_mode.py`.
- On start: mutes GNOME notifications (`gsettings org.gnome.desktop.
  notifications show-banners false`), pauses the active browser media
  session, schedules a single end-of-session timer (1–240 min), records
  the previous banner state for restore.
- On end / timer fire: restores notifications, announces "session
  complete after N minutes". Re-entry while active reports remaining
  time instead of restarting.
- Tests: `T-13c.1`–`T-13c.7`.

### 4. Calendar event creation — `modules/task_manager` *(✅ done)*
- Tools: `create_calendar_event`, `move_calendar_event`,
  `cancel_calendar_event`, plus the existing `list_calendar_events`.
- Voice covered: "create a calendar event titled standup tomorrow at 10",
  "schedule a meeting in 15 minutes", "move my 3 PM to 4",
  "shift the gym block by 2 hours", "reschedule the standup to tomorrow
  morning", "cancel the next event", "cancel the gym block on Friday".
- Storage: rows in the existing `calendar_events` SQLite table; system
  notifications + in-process timers re-armed on reschedule, cancelled on
  delete. (`.ics` export remains a future enhancement.)
- Tests: `T-13d.1`–`T-13d.8`.

### 5. Screen reader / OCR — `modules/screen_text` *(✅ done)*
- Tools: `read_selection`, `ocr_region`.
- `read_selection` pulls the X primary selection via `xclip -selection
  primary -o` (truncated to 4 KB).
- `ocr_region` captures with `gnome-screenshot -a` (falls back to
  `flameshot gui --raw` or ImageMagick `import`), runs `tesseract` with
  `--psm 6`, deletes the temp PNG. Output truncated to 4 KB.
- Voice covered: "read the highlighted text", "what does this say",
  "OCR the selection", "extract text from this region", "read what's on
  the screen".
- Tests: `T-13e.1`–`T-13e.7`.

## Tier 2 — clear value, slightly bigger lift

### 6. Clipboard memory
- Voice-addressable clipboard history. "save this as 'address'", "paste my
  address", "what did I copy ten minutes ago".
- Stack: `xclip` watcher + small SQLite store under
  `~/.local/share/friday/clipboard.db`. Hooks into `manage_file` for "save
  clipboard to file".

### 7. Project / repo agent — `modules/project_agent`
- Voice: "what changed today in friday-linux", "summarize my staged diff",
  "open the file with the most churn this week", "draft a commit message
  for the staged changes".
- Stack: shell out to `git log/diff/status/blame`; feed Qwen-7B (the tool
  model) tight prompts. Strong fit since the user is on a dev machine.

### 8. Quick translate / define / convert
- Voice: "translate 'thank you' to Japanese", "define entropy",
  "47 USD in INR", "28 times 47".
- Stack: calculator + unit conversion via `pint`; offline dictionary
  (`dict` / `wordnet`); translate is online-gated through the existing
  consent service.

### 9. Email triage helper
- Already reads email; extend to "summarize my unread", "draft a reply
  saying I'll be late", "archive promo emails". Online-gated.

### 10. Smart paste / snippets
- "insert my email signature", "paste the meeting agenda template".
  Templates live in `~/.config/friday/snippets/*.md`, pasted via
  `xdotool type --delay 5 -- "$(cat snippet)"` or clipboard.

## Tier 3 — uniqueness plays

### 11. Routine builder
- User-defined YAML macros: "good morning routine" runs weather + calendar
  + unread email + favorite playlist; "shutdown" closes apps and turns off
  monitors. Routines under `~/.config/friday/routines/*.yaml`, registered
  dynamically.

### 12. Meeting copilot
- When Zoom / Google Meet / Slack call is foregrounded: auto-pause music,
  start dictation, save the transcript with timestamps and an action-item
  list at the end.

### 13. Watch-and-notify
- "tell me when build #1234 turns green", "ping me when this download
  finishes", "watch this folder for new PDFs". Polling jobs scheduled
  through the existing TaskManager.

### 14. Voice memory recall
- "Friday what did I tell you about X yesterday?" Surface the chroma-backed
  memory broker conversationally instead of only as routing context.

### 15. Live-coding assistant mode
- When an editor is foregrounded, "explain this function", "write a test
  for it", "make it a one-liner". Reads selection via `xclip`, uses the
  tool LLM (Qwen-7B already loaded).

## Cross-cutting follow-ups

- Replace the "world monitor for top 3 stories" intent so the *N* filter is
  honored (currently ignored — the briefing always returns all items).
- Tighten the conversational fallback further: short queries should never
  pull in semantic recall, durable memory, or workflow summary headers
  (already partially fixed; revisit once usage data shows remaining
  latency tail).
- Wire OCR / screen-reader output through the response finalizer so
  voice-spoken results stay in the existing TTS pipeline.
