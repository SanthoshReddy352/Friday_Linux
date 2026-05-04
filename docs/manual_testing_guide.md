# FRIDAY Manual Testing Guide

A scenario-by-scenario walkthrough of every capability and user flow FRIDAY
exposes today. Use this when smoke-testing a build, when checking a new
device, or when validating a regression-fix branch end-to-end.

> Read top-to-bottom for a full session, or jump to a section when you only
> care about one feature. Each test lists the exact phrasing to say (or
> type), the precondition state, and the pass/fail criteria.

---

## How to use this guide

1. **Launch FRIDAY** in the project root:
   ```
   python main.py
   ```
   Wait for the GUI to appear and the log to show
   `FRIDAY initialized successfully`.

2. **Pick an input mode**. Most scenarios assume **voice**. To use text
   instead, type into the chat box in the GUI; the same routing applies.

3. **Mark each test pass or fail in your scratch notes.** A test passes when
   the bold "expect" line is satisfied — both the spoken response *and* any
   side-effect (file written, browser tab opened, system action taken).

4. **Reset state between sections** unless a section explicitly chains
   ("after the previous test…"). To reset, say "Friday cancel" or close and
   relaunch.

### Conventions

- **You say:** `"Friday <command>"` — the literal voice/text input.
- **Expect:** what should happen.
- **Pass criteria:** what proves the test succeeded.
- A leading `[T-N]` is a stable test ID for cross-referencing in PRs.

---

## 0. Pre-flight checks

Before running scenarios, confirm:

- [ ] `python main.py` boots without errors in `logs/friday.log`.
- [ ] The GUI window appears.
- [ ] Microphone status indicator shows a live state ("listening", "armed",
      or "muted") rather than "error".
- [ ] First wake utterance ("Friday hello") gets a response.
- [ ] `gws --help` works in your shell (Workspace tests need it).
- [ ] `playwright` is installed if you plan to run browser-automation tests.
- [ ] Optional: open `logs/friday.log` in a tail window so you can watch
      transcripts and routing decisions live:
      ```
      tail -f logs/friday.log
      ```

---

## 1. Wake word, listening modes, and barge-in

### [T-1.1] Wake-word activation
**Listening mode:** `wake_word`
**You say:** `"Friday."` (alone, then pause)
**Expect:** FRIDAY emits a soft acknowledgement or simply opens the mic. The
runtime state should switch from `armed` → `listening` for the wake-session
window (12 s by default).
**Pass:** GUI shows `listening` after the wake-word; subsequent utterances
within 12 s are processed without needing "Friday" again.

### [T-1.2] Persistent listening
**Listening mode:** `persistent`
**You say:** `"What time is it?"` (no wake word)
**Expect:** Spoken time response.
**Pass:** Time announced.

### [T-1.3] On-demand listening
**Listening mode:** `on_demand`
**You say:** `"Friday open calculator."`
**Expect:** Mic opens for one turn, calculator launches, mic mutes again.
**Pass:** State sequence `armed → listening → muted` in the runtime log.

### [T-1.4] Manual listening
**Listening mode:** `manual`
**You say:** Anything without first toggling the mic in the GUI.
**Expect:** Nothing is processed.
**You then:** Click the mic button and speak.
**Pass:** Only the post-button utterance reaches the assistant.

### [T-1.5] Switching modes by voice
**You say (in order):**
1. `"Friday set voice mode to wake word."`
2. `"Friday set voice mode to persistent."`
3. `"Friday set voice mode to on demand."`
4. `"Friday set voice mode to manual."`

**Expect:** Each command updates `config.yaml → conversation.listening_mode`
and FRIDAY responds with a short confirmation.
**Pass:** `python -c "from core.config import ConfigManager; c=ConfigManager(); c.load(); print(c.get('conversation.listening_mode'))"`
matches the last setting.

### [T-1.6] Disable / enable voice
**You say:** `"Friday disable voice."` (mic mutes)
**Then:** `"Friday enable voice."` (mic re-opens — you may need to use the
GUI button first if the mic is fully closed).
**Pass:** Toggle works without restarting.

### [T-1.7] Barge-in: "Friday stop"
**Setup:** Ask FRIDAY a long question that triggers a multi-sentence reply,
e.g. `"Friday tell me a small story."`
**While the reply is playing, say:** `"Friday stop."`
**Expect:** TTS stops within ~0.5–0.8 s.
**Pass:** Log shows `[STT] Barge-in detected during speech: 'stop'` followed
immediately by `[TTS] Stop requested`.

### [T-1.8] Barge-in: ambient stop
**Setup:** As above.
**While speaking, say:** `"wait"` or `"enough"`.
**Pass:** Same as T-1.7.

### [T-1.9] Task cancellation mid-execution
**You say:** `"Friday read my latest email."` then immediately `"Friday cancel."`
**Expect:** The in-progress task is aborted with a "Task cancelled, sir"
acknowledgement.
**Pass:** Log shows `[TaskRunner] Task cancelled by user`.

### [T-1.10] Wake-word sustain
**Setup:** Persistent or wake-word mode, idle.
**You say:** `"Friday what's the time."` then within 12 s `"What's the date."`
(no wake word).
**Pass:** Both questions get answered.

### [T-1.11] Echo rejection
**Setup:** While FRIDAY is speaking a long sentence, do NOT speak.
**Expect:** FRIDAY does not transcribe its own voice as user input.
**Pass:** No `[USER]` line for the assistant's own words appears in the log.

---

## 2. Greeter & help

### [T-2.1] Greeting variants
**You say (one at a time):**
- `"Friday hello."`
- `"Friday hi."`
- `"Friday hey."`
- `"Friday good morning."`

**Expect:** Time-aware greetings ("Good morning, sir…", "At your service,
sir…").
**Pass:** Replies vary; never an error.

### [T-2.2] Show help / capability tour
**You say:** `"Friday what can you do?"` or `"Friday show help."`
**Expect:** A grouped list of available capabilities (system, browser,
email/calendar, etc.) with one-line examples.
**Pass:** Output is non-empty and references categories that exist in your
build (no broken capability names).

### [T-2.3] Goodbye
**You say:** `"Friday goodbye."` or `"Friday exit program."`
**Expect:** A farewell, then graceful shutdown.
**Pass:** Process exits with status 0 (`echo $?` after `python main.py`).

---

## 3. System control

### [T-3.1] System status
**You say:** `"Friday system status."`
**Expect:** Spoken summary of CPU, RAM, battery.
**Pass:** Numbers look plausible (battery between 0–100%, CPU below 100%).

### [T-3.2] Battery
**You say:** `"Friday battery status."`
**Pass:** Percentage and charging state announced.

### [T-3.3] CPU & RAM
**You say:** `"Friday what's my CPU usage?"` / `"Friday memory usage."`
**Pass:** Readings produced; stays consistent with `top` / `free -h`.

### [T-3.4] FRIDAY's own status
**You say:** `"Friday what's your status?"` / `"Friday model status."`
**Expect:** Lists which models are loaded and which optional skills are
disabled.
**Pass:** Mentions Gemma + Qwen + faster-whisper; no traceback.

### [T-3.5] Launch a single app
**You say:** `"Friday open Firefox."`
**Pass:** Firefox window appears within ~5 s.

### [T-3.6] Launch multiple apps
**You say:** `"Friday open Firefox and Calculator."`
**Pass:** Both apps launch.

### [T-3.7] Launch unknown app (graceful failure)
**You say:** `"Friday open Snowscape Pro."`
**Pass:** FRIDAY says it cannot find that app; no crash.

### [T-3.8] Volume up/down/mute/unmute
**You say (one at a time):**
- `"Friday volume up."`
- `"Friday volume down."`
- `"Friday mute."`
- `"Friday unmute."`

**Pass:** Each call audibly changes system volume.

### [T-3.9] Screenshot
**You say:** `"Friday take a screenshot."`
**Pass:** A new PNG appears in the Pictures or Screenshots folder; FRIDAY
reports the path.

### [T-3.10] Time / date
**You say:** `"Friday what time is it?"` and `"Friday what's today's date?"`
**Pass:** Local time and ISO-correct date.

---

## 4. File operations

### [T-4.1] Search file
**You say:** `"Friday find file friday.log."`
**Pass:** FRIDAY locates `logs/friday.log` and offers to read or open it.

### [T-4.2] Multiple candidates → selection
**Setup:** Have at least two files containing "report" in the name.
**You say:** `"Friday find report."`
**Expect:** A numbered list of candidates.
**You then:** `"Friday first one."` or `"Friday option 2."`
**Pass:** That candidate is opened/read.

### [T-4.3] Open file
**You say:** `"Friday open file resume.pdf."` (or any file you know exists)
**Pass:** Default app launches with that file.

### [T-4.4] Read file
**You say:** `"Friday read file todo.txt."`
**Pass:** First chunk of file contents announced.

### [T-4.5] Summarize file
**You say:** `"Friday summarize file todo.txt."`
**Pass:** A 2–3 sentence offline summary is produced.

### [T-4.6] List folder contents
**You say:** `"Friday list folder Downloads."`
**Pass:** First several visible filenames spoken/listed.

### [T-4.7] Open folder
**You say:** `"Friday open folder Documents."`
**Pass:** Nautilus / file-manager opens that path.

### [T-4.8] Manage file → create
**You say:** `"Friday create file scratch_test.md in Documents."`
**Pass:** New empty file at `~/Documents/scratch_test.md`.

### [T-4.9] Manage file → write
**You say:** `"Friday write 'Hello FRIDAY' to scratch_test.md."`
**Pass:** File contents replaced.

### [T-4.10] Manage file → append
**You say:** `"Friday append 'Second line' to scratch_test.md."`
**Pass:** Line appended without truncating prior content.

### [T-4.11] Save the last assistant answer
**You say:**
1. `"Friday give me a haiku about Linux."`
2. `"Friday save that to a file called haiku.txt."`

**Pass:** File contains the haiku text.

---

## 5. Reminders, notes, calendar (local)

### [T-5.1] Set a reminder (relative)
**You say:** `"Friday remind me to drink water in 2 minutes."`
**Pass:** FRIDAY confirms; after 2 min it announces the reminder.

### [T-5.2] Set a reminder (absolute)
**You say:** `"Friday set a reminder for 9 PM tomorrow to call Mom."`
**Pass:** Reminder stored with the right datetime; visible in T-5.4.

### [T-5.3] Save / read notes
**You say:**
1. `"Friday save note: groceries — milk, eggs, bread."`
2. `"Friday read my notes."`

**Pass:** Step 2 reads the saved note back.

### [T-5.4] List local calendar events
**You say:** `"Friday list calendar events."` / `"Friday upcoming reminders."`
**Pass:** All scheduled reminders/events with their times are read aloud.

---

## 6. Conversational chat (LLM fallback)

### [T-6.1] Open-ended question
**You say:** `"Friday tell me a small story about a robot."`
**Pass:** A short narrative reply that doesn't trigger any tool.

### [T-6.2] Ambiguous greeting
**You say:** `"Friday I'm bored."`
**Pass:** A conversational reply (no error, no tool dispatch).

### [T-6.3] Saying "yes" with no pending action
**You say:** `"Friday yes."` (out of context)
**Expect:** A polite "I'm not sure what you're saying yes to."
**Pass:** No max-recursion error; mic resumes.

---

## 7. Google Workspace (gws CLI)

> **Pre-req:** `gws` CLI installed and authenticated to your Google account.
> Verify with `gws gmail +triage --max 1 --format json`.

### [T-7.1] List unread emails
**You say:** `"Friday check my email."` / `"Friday any new emails."`
**Expect:** `"You have N unread email(s), sir: 1. From … — subject (date)…"`
**Pass:** Sender names + subjects match what you see in Gmail.

### [T-7.2] Read latest email
**You say:** `"Friday read my latest email."`
**Expect:** Sender, subject, date headers, then the body text (capped at
~1500 chars).
**Pass:** Body matches the most-recent unread message in Gmail.

### [T-7.3] Read a specific email by ID
**You say:** First run T-7.1 to get an ID, then
`"Friday read email <message_id>."`
**Pass:** Body of that exact message.

### [T-7.4] Today's calendar
**You say:** `"Friday what's on my calendar today?"`
**Pass:** Today's events listed; "no events scheduled" if calendar is empty.

### [T-7.5] Week's calendar
**You say:** `"Friday what's on my calendar this week?"`
**Pass:** Week's events.

### [T-7.6] Agenda for next N days
**You say:** `"Friday show my agenda for the next 5 days."`
**Pass:** Events grouped by date.

### [T-7.7] Create a calendar event (CONSENT prompt)
**You say:** `"Friday create a calendar event titled Test Meeting from 2026-05-01T15:00 to 2026-05-01T16:00."`
**Expect:** FRIDAY asks for confirmation (`create_calendar_event` is the
only Workspace tool that still needs consent).
**You then:** `"Friday yes."`
**Pass:** Event appears in Google Calendar.

### [T-7.8] Search Drive
**You say:** `"Friday search drive for resume."`
**Pass:** Up to 5 Drive files matching the query are listed with names and
links.

### [T-7.9] Daily briefing
**You say:** `"Friday give me my daily briefing."`
**Pass:** A combined summary of today's calendar + unread emails.

### [T-7.10] Workspace failure mode
**Setup:** Disconnect from the network.
**You say:** `"Friday check my email."`
**Pass:** Graceful "I couldn't reach Gmail: …" message, no traceback.

---

## 8. Browser automation & media (Playwright + worker thread)

> **Pre-req:** Chrome (or Chromium) installed; Playwright drivers present
> (`playwright install chromium`). Internet connection.
> The browser worker is a **single dedicated thread**, so successive
> commands across multiple voice turns must all succeed without the
> "cannot switch to a different thread" error.

### [T-8.1] Open a URL
**You say:** `"Friday open YouTube."` (asks consent first time)
**You then:** `"Friday yes."`
**Pass:** A controlled Chrome window opens YouTube.

### [T-8.2] Play a YouTube video
**You say:** `"Friday play LoFi study mix on YouTube."`
**Pass:** YouTube tab navigates to the first result and starts playing
fullscreen.

### [T-8.3] Play a YouTube Music song
**You say:** `"Friday play Closer on YouTube Music."`
**Pass:** Separate YouTube Music tab opens; song begins.

### [T-8.4] Independent tabs (regression for the "music pauses video" bug)
**Sequence:**
1. T-8.2 — start a YouTube video.
2. Wait until it's playing audibly.
3. T-8.3 — start a YouTube Music song.

**Pass:** Both tabs continue playing (you may need headphones to confirm).
The YouTube tab does **not** pause when the YouTube Music tab opens.

### [T-8.5] Fast-path media controls (instant)
**Setup:** Media is playing from T-8.2 or T-8.3.
**You say (each one in turn):**
- `"Friday pause."` → playback pauses
- `"Friday resume."` (or `"Friday play."`) → resumes
- `"Friday next."` → next track / video
- `"Friday previous."` (or `"Friday rewind."`) → previous
- `"Friday forward."` → +10 s
- `"Friday backward."` → -10 s
- `"Friday mute."` → toggles mute

**Pass:** Each command takes effect within ~0.5 s and the log shows
`[STT] Fast media command: <action>` rather than going through the LLM
router.

### [T-8.6] Long media-control phrasing (router path)
**You say:** `"Friday skip 30 seconds forward."`
**Pass:** Player jumps ~30 s forward; log shows
`[router] Match Found … browser_media_control` (not the fast-path).

### [T-8.7] "Music instead" / "YouTube instead" pivot
**Setup:** Just played a song on YouTube.
**You say:** `"Friday open it in music instead."`
**Pass:** The same query starts on YouTube Music in the existing tab.

### [T-8.8] Tasks while media plays
**Setup:** Music is playing.
**You say (with wake word required):**
- `"Friday what time is it?"` → answers, music keeps playing.
- `"Friday read my latest email."` → reads it, music keeps playing.

**Pass:** Both succeed; music does not pause; FRIDAY's TTS audibly mixes
with the music output (the browser is a separate audio source).

### [T-8.9] Search Google
**You say:** `"Friday search Google for python type hints."`
**Pass:** A new Google search results tab opens with that query.

### [T-8.10] Alt phrasing for Google search
**You say (each):**
- `"Friday google for capital of France."`
- `"Friday look up the GPL license."`
- `"Friday search the web for Linux 6.18 changelog."`

**Pass:** Each opens a Google search tab with the expected query.

### [T-8.11] Browser worker survival across turns
**Sequence:**
1. T-8.5 — pause via fast path.
2. Wait 30 s.
3. T-8.5 again — resume.
4. T-8.9 — search Google.

**Pass:** No `cannot switch to a different thread` error in the log;
operations are served by the same worker thread (`friday-browser` in the
log).

### [T-8.12] Browser disabled
**Edit `config.yaml`:** `browser_automation.enabled: false`, restart.
**You say:** `"Friday play LoFi on YouTube."`
**Pass:** FRIDAY says browser automation is disabled; no crash.

---

## 9. World Monitor (online news)

### [T-9.1] Global digest
**You say:** `"Friday give me a world monitor briefing."`
**Pass:** A few short story summaries are spoken.

### [T-9.2] Category filter
**You say:** `"Friday tech news from world monitor."` (or `finance`,
`commodity`, `energy`, `good`).
**Pass:** Stories are tagged with the right category.

### [T-9.3] Focus filter
**You say:** `"Friday world monitor news about oil."`
**Pass:** Returned stories mention oil/energy.

### [T-9.4] Country filter
**You say:** `"Friday world monitor news for India."`
**Pass:** Stories mention India or related geo-tags.

### [T-9.5] Threat threshold
**You say:** `"Friday world monitor critical alerts."`
**Pass:** Only high/critical-severity items are read.

### [T-9.6] Window override
**You say:** `"Friday world monitor news from the last 6 hours."`
**Pass:** Only stories from that window appear.

### [T-9.7] Limit
**You say:** `"Friday world monitor top 3 stories."`
**Pass:** Exactly 3 items.

---

## 10. Online consent flow

### [T-10.1] First online tool with `ask_first` mode
**Edit `config.yaml`:** `conversation.online_permission_mode: ask_first`,
restart.
**You say:** `"Friday play LoFi on YouTube."`
**Expect:** "I can handle that with an online skill … Say yes if you want
me to go online."
**You then:** `"Friday yes."`
**Pass:** Tool runs; pending state cleared in `data/context.sqlite`.

### [T-10.2] Decline online consent
**Trigger consent prompt as in T-10.1, then:** `"Friday no."`
**Pass:** Pending state cleared; FRIDAY says it'll stay offline.

### [T-10.3] Workspace consent bypass
Workspace **read-only** tools (mail, calendar list, drive search) are
tagged `permission_mode=always_ok`, so they should NOT trigger a consent
prompt — only `create_calendar_event` does.
**You say:** `"Friday read my latest email."`
**Pass:** No "say yes" prompt; the email is read directly.

### [T-10.4] "yes" with no pending action
**Setup:** No prior online prompt.
**You say:** `"Friday yes."`
**Pass:** Polite fallback ("I'm not sure what you're saying yes to.") —
**no `maximum recursion depth exceeded` error** in the log (regression
guard for the workspace recursion bug).

---

## 11. Multi-step / multi-action plans

### [T-11.1] Sequential actions
**You say:** `"Friday open calculator and take a screenshot."`
**Pass:** Calculator launches first, then a screenshot is captured.

### [T-11.2] Action then question
**You say:** `"Friday open Firefox and tell me a joke."`
**Pass:** Firefox launches; then a joke is spoken.

### [T-11.3] Workflow continuation (file)
**Sequence:**
1. `"Friday create a file."`
2. (FRIDAY asks for filename) → `"Friday call it ideas.md."`
3. (FRIDAY asks for content) → `"Friday write 'Phase 1 ideas' in it."`

**Pass:** File created, then written. Workflow state persists across the
three turns.

### [T-11.4] Reminder follow-up
**Sequence:**
1. `"Friday remind me about a meeting."`
2. (FRIDAY asks when) → `"Friday at 4 PM today."`

**Pass:** Reminder is scheduled with correct time.

---

## 12. Memory & persona

### [T-12.1] Active persona
Run:
```
python -c "from core.context_store import ContextStore; cs=ContextStore(); s=cs.start_session({'entrypoint':'cli'}); print(cs.get_session_state(s))"
```
**Pass:** Output references `friday_core` (default persona).

### [T-12.2] Auto-memory capture
**You say:** `"Friday remember that I work as a backend engineer at Acme."`
**Then on next session:** `"Friday what do you know about me?"`
**Pass:** FRIDAY references the saved fact.

### [T-12.3] Procedural memory: tool success rate
**Setup:** Run T-3.5 (launch_app) several times.
**Then:**
```
python -c "
from core.memory.procedural import ProceduralMemory
print(ProceduralMemory().capability_outcomes('launch_app'))
"
```
**Pass:** Records of recent success/failure outcomes appear.

---

## 13. Error handling & resilience

### [T-13.1] Network drop mid-online task
**Setup:** Disconnect Wi-Fi while music is playing.
**You say:** `"Friday play despacito on YouTube Music."`
**Pass:** FRIDAY responds with a graceful failure (or fallback `xdg-open`),
no traceback.

### [T-13.2] Whisper transcription confusion
**You say:** `"Friday … <inaudible mumble>."`
**Pass:** Either rejected with `low-signal transcript` or routed to
clarify; no crash.

### [T-13.3] gws not authenticated
**Setup:** Run `gws auth logout` first.
**You say:** `"Friday check my email."`
**Pass:** Graceful "I couldn't reach Gmail: …" message.

### [T-13.4] Playwright driver missing
**Setup:** `pip uninstall -y playwright` (or rename its `driver/` dir).
**You say:** `"Friday play LoFi on YouTube."`
**Pass:** FRIDAY falls back to `xdg-open` and opens the search results URL
in your default browser.

### [T-13.5] Capability collision
**Sanity check:** the IMAP `email_ops` skill and the gws `WorkspaceAgent`
both register `check_unread_emails`. Confirm Workspace wins.
**You say:** `"Friday check my email."`
**Pass:** Output uses gws (sender names + subjects with proper formatting),
**not** an IMAP "EMAIL_ADDRESS not configured" error.

---

## 13a. Window manager *(new)*

> **Pre-req:** `wmctrl` installed; `xdotool` recommended for accurate
> active-window detection. Tests assume an X11 session.

### [T-13a.1] Tile to the left
**Setup:** Open Firefox so it isn't already half-screen.
**You say:** `"Friday tile firefox to the left."`
**Pass:** Firefox snaps to the left half of the active monitor; FRIDAY
replies "Tiled firefox to the left."

### [T-13a.2] Tile by side keyword
**You say (each):** `"Friday tile this to the right."`,
`"Friday tile this to the top."`, `"Friday tile this to the bottom."`
**Pass:** Active window snaps to that half each time.

### [T-13a.3] Maximize / unmaximize / restore
**You say:** `"Friday maximize this."` then `"Friday unmaximize this."`
**Pass:** Window maximizes, then returns to its prior size.

### [T-13a.4] Fullscreen / exit fullscreen
**You say:** `"Friday fullscreen this."` then
`"Friday exit fullscreen."`
**Pass:** Window enters and leaves fullscreen.

### [T-13a.5] Minimize active window
**You say:** `"Friday minimize this."`
**Pass:** Active window minimizes.

### [T-13a.6] Minimize everything but X
**Setup:** At least three apps open including a code editor.
**You say:** `"Friday minimize everything but the editor."`
**Pass:** Editor stays visible; FRIDAY reports the count of windows
minimized.

### [T-13a.7] Focus a named window
**You say:** `"Friday focus the firefox window."` /
`"Friday switch to the editor window."`
**Pass:** That window comes to the front.

### [T-13a.8] Close window
**Setup:** Open a throwaway calculator window.
**You say:** `"Friday close this window."`
**Pass:** Calculator closes.

### [T-13a.9] Send to workspace
**Setup:** At least 2 workspaces.
**You say:** `"Friday send this to workspace 2."`
**Pass:** The active window jumps to workspace 2 (FRIDAY confirms).

### [T-13a.10] Switch workspace
**You say:** `"Friday go to workspace 1."`
**Pass:** Desktop switches to workspace 1.

### [T-13a.11] Send to monitor *(multi-monitor only)*
**Setup:** Two or more displays connected. Run `xrandr --query` to
confirm.
**You say:** `"Friday send this to monitor 2."` /
`"Friday throw firefox to display 1."`
**Pass:** Window centers itself on the named monitor at 2/3 of that
monitor's resolution; FRIDAY says "Sent <app> to monitor 2 (HDMI-…)".

### [T-13a.12] Send to nonexistent monitor
**You say:** `"Friday send this to monitor 9."`
**Pass:** "I only see N monitor(s) connected."

### [T-13a.13] Graceful failure (wmctrl missing)
**Setup:** Temporarily rename `/usr/bin/wmctrl` (or run as a user without
it on `$PATH`).
**You say:** `"Friday tile firefox to the left."`
**Pass:** Spoken response says wmctrl is missing — no crash.

---

## 13b. Dictation mode *(new)*

> Memo files land in `~/Documents/friday-memos/` as
> `YYYY-MM-DD_HHMM_<slug>.md`.

### [T-13b.1] Start a memo
**You say:** `"Friday take a memo."`
**Pass:** FRIDAY confirms dictation has started and reads back the file
name; log shows `[dictation] Started session 'memo' …`.

### [T-13b.2] Capture mid-memo
**Continuing T-13b.1, you say (without "Friday"):**
1. `"This is the first thought."`
2. `"And here is a second sentence."`

**Pass:** Each utterance produces `[dictation] captured: …` in the log;
no transcript reaches the normal command pipeline.

### [T-13b.3] End the memo
**You say:** `"Friday end memo."` (or `"Friday save the dictation."`)
**Pass:** FRIDAY announces the word count and file name; the
`~/Documents/friday-memos/<file>.md` exists with a Markdown header,
recorded timestamp, and the captured body text.

### [T-13b.4] Cancel a memo
1. `"Friday take a memo called scratch."`
2. `"This text should not be saved."`
3. `"Friday cancel the memo."`

**Pass:** No file is written; FRIDAY responds "Dictation cancelled."

### [T-13b.5] Labelled memo
**You say:** `"Friday start a dictation called grocery list."`
Then `"Milk, eggs, bread."` then `"Friday end memo."`
**Pass:** File is named `<date>_<time>_grocery-list.md` with
`# Grocery List` heading.

### [T-13b.6] Re-entry guard
**Setup:** Start a memo (T-13b.1).
**You say (during the active session):** `"Friday take a memo."`
**Pass:** FRIDAY tells you a memo is already active and points at its
file name. (No second session is opened.)

### [T-13b.7] Wake-word bypass
**Setup:** Active dictation, persistent listening mode.
**You say (no wake word):** `"Quick reminder for the report on Friday."`
**Pass:** Captured into the memo; `[dictation] captured` appears.

---

## 13c. Focus session *(new)*

### [T-13c.1] Default 25-minute pomodoro
**You say:** `"Friday start a focus session."`
**Pass:** Confirmation says 25 minutes, notifications muted, media
paused. Run `gsettings get org.gnome.desktop.notifications show-banners`
— it should report `false`.

### [T-13c.2] Custom duration
**You say:** `"Friday focus for 50 minutes."`
**Pass:** Confirmation references 50 minutes.

### [T-13c.3] Status query
**Continuing T-13c.2, you say:** `"Friday focus status."` /
`"Friday how much focus is left?"`
**Pass:** Remaining time announced.

### [T-13c.4] Re-entry guard
**You say (mid-session):** `"Friday start a focus session."`
**Pass:** FRIDAY says focus is already active and reports the time
remaining; no second timer is started.

### [T-13c.5] Stop focus early
**You say:** `"Friday end focus."` (or `"Friday stop focus session."`)
**Pass:** FRIDAY confirms the elapsed minutes; the
`show-banners` gsetting returns to its previous value.

### [T-13c.6] Auto end + reminder
**Setup:** Start a 1-minute session: edit
`core/reasoning/workflows/focus_mode.py` if a 1-minute floor isn't
exposed, or simply trust the timer with a longer wait.
**Pass:** When the timer fires, FRIDAY speaks the "session complete"
line and notifications come back on.

### [T-13c.7] Media pause on start
**Setup:** Music playing on YouTube Music (T-8.3).
**You say:** `"Friday start a 5-minute focus."`
**Pass:** Music pauses within ~1 s of the start announcement.

---

## 13d. Calendar event creation *(new)*

### [T-13d.1] Schedule with explicit time
**You say:** `"Friday create a calendar event titled standup tomorrow at 10am."`
**Pass:** FRIDAY confirms the title and the absolute date/time. Run
`python -c "import sqlite3,os; print(sqlite3.connect(os.path.expanduser('~/Friday_Linux/data/tasks.db')).execute('SELECT title,remind_at FROM calendar_events ORDER BY id DESC LIMIT 1').fetchone())"`
— last row is the new event.

### [T-13d.2] Relative time
**You say:** `"Friday schedule a meeting in 15 minutes."`
**Pass:** Event scheduled 15 minutes from now.

### [T-13d.3] "schedule X for Friday at 3pm"
**You say:** `"Friday schedule a dentist appointment on Friday at 3 pm."`
**Pass:** Stored at the next Friday 3 PM.

### [T-13d.4] Missing time → confirmation prompt
**You say:** `"Friday create a calendar event titled lunch."`
**Pass:** FRIDAY asks when to schedule it (no event created).

### [T-13d.5] Past time guard
**You say:** `"Friday create an event titled retro yesterday at 9 am."`
**Pass:** FRIDAY refuses with "That time has already passed."

### [T-13d.6] Cancel by name
**Setup:** From T-13d.1 there's a "standup" event.
**You say:** `"Friday cancel the standup reminder."`
**Pass:** FRIDAY confirms cancellation; the row's status flips (or it's
removed); `list_calendar_events` no longer reads it back.

### [T-13d.7] Cancel the next one
**Setup:** At least one upcoming event.
**You say:** `"Friday cancel the next event."`
**Pass:** Earliest upcoming event removed.

### [T-13d.8] Cancel without match
**You say:** `"Friday cancel the unicorn meeting."`
**Pass:** "I couldn't find a reminder matching 'unicorn meeting'."

### [T-13d.9] Move by name to a new clock time
**Setup:** From T-13d.1 there's a "standup" event tomorrow at 10 AM.
**You say:** `"Friday reschedule the standup to 11 AM."`
**Pass:** FRIDAY confirms the move; `list_calendar_events` shows the
event at 11 AM tomorrow.

### [T-13d.10] Move "my 3 PM" to "4"
**Setup:** Schedule an event at 3 PM today (T-13d.1 with a 3 PM time).
**You say:** `"Friday move my 3 PM to 4."`
**Pass:** Event moved to 4 PM same day. (Voice "to 4" with a PM anchor
auto-promotes to 16:00.)

### [T-13d.11] Shift by duration
**You say:** `"Friday shift the gym block by 2 hours."`
**Pass:** The matching event's time shifts forward by exactly 2 hours.

### [T-13d.12] Move the next reminder
**You say:** `"Friday move the next reminder to 5pm."`
**Pass:** The earliest upcoming event is moved to 5 PM today/tomorrow.

### [T-13d.13] Move past time guard
**You say:** `"Friday move my 9 AM to 8."` (when 9 AM was earlier today
and 8 AM is in the past).
**Pass:** "That time has already passed. Please pick a future time."

---

## 13e. Screen reader & OCR *(new)*

> **Pre-req:** `xclip` for selection reads; `tesseract-ocr` plus
> `gnome-screenshot` (or `flameshot` / ImageMagick `import`) for OCR.

### [T-13e.1] Read highlighted text
**Setup:** Open any text editor and highlight a paragraph with the
mouse (no need to copy).
**You say:** `"Friday read the highlighted text."`
**Pass:** FRIDAY reads back the selected paragraph (truncated to ~4000
chars).

### [T-13e.2] "What does this say"
**Setup:** Highlight a single word.
**You say:** `"Friday what does this say?"`
**Pass:** FRIDAY reads back that word.

### [T-13e.3] Empty selection
**Setup:** Make sure nothing is highlighted (click elsewhere).
**You say:** `"Friday read this."`
**Pass:** "Nothing is highlighted right now…"

### [T-13e.4] OCR a region
**You say:** `"Friday OCR the selection."`
**Pass:** A region-capture cursor appears (gnome-screenshot crosshair).
Drag a box around any visible text. FRIDAY reads back the recognised
text. The temp PNG is deleted afterwards (`ls /tmp/tmp*.png` is empty).

### [T-13e.5] Alt phrasings
**You say (each):** `"Friday read the text in this region."`,
`"Friday extract text from this image."`,
`"Friday read what's on the screen."`
**Pass:** Same OCR flow each time.

### [T-13e.6] Capture cancelled
**During the OCR cursor, press `Escape` instead of dragging.**
**Pass:** FRIDAY reports a capture failure cleanly — no traceback.

### [T-13e.7] Tesseract missing
**Setup:** `sudo apt remove tesseract-ocr` (or move it off `$PATH`).
**You say:** `"Friday OCR the selection."`
**Pass:** Friendly message asking the user to install tesseract.

---

## 13f. Regression — earlier fixes

### [T-13f.1] "play X on YouTube" routes to a fresh search
*(was: collapsed to "Resume youtube" because the workflow regex only
matched "in youtube".)*

**Setup:** "Friday open YouTube" so a workflow is active.
**You say:** `"Friday play closer on YouTube."`
**Pass:** A YouTube search starts and the song begins; reply contains
"Playing closer on youtube …", **not** "Resumed youtube".

### [T-13f.2] Skip-with-seconds via the long path
*(was: "skip 30 seconds forward" mapped to next track.)*

**Setup:** A YouTube video is playing.
**You say:** `"Friday skip 30 seconds forward."`
**Pass:** Player jumps ~30 s ahead; FRIDAY says "Skipped forward 30
seconds on youtube." Same with `"go back 15 seconds"` → 15 s rewind.

### [T-13f.3] Plain forward/backward seek by 10 s
**You say:** `"Friday forward."` / `"Friday backward."`
**Pass:** Each call moves playback ±10 s (use a podcast or long video to
verify).

### [T-13f.4] YouTube Music pause via JS
*(was: pressing `k` had no effect on YT Music; the prior "click(10,10)"
sometimes navigated away.)*

**Setup:** YT Music playing (T-8.3).
**You say:** `"Friday pause."` then `"Friday resume."`
**Pass:** Audio pauses and resumes within ~0.5 s without the YT Music
page reloading or the sidebar opening.

### [T-13f.5] YouTube Music previous goes to previous track
*(was: pressing previous when past 3 s only restarted the current
song.)*

**Setup:** YT Music has played for >5 s.
**You say:** `"Friday previous."`
**Pass:** Playback moves to the previous song (not a restart).

### [T-13f.6] File search shows folder context, not full paths
*(was: search results read out the entire absolute path.)*

**You say:** `"Friday find file friday.log."`
**Pass:** Each result line is `- friday.log (in logs)` — base filename
plus parent folder, never the home/absolute path.

### [T-13f.7] Write topic content into a file
*(was: "write the advantages of coffee into a file named X" stored the
literal phrase or refused.)*

**You say:** `"Friday write the advantages of coffee into a file named
coffee_notes."`
**Pass:** A file `coffee_notes` (or `.md`) is created in the active
folder containing a multi-paragraph article generated by Gemma — not
the literal phrase "the advantages of coffee".

### [T-13f.8] Open and read on the same selected file
*(was: "open and read it to me" was split into two clauses and tried to
launch an app called "and read it to me".)*

**Setup:** Run T-4.2 to leave a single pending file selected
(LOG.old).
**You say:** `"Friday open and read it to me."`
**Pass:** The selected file opens in its default app and FRIDAY also
reads back its contents — single clause, no app-launch error.

### [T-13f.9] Conversational chat latency
*(was: short questions like "I'm bored" took 8–11 s.)*

**You say:** `"Friday I'm bored."`
**Pass:** Spoken reply within ~3 s. The log shows `[LLMChat] Response`
with a 1–2 sentence answer (no chain-of-thought, no emoji unless you
used one first).

### [T-13f.10] Calendar create no longer collapses to agenda read
*(was: "create a calendar event titled X" returned the agenda.)*

**You say:** `"Friday create a calendar event titled retro tomorrow at 4."`
**Pass:** The event is created; the response is the
`_format_confirmation` text, **not** the upcoming-events list.

---

## 14. Configuration smoke tests

For each, edit `config.yaml`, restart, run a representative test:

| Setting | Test |
|---|---|
| `conversation.listening_mode` | T-1.2, T-1.3, T-1.4 |
| `conversation.online_permission_mode` | T-10.1 vs T-10.3 |
| `conversation.progress_delays_s` | Set to `[2.5, 6.0]` and run T-6.1 — expect filler "I'm working on it" announcements |
| `routing.tool_timeout_ms` | Drop to `200`, then run T-3.5 — expect timeout handling |
| `voice.input_device` | Switch ID, restart, confirm STT initializes against the new mic |
| `browser_automation.enabled` | T-8.12 |
| `browser_automation.preferred_browser` | Set to `chromium`, run T-8.2 |

---

## 15. Performance budgets (subjective)

| Operation | Target | How to measure |
|---|---|---|
| Wake → first transcript | ≤ 1 s | Whisper transcribe log line |
| Barge-in stop | ≤ 0.8 s | Time from "stop" to TTS subprocess kill |
| Fast media command | ≤ 0.5 s | `[STT] Fast media command` → browser action |
| Local tool turn (e.g. battery) | ≤ 1 s | `route_duration_ms` in `traces.jsonl` |
| Workspace email read | ≤ 4 s | Stopwatch — gws CLI is the bottleneck |
| Browser cold start | ≤ 15 s | Chrome launch + Playwright driver load |
| Browser warm command | ≤ 1.5 s | After T-8.11 step 1 has primed the worker |

---

## 16. Regression guards (must-not-break list)

If any of these fail, the build is **not shippable**:

- [ ] T-1.7 (barge-in stop)
- [ ] T-1.9 (task cancel)
- [ ] T-7.1 + T-7.2 (Workspace email reads)
- [ ] T-8.4 (independent media tabs)
- [ ] T-8.5 (fast-path media controls)
- [ ] T-8.11 (browser worker survives across turns)
- [ ] T-10.4 (no recursion on bare "yes")
- [ ] T-13.5 (Workspace wins over IMAP skill)
- [ ] T-13f.1 (play X on YouTube routes to fresh search)
- [ ] T-13f.2 (skip 30 seconds forward)
- [ ] T-13f.4 (YouTube Music pause works)
- [ ] T-13f.6 (file search shows folder, not full path)
- [ ] T-13f.8 (open and read it on selected file)
- [ ] T-13f.10 (calendar create doesn't fall through to agenda)

---

## 17. Reporting a failure

When a test fails:

1. Capture the relevant slice of `logs/friday.log` (5 lines before and
   after the failure).
2. Note the test ID (e.g. `T-8.4`).
3. If the GUI is involved, attach a screenshot.
4. Open an issue or PR-comment with:
   ```
   Test: T-X.Y <name>
   Build: <git rev-parse --short HEAD>
   Listening mode: <mode>
   Voice / text: <which input>
   Steps: <what you said>
   Expected: <expected behavior>
   Actual: <what happened>
   Logs:
   <paste>
   ```

---

## Appendix A — Tool catalog (cross-reference)

| Tool | Section | Notes |
|---|---|---|
| `greet` | T-2.1 | greeter |
| `show_help` | T-2.2 | greeter, dynamic catalog |
| `shutdown_assistant` | T-2.3 | system_control |
| `get_system_status` | T-3.1 | |
| `get_friday_status` | T-3.4 | |
| `get_battery` | T-3.2 | |
| `get_cpu_ram` | T-3.3 | |
| `launch_app` | T-3.5–7 | multi-arg via `app_names` |
| `set_volume` | T-3.8 | |
| `take_screenshot` | T-3.9 | |
| `get_time` / `get_date` | T-3.10 | task_manager |
| `search_file` | T-4.1 | |
| `select_file_candidate` | T-4.2 | |
| `open_file` | T-4.3 | |
| `read_file` | T-4.4 | |
| `summarize_file` | T-4.5 | offline summarizer |
| `list_folder_contents` | T-4.6 | |
| `open_folder` | T-4.7 | |
| `manage_file` | T-4.8–11 | create/write/append/read |
| `set_reminder` | T-5.1–2 | |
| `save_note` / `read_notes` | T-5.3 | |
| `list_calendar_events` | T-5.4 | |
| `llm_chat` | section 6 | fallback |
| `check_unread_emails` | T-7.1 | Workspace |
| `read_latest_email` | T-7.2 | Workspace |
| `read_email` | T-7.3 | Workspace |
| `get_calendar_today` | T-7.4 | Workspace |
| `get_calendar_week` | T-7.5 | Workspace |
| `get_calendar_agenda` | T-7.6 | Workspace |
| `create_calendar_event` | T-7.7 | Workspace, ask_first |
| `search_drive` | T-7.8 | Workspace |
| `daily_briefing` | T-7.9 | Workspace |
| `open_browser_url` | T-8.1 | |
| `play_youtube` | T-8.2 | |
| `play_youtube_music` | T-8.3 | |
| `browser_media_control` | T-8.5–8.7 | fast path + router path |
| `search_google` | T-8.9–10 | |
| `get_world_monitor_news` | section 9 | |
| `enable_voice` / `disable_voice` / `set_voice_mode` | section 1 | voice_io |
| `confirm_yes` / `confirm_no` | T-10.1–4 | consent flow |
| `window_action` | section 13a | window_manager |
| `start_dictation` / `end_dictation` / `cancel_dictation` | section 13b | dictation |
| `start_focus_session` / `end_focus_session` / `focus_session_status` | section 13c | focus_session |
| `create_calendar_event` / `move_calendar_event` / `cancel_calendar_event` | section 13d | task_manager |
| `read_selection` / `ocr_region` | section 13e | screen_text |

---

## Appendix B — Key log markers

When watching `logs/friday.log` during tests, look for:

| Marker | Meaning |
|---|---|
| `Router received: <text>` | Routing started |
| `[router] Match Found: …` | Deterministic match |
| `[router] Fast-path …` | Intent recognizer resolved |
| `[STT] Fast media command: <action>` | Bypassed router → browser worker |
| `[STT] Barge-in detected during speech` | TTS will be interrupted |
| `[TaskRunner] Task cancelled by user` | Voice cancel path fired |
| `[workflow] Running workflow: <name>` | Multi-turn workflow active |
| `[loader] Skipping JARVIS tool '<x>' from skill … (capability already registered)` | Native extension precedence held |
| `[browser] fast_media_command(<x>) failed` | Fast-path swallowed an exception |
