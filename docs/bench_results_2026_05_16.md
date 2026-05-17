# Intent-routing benchmark — 2026-05-16 09:56 UTC

**Cases:** 328

**Models compared:** current, gemma, fn-gemma


## Headline metrics

| Model | Accuracy | Macro P | Macro R | Macro F1 | Micro F1 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| current | 50.9% | 0.704 | 0.464 | 0.507 | 0.509 | 2 | 3 |
| gemma | 77.4% | 0.851 | 0.759 | 0.762 | 0.777 | 93 | 163 |
| fn-gemma | 69.2% | 0.746 | 0.820 | 0.754 | 0.703 | 388 | 456 |

## Per-category accuracy

| Category | N | current ✓ | gemma ✓ | fn-gemma ✓ | current p50 | gemma p50 | fn-gemma p50 |
|---|---|---|---|---|---|---|---|
| browser_media_control | 6 | 0/6 | 5/6 | 5/6 | 3ms | 135ms | 403ms |
| cancel_calendar_event | 5 | 5/5 | 5/5 | 5/5 | 2ms | 105ms | 418ms |
| cancel_dictation | 6 | 2/6 | 6/6 | 2/6 | 3ms | 120ms | 379ms |
| chitchat | 9 | 8/9 | 8/9 | 0/9 | 3ms | 90ms | 382ms |
| confirm_no | 6 | 0/6 | 5/6 | 5/6 | 3ms | 93ms | 355ms |
| confirm_yes | 6 | 1/6 | 5/6 | 5/6 | 3ms | 68ms | 384ms |
| create_calendar_event | 6 | 5/6 | 6/6 | 6/6 | 1ms | 109ms | 397ms |
| delete_memory | 6 | 1/6 | 6/6 | 5/6 | 3ms | 93ms | 390ms |
| disable_voice | 6 | 3/6 | 6/6 | 4/6 | 2ms | 73ms | 371ms |
| enable_voice | 5 | 2/5 | 4/5 | 4/5 | 2ms | 73ms | 388ms |
| end_dictation | 5 | 3/5 | 5/5 | 4/5 | 1ms | 85ms | 406ms |
| end_focus_session | 6 | 0/6 | 6/6 | 6/6 | 3ms | 98ms | 418ms |
| focus_session_status | 5 | 3/5 | 4/5 | 5/5 | 1ms | 143ms | 410ms |
| get_battery | 5 | 2/5 | 1/5 | 5/5 | 3ms | 90ms | 397ms |
| get_cpu_ram | 5 | 3/5 | 1/5 | 5/5 | 1ms | 133ms | 375ms |
| get_date | 5 | 1/5 | 2/5 | 4/5 | 3ms | 125ms | 335ms |
| get_friday_status | 6 | 4/6 | 0/6 | 5/6 | 1ms | 141ms | 392ms |
| get_system_status | 5 | 3/5 | 1/5 | 5/5 | 1ms | 82ms | 433ms |
| get_time | 6 | 4/6 | 2/6 | 6/6 | 1ms | 77ms | 390ms |
| get_weather | 6 | 3/6 | 1/6 | 5/6 | 2ms | 84ms | 363ms |
| greet | 6 | 4/6 | 6/6 | 5/6 | 2ms | 68ms | 300ms |
| launch_app | 6 | 5/6 | 6/6 | 5/6 | 2ms | 72ms | 382ms |
| list_calendar_events | 6 | 3/6 | 3/6 | 5/6 | 2ms | 102ms | 391ms |
| list_folder_contents | 6 | 0/6 | 1/6 | 6/6 | 3ms | 90ms | 421ms |
| list_reminders | 6 | 4/6 | 0/6 | 4/6 | 2ms | 124ms | 381ms |
| manage_file | 6 | 0/6 | 6/6 | 5/6 | 3ms | 71ms | 400ms |
| move_calendar_event | 5 | 2/5 | 5/5 | 5/5 | 3ms | 128ms | 413ms |
| neg/browser_media_control | 1 | 1/1 | 1/1 | 0/1 | 3ms | 121ms | 321ms |
| neg/cancel_calendar_event | 1 | 1/1 | 1/1 | 0/1 | 3ms | 78ms | 414ms |
| neg/cancel_dictation | 1 | 1/1 | 1/1 | 0/1 | 3ms | 70ms | 825ms |
| neg/confirm_no | 1 | 1/1 | 1/1 | 0/1 | 3ms | 125ms | 378ms |
| neg/confirm_yes | 1 | 1/1 | 0/1 | 0/1 | 2ms | 101ms | 365ms |
| neg/create_calendar_event | 1 | 1/1 | 1/1 | 0/1 | 4ms | 90ms | 444ms |
| neg/delete_memory | 1 | 1/1 | 1/1 | 0/1 | 3ms | 92ms | 350ms |
| neg/disable_voice | 1 | 1/1 | 1/1 | 0/1 | 3ms | 147ms | 341ms |
| neg/enable_voice | 1 | 1/1 | 1/1 | 0/1 | 3ms | 127ms | 327ms |
| neg/end_dictation | 1 | 1/1 | 1/1 | 0/1 | 3ms | 79ms | 426ms |
| neg/end_focus_session | 1 | 1/1 | 0/1 | 0/1 | 3ms | 90ms | 377ms |
| neg/focus_session_status | 1 | 1/1 | 1/1 | 0/1 | 23ms | 91ms | 400ms |
| neg/get_battery | 1 | 1/1 | 1/1 | 0/1 | 3ms | 82ms | 401ms |
| neg/get_cpu_ram | 1 | 0/1 | 1/1 | 0/1 | 2ms | 92ms | 419ms |
| neg/get_date | 1 | 1/1 | 1/1 | 0/1 | 2ms | 136ms | 354ms |
| neg/get_friday_status | 1 | 1/1 | 1/1 | 0/1 | 3ms | 76ms | 369ms |
| neg/get_system_status | 1 | 0/1 | 1/1 | 0/1 | 1ms | 76ms | 430ms |
| neg/get_time | 1 | 1/1 | 1/1 | 0/1 | 3ms | 187ms | 323ms |
| neg/get_weather | 1 | 1/1 | 1/1 | 0/1 | 3ms | 123ms | 331ms |
| neg/greet | 1 | 0/1 | 1/1 | 0/1 | 1ms | 80ms | 395ms |
| neg/launch_app | 1 | 0/1 | 0/1 | 0/1 | 2ms | 63ms | 354ms |
| neg/list_calendar_events | 1 | 1/1 | 1/1 | 0/1 | 3ms | 80ms | 389ms |
| neg/list_folder_contents | 1 | 1/1 | 0/1 | 0/1 | 3ms | 206ms | 371ms |
| neg/manage_file | 1 | 1/1 | 0/1 | 0/1 | 3ms | 109ms | 358ms |
| neg/move_calendar_event | 1 | 1/1 | 1/1 | 0/1 | 3ms | 70ms | 404ms |
| neg/open_browser_url | 1 | 0/1 | 1/1 | 0/1 | 2ms | 74ms | 396ms |
| neg/open_file | 1 | 0/1 | 0/1 | 0/1 | 2ms | 72ms | 452ms |
| neg/open_folder | 1 | 1/1 | 1/1 | 0/1 | 6ms | 122ms | 338ms |
| neg/play_youtube | 1 | 0/1 | 1/1 | 0/1 | 1ms | 74ms | 426ms |
| neg/play_youtube_music | 1 | 1/1 | 1/1 | 0/1 | 3ms | 78ms | 448ms |
| neg/read_file | 1 | 1/1 | 1/1 | 0/1 | 3ms | 80ms | 365ms |
| neg/read_latest_email | 1 | 1/1 | 1/1 | 0/1 | 3ms | 75ms | 429ms |
| neg/read_notes | 1 | 1/1 | 1/1 | 0/1 | 3ms | 115ms | 333ms |
| neg/save_note | 1 | 1/1 | 1/1 | 0/1 | 3ms | 130ms | 334ms |
| neg/search_file | 1 | 1/1 | 1/1 | 0/1 | 3ms | 118ms | 330ms |
| neg/search_google | 1 | 0/1 | 1/1 | 0/1 | 2ms | 122ms | 330ms |
| neg/select_file_candidate | 1 | 0/1 | 1/1 | 0/1 | 2ms | 107ms | 319ms |
| neg/set_reminder | 1 | 0/1 | 1/1 | 0/1 | 1ms | 78ms | 375ms |
| neg/set_voice_mode | 1 | 1/1 | 1/1 | 0/1 | 3ms | 71ms | 371ms |
| neg/set_volume | 1 | 0/1 | 1/1 | 0/1 | 1ms | 125ms | 310ms |
| neg/show_memories | 1 | 1/1 | 1/1 | 0/1 | 3ms | 128ms | 326ms |
| neg/shutdown_assistant | 1 | 1/1 | 0/1 | 0/1 | 3ms | 118ms | 316ms |
| neg/start_dictation | 1 | 0/1 | 1/1 | 0/1 | 2ms | 76ms | 427ms |
| neg/start_focus_session | 1 | 1/1 | 1/1 | 0/1 | 3ms | 77ms | 385ms |
| neg/summarize_file | 1 | 1/1 | 0/1 | 0/1 | 3ms | 170ms | 352ms |
| neg/summarize_inbox | 1 | 1/1 | 1/1 | 0/1 | 3ms | 121ms | 354ms |
| neg/take_screenshot | 1 | 1/1 | 1/1 | 0/1 | 5ms | 79ms | 447ms |
| open_browser_url | 6 | 0/6 | 6/6 | 6/6 | 2ms | 96ms | 399ms |
| open_file | 6 | 5/6 | 6/6 | 6/6 | 2ms | 89ms | 400ms |
| open_folder | 5 | 0/5 | 5/5 | 5/5 | 2ms | 73ms | 355ms |
| play_youtube | 5 | 3/5 | 0/5 | 3/5 | 1ms | 125ms | 407ms |
| play_youtube_music | 6 | 4/6 | 6/6 | 6/6 | 1ms | 94ms | 414ms |
| read_file | 6 | 4/6 | 6/6 | 3/6 | 2ms | 98ms | 398ms |
| read_latest_email | 6 | 0/6 | 4/6 | 4/6 | 3ms | 100ms | 403ms |
| read_notes | 6 | 2/6 | 6/6 | 6/6 | 2ms | 70ms | 367ms |
| save_note | 6 | 5/6 | 6/6 | 4/6 | 2ms | 97ms | 366ms |
| search_file | 6 | 5/6 | 6/6 | 4/6 | 2ms | 98ms | 363ms |
| search_google | 6 | 4/6 | 2/6 | 6/6 | 1ms | 100ms | 395ms |
| select_file_candidate | 6 | 2/6 | 4/6 | 1/6 | 3ms | 93ms | 415ms |
| set_reminder | 6 | 4/6 | 5/6 | 6/6 | 1ms | 82ms | 366ms |
| set_voice_mode | 5 | 1/5 | 5/5 | 1/5 | 3ms | 133ms | 375ms |
| set_volume | 6 | 6/6 | 6/6 | 6/6 | 1ms | 74ms | 353ms |
| show_memories | 5 | 0/5 | 4/5 | 4/5 | 3ms | 134ms | 383ms |
| shutdown_assistant | 5 | 5/5 | 5/5 | 5/5 | 2ms | 74ms | 356ms |
| start_dictation | 5 | 2/5 | 5/5 | 5/5 | 2ms | 123ms | 375ms |
| start_focus_session | 6 | 1/6 | 6/6 | 6/6 | 2ms | 132ms | 435ms |
| summarize_file | 6 | 4/6 | 6/6 | 4/6 | 2ms | 84ms | 409ms |
| summarize_inbox | 6 | 0/6 | 6/6 | 5/6 | 3ms | 113ms | 389ms |
| take_screenshot | 5 | 4/5 | 4/5 | 5/5 | 1ms | 78ms | 377ms |

## Per-tool metrics — `current`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 56 | 43 | 107 | 13 | 165 | 0.287 | 0.768 | 0.417 |
| `browser_media_control` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `cancel_dictation` | 6 | 2 | 0 | 4 | 322 | 1.000 | 0.333 | 0.500 |
| `confirm_no` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `confirm_yes` | 6 | 1 | 0 | 5 | 322 | 1.000 | 0.167 | 0.286 |
| `create_calendar_event` | 6 | 5 | 0 | 1 | 322 | 1.000 | 0.833 | 0.909 |
| `delete_memory` | 6 | 1 | 0 | 5 | 322 | 1.000 | 0.167 | 0.286 |
| `disable_voice` | 6 | 3 | 0 | 3 | 322 | 1.000 | 0.500 | 0.667 |
| `end_focus_session` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `get_friday_status` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `get_time` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `get_weather` | 6 | 3 | 0 | 3 | 322 | 1.000 | 0.500 | 0.667 |
| `greet` | 6 | 4 | 14 | 2 | 308 | 0.222 | 0.667 | 0.333 |
| `launch_app` | 6 | 5 | 17 | 1 | 305 | 0.227 | 0.833 | 0.357 |
| `list_calendar_events` | 6 | 3 | 0 | 3 | 322 | 1.000 | 0.500 | 0.667 |
| `list_folder_contents` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `list_reminders` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `manage_file` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `open_browser_url` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `open_file` | 6 | 5 | 9 | 1 | 313 | 0.357 | 0.833 | 0.500 |
| `play_youtube_music` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `read_file` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `read_latest_email` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `read_notes` | 6 | 2 | 0 | 4 | 322 | 1.000 | 0.333 | 0.500 |
| `save_note` | 6 | 5 | 0 | 1 | 322 | 1.000 | 0.833 | 0.909 |
| `search_file` | 6 | 5 | 7 | 1 | 315 | 0.417 | 0.833 | 0.556 |
| `search_google` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `select_file_candidate` | 6 | 2 | 0 | 4 | 322 | 1.000 | 0.333 | 0.500 |
| `set_reminder` | 6 | 4 | 1 | 2 | 321 | 0.800 | 0.667 | 0.727 |
| `set_volume` | 6 | 6 | 3 | 0 | 319 | 0.667 | 1.000 | 0.800 |
| `start_focus_session` | 6 | 1 | 0 | 5 | 322 | 1.000 | 0.167 | 0.286 |
| `summarize_file` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `summarize_inbox` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `cancel_calendar_event` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `enable_voice` | 5 | 2 | 0 | 3 | 323 | 1.000 | 0.400 | 0.571 |
| `end_dictation` | 5 | 3 | 0 | 2 | 323 | 1.000 | 0.600 | 0.750 |
| `focus_session_status` | 5 | 3 | 0 | 2 | 323 | 1.000 | 0.600 | 0.750 |
| `get_battery` | 5 | 2 | 0 | 3 | 323 | 1.000 | 0.400 | 0.571 |
| `get_cpu_ram` | 5 | 3 | 0 | 2 | 323 | 1.000 | 0.600 | 0.750 |
| `get_date` | 5 | 1 | 0 | 4 | 323 | 1.000 | 0.200 | 0.333 |
| `get_system_status` | 5 | 3 | 0 | 2 | 323 | 1.000 | 0.600 | 0.750 |
| `move_calendar_event` | 5 | 2 | 0 | 3 | 323 | 1.000 | 0.400 | 0.571 |
| `open_folder` | 5 | 0 | 0 | 5 | 323 | 0.000 | 0.000 | 0.000 |
| `play_youtube` | 5 | 3 | 3 | 2 | 320 | 0.500 | 0.600 | 0.545 |
| `set_voice_mode` | 5 | 1 | 0 | 4 | 323 | 1.000 | 0.200 | 0.333 |
| `show_memories` | 5 | 0 | 0 | 5 | 323 | 0.000 | 0.000 | 0.000 |
| `shutdown_assistant` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `start_dictation` | 5 | 2 | 0 | 3 | 323 | 1.000 | 0.400 | 0.571 |
| `take_screenshot` | 5 | 4 | 0 | 1 | 323 | 1.000 | 0.800 | 0.889 |

## Per-tool metrics — `gemma`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 56 | 47 | 42 | 9 | 230 | 0.528 | 0.839 | 0.648 |
| `browser_media_control` | 6 | 5 | 0 | 1 | 322 | 1.000 | 0.833 | 0.909 |
| `cancel_dictation` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `confirm_no` | 6 | 5 | 1 | 1 | 321 | 0.833 | 0.833 | 0.833 |
| `confirm_yes` | 6 | 5 | 1 | 1 | 321 | 0.833 | 0.833 | 0.833 |
| `create_calendar_event` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `delete_memory` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `disable_voice` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `end_focus_session` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `get_friday_status` | 6 | 0 | 0 | 6 | 322 | 0.000 | 0.000 | 0.000 |
| `get_time` | 6 | 2 | 1 | 4 | 321 | 0.667 | 0.333 | 0.444 |
| `get_weather` | 6 | 1 | 0 | 5 | 322 | 1.000 | 0.167 | 0.286 |
| `greet` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `launch_app` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `list_calendar_events` | 6 | 3 | 0 | 3 | 322 | 1.000 | 0.500 | 0.667 |
| `list_folder_contents` | 6 | 1 | 0 | 5 | 322 | 1.000 | 0.167 | 0.286 |
| `list_reminders` | 6 | 0 | 2 | 6 | 320 | 0.000 | 0.000 | 0.000 |
| `manage_file` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `open_browser_url` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `open_file` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `play_youtube_music` | 6 | 6 | 6 | 0 | 316 | 0.500 | 1.000 | 0.667 |
| `read_file` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `read_latest_email` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `read_notes` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `save_note` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `search_file` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `search_google` | 6 | 2 | 0 | 4 | 322 | 1.000 | 0.333 | 0.500 |
| `select_file_candidate` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `set_reminder` | 6 | 5 | 3 | 1 | 319 | 0.625 | 0.833 | 0.714 |
| `set_volume` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `start_focus_session` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `summarize_file` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `summarize_inbox` | 6 | 6 | 4 | 0 | 318 | 0.600 | 1.000 | 0.750 |
| `cancel_calendar_event` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `enable_voice` | 5 | 4 | 0 | 1 | 323 | 1.000 | 0.800 | 0.889 |
| `end_dictation` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `focus_session_status` | 5 | 4 | 0 | 1 | 323 | 1.000 | 0.800 | 0.889 |
| `get_battery` | 5 | 1 | 0 | 4 | 323 | 1.000 | 0.200 | 0.333 |
| `get_cpu_ram` | 5 | 1 | 0 | 4 | 323 | 1.000 | 0.200 | 0.333 |
| `get_date` | 5 | 2 | 1 | 3 | 322 | 0.667 | 0.400 | 0.500 |
| `get_system_status` | 5 | 1 | 0 | 4 | 323 | 1.000 | 0.200 | 0.333 |
| `move_calendar_event` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `open_folder` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `play_youtube` | 5 | 0 | 0 | 5 | 323 | 0.000 | 0.000 | 0.000 |
| `set_voice_mode` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `show_memories` | 5 | 4 | 3 | 1 | 320 | 0.571 | 0.800 | 0.667 |
| `shutdown_assistant` | 5 | 5 | 1 | 0 | 322 | 0.833 | 1.000 | 0.909 |
| `start_dictation` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `take_screenshot` | 5 | 4 | 0 | 1 | 323 | 1.000 | 0.800 | 0.889 |

## Per-tool metrics — `fn-gemma`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 56 | 0 | 0 | 56 | 272 | 0.000 | 0.000 | 0.000 |
| `browser_media_control` | 6 | 5 | 4 | 1 | 318 | 0.556 | 0.833 | 0.667 |
| `cancel_dictation` | 6 | 2 | 0 | 4 | 322 | 1.000 | 0.333 | 0.500 |
| `confirm_no` | 6 | 5 | 2 | 1 | 320 | 0.714 | 0.833 | 0.769 |
| `confirm_yes` | 6 | 5 | 3 | 1 | 319 | 0.625 | 0.833 | 0.714 |
| `create_calendar_event` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `delete_memory` | 6 | 5 | 2 | 1 | 320 | 0.714 | 0.833 | 0.769 |
| `disable_voice` | 6 | 4 | 2 | 2 | 320 | 0.667 | 0.667 | 0.667 |
| `end_focus_session` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `get_friday_status` | 6 | 5 | 9 | 1 | 313 | 0.357 | 0.833 | 0.500 |
| `get_time` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `get_weather` | 6 | 5 | 1 | 1 | 321 | 0.833 | 0.833 | 0.833 |
| `greet` | 6 | 5 | 1 | 1 | 321 | 0.833 | 0.833 | 0.833 |
| `launch_app` | 6 | 5 | 2 | 1 | 320 | 0.714 | 0.833 | 0.769 |
| `list_calendar_events` | 6 | 5 | 0 | 1 | 322 | 1.000 | 0.833 | 0.909 |
| `list_folder_contents` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `list_reminders` | 6 | 4 | 1 | 2 | 321 | 0.800 | 0.667 | 0.727 |
| `manage_file` | 6 | 5 | 1 | 1 | 321 | 0.833 | 0.833 | 0.833 |
| `open_browser_url` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `open_file` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `play_youtube_music` | 6 | 6 | 3 | 0 | 319 | 0.667 | 1.000 | 0.800 |
| `read_file` | 6 | 3 | 3 | 3 | 319 | 0.500 | 0.500 | 0.500 |
| `read_latest_email` | 6 | 4 | 2 | 2 | 320 | 0.667 | 0.667 | 0.667 |
| `read_notes` | 6 | 6 | 0 | 0 | 322 | 1.000 | 1.000 | 1.000 |
| `save_note` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `search_file` | 6 | 4 | 0 | 2 | 322 | 1.000 | 0.667 | 0.800 |
| `search_google` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `select_file_candidate` | 6 | 1 | 0 | 5 | 322 | 1.000 | 0.167 | 0.286 |
| `set_reminder` | 6 | 6 | 10 | 0 | 312 | 0.375 | 1.000 | 0.545 |
| `set_volume` | 6 | 6 | 1 | 0 | 321 | 0.857 | 1.000 | 0.923 |
| `start_focus_session` | 6 | 6 | 2 | 0 | 320 | 0.750 | 1.000 | 0.857 |
| `summarize_file` | 6 | 4 | 1 | 2 | 321 | 0.800 | 0.667 | 0.727 |
| `summarize_inbox` | 6 | 5 | 3 | 1 | 319 | 0.625 | 0.833 | 0.714 |
| `cancel_calendar_event` | 5 | 5 | 3 | 0 | 320 | 0.625 | 1.000 | 0.769 |
| `enable_voice` | 5 | 4 | 3 | 1 | 320 | 0.571 | 0.800 | 0.667 |
| `end_dictation` | 5 | 4 | 2 | 1 | 321 | 0.667 | 0.800 | 0.727 |
| `focus_session_status` | 5 | 5 | 6 | 0 | 317 | 0.455 | 1.000 | 0.625 |
| `get_battery` | 5 | 5 | 1 | 0 | 322 | 0.833 | 1.000 | 0.909 |
| `get_cpu_ram` | 5 | 5 | 1 | 0 | 322 | 0.833 | 1.000 | 0.909 |
| `get_date` | 5 | 4 | 1 | 1 | 322 | 0.800 | 0.800 | 0.800 |
| `get_system_status` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `move_calendar_event` | 5 | 5 | 1 | 0 | 322 | 0.833 | 1.000 | 0.909 |
| `open_folder` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `play_youtube` | 5 | 3 | 0 | 2 | 323 | 1.000 | 0.600 | 0.750 |
| `set_voice_mode` | 5 | 1 | 1 | 4 | 322 | 0.500 | 0.200 | 0.286 |
| `show_memories` | 5 | 4 | 1 | 1 | 322 | 0.800 | 0.800 | 0.800 |
| `shutdown_assistant` | 5 | 5 | 4 | 0 | 319 | 0.556 | 1.000 | 0.714 |
| `start_dictation` | 5 | 5 | 0 | 0 | 323 | 1.000 | 1.000 | 1.000 |
| `take_screenshot` | 5 | 5 | 1 | 0 | 322 | 0.833 | 1.000 | 0.909 |

## Per-case detail

| # | Utterance | Expected | current | current ✓ | current ms | gemma | gemma ✓ | gemma ms | fn-gemma | fn-gemma ✓ | fn-gemma ms | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `real quick - what you've learned about me` | `show_memories` | `llm_chat` | ✗ | 14 | `show_memories` | ✓ | 406 | `show_memories` | ✓ | 4120 | synth/query |
| 2 | `uh hey, the temperature in tokyo` | `get_weather` | `get_weather` | ✓ | 2 | `get_weather` | ✓ | 71 | `get_weather` | ✓ | 400 | synth/query |
| 3 | `real quick, mute the audio` | `set_volume` | `set_volume` | ✓ | 2 | `set_volume` | ✓ | 72 | `set_volume` | ✓ | 372 | synth/command |
| 4 | `any chance you could end the work session` | `end_focus_session` | `llm_chat` | ✗ | 3 | `end_focus_session` | ✓ | 97 | `end_focus_session` | ✓ | 466 | synth/command |
| 5 | `do me a favor and forget what i just said` | `delete_memory` | `llm_chat` | ✗ | 3 | `delete_memory` | ✓ | 87 | `confirm_no` | ✗ | 392 | synth/command |
| 6 | `i need you to switch to on demand listening` | `set_voice_mode` | `llm_chat` | ✗ | 4 | `set_voice_mode` | ✓ | 97 | `focus_session_status` | ✗ | 411 | synth/command |
| 7 | `let's push that call to next week` | `move_calendar_event` | `llm_chat` | ✗ | 3 | `move_calendar_event` | ✓ | 108 | `move_calendar_event` | ✓ | 460 | synth/command |
| 8 | `this milk is past its date` | `llm_chat` | `llm_chat` | ✓ | 2 | `llm_chat` | ✓ | 136 | `get_date` | ✗ | 354 | registry/hard_negative |
| 9 | `how about you open that text file` | `open_file` | `open_file` | ✓ | 1 | `open_file` | ✓ | 69 | `open_file` | ✓ | 398 | synth/command |
| 10 | `actually, tldr this file` | `summarize_file` | `llm_chat` | ✗ | 3 | `summarize_file` | ✓ | 83 | `read_file` | ✗ | 370 | synth/command |
| 11 | `let's open the projects directory` | `open_folder` | `launch_app` | ✗ | 3 | `open_folder` | ✓ | 66 | `open_folder` | ✓ | 339 | synth/command |
| 12 | `any chance you could cancel my meeting at three` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 26 | `cancel_calendar_event` | ✓ | 93 | `cancel_calendar_event` | ✓ | 418 | synth/command |
| 13 | `any chance you could share the one called report` | `select_file_candidate` | `llm_chat` | ✗ | 3 | `select_file_candidate` | ✓ | 98 | `get_friday_status` | ✗ | 396 | synth/query |
| 14 | `real quick, copy the report to desktop` | `manage_file` | `llm_chat` | ✗ | 3 | `manage_file` | ✓ | 77 | `manage_file` | ✓ | 377 | synth/command |
| 15 | `any chance you could share my inbox` | `summarize_inbox` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✓ | 97 | `summarize_inbox` | ✓ | 416 | synth/query |
| 16 | `give me an unpopular opinion` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 74 | `—` | ✗ | 192 | chitchat/seed |
| 17 | `mind telling me current time` | `get_time` | `get_time` | ✓ | 1 | `get_time` | ✓ | 65 | `get_time` | ✓ | 390 | synth/query |
| 18 | `mind telling me system status` | `get_system_status` | `get_system_status` | ✓ | 1 | `llm_chat` | ✗ | 72 | `get_system_status` | ✓ | 389 | synth/query |
| 19 | `would you exit friday` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 29 | `shutdown_assistant` | ✓ | 70 | `shutdown_assistant` | ✓ | 356 | synth/command |
| 20 | `real quick, open the spreadsheet from yesterday` | `open_file` | `launch_app` | ✗ | 3 | `open_file` | ✓ | 76 | `open_file` | ✓ | 418 | synth/command |
| 21 | `real quick - my pomodoro timer` | `focus_session_status` | `llm_chat` | ✗ | 3 | `set_reminder` | ✗ | 66 | `focus_session_status` | ✓ | 410 | synth/query |
| 22 | `mind telling me the one called report` | `select_file_candidate` | `llm_chat` | ✗ | 3 | `select_file_candidate` | ✓ | 90 | `get_friday_status` | ✗ | 420 | synth/query |
| 23 | `i need you to end this pomodoro` | `end_focus_session` | `llm_chat` | ✗ | 3 | `end_focus_session` | ✓ | 99 | `end_focus_session` | ✓ | 407 | synth/command |
| 24 | `see you on friday` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 76 | `shutdown_assistant` | ✗ | 369 | registry/hard_negative |
| 25 | `i'd love to know system status` | `get_system_status` | `get_system_status` | ✓ | 1 | `get_system_status` | ✓ | 85 | `get_system_status` | ✓ | 437 | synth/query |
| 26 | `i need you to read that document aloud` | `read_file` | `llm_chat` | ✗ | 3 | `read_file` | ✓ | 68 | `read_latest_email` | ✗ | 408 | synth/command |
| 27 | `let's open that text file` | `open_file` | `open_file` | ✓ | 2 | `open_file` | ✓ | 66 | `open_file` | ✓ | 402 | synth/command |
| 28 | `i need you to drop that preference` | `delete_memory` | `llm_chat` | ✗ | 3 | `delete_memory` | ✓ | 66 | `delete_memory` | ✓ | 384 | synth/command |
| 29 | `actually, google how to fix a leaky faucet` | `search_google` | `search_google` | ✓ | 1 | `search_google` | ✓ | 75 | `search_google` | ✓ | 447 | synth/command |
| 30 | `i need you to open the anthropic website` | `open_browser_url` | `open_file` | ✗ | 2 | `open_browser_url` | ✓ | 96 | `open_browser_url` | ✓ | 461 | synth/command |
| 31 | `actually, my last unread email` | `read_latest_email` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✗ | 95 | `summarize_inbox` | ✗ | 399 | synth/query |
| 32 | `how about you start listening` | `enable_voice` | `launch_app` | ✗ | 2 | `enable_voice` | ✓ | 101 | `enable_voice` | ✓ | 388 | synth/command |
| 33 | `status quo is fine` | `llm_chat` | `llm_chat` | ✓ | 23 | `llm_chat` | ✓ | 91 | `get_friday_status` | ✗ | 400 | registry/hard_negative |
| 34 | `set in my ways` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 71 | `set_reminder` | ✗ | 371 | registry/hard_negative |
| 35 | `do me a favor and copy the report to desktop` | `manage_file` | `llm_chat` | ✗ | 3 | `manage_file` | ✓ | 73 | `manage_file` | ✓ | 430 | synth/command |
| 36 | `i need you to remind me to take the laundry out` | `set_reminder` | `set_reminder` | ✓ | 1 | `set_reminder` | ✓ | 70 | `set_reminder` | ✓ | 364 | synth/command |
| 37 | `i love a good screen door in summer` | `llm_chat` | `llm_chat` | ✓ | 5 | `llm_chat` | ✓ | 79 | `browser_media_control` | ✗ | 447 | registry/hard_negative |
| 38 | `actually, play the new kendrick album` | `play_youtube_music` | `play_youtube_music` | ✓ | 1 | `play_youtube_music` | ✓ | 91 | `play_youtube_music` | ✓ | 393 | synth/command |
| 39 | `well hello` | `greet` | `greet` | ✓ | 1 | `greet` | ✓ | 39 | `greet` | ✓ | 306 | synth/greet |
| 40 | `real quick, play that funny cat video` | `play_youtube` | `play_youtube` | ✓ | 1 | `play_youtube_music` | ✗ | 91 | `play_youtube` | ✓ | 407 | synth/command |
| 41 | `let's find a file called report` | `search_file` | `search_file` | ✓ | 1 | `search_file` | ✓ | 67 | `open_file` | ✗ | 381 | synth/command |
| 42 | `any advice for a quiet evening` | `llm_chat` | `llm_chat` | ✓ | 2 | `llm_chat` | ✓ | 82 | `set_reminder` | ✗ | 380 | chitchat/seed |
| 43 | `any chance you could start a work session` | `start_focus_session` | `launch_app` | ✗ | 2 | `start_focus_session` | ✓ | 92 | `start_focus_session` | ✓ | 411 | synth/command |
| 44 | `actually, open the anthropic website` | `open_browser_url` | `open_file` | ✗ | 2 | `open_browser_url` | ✓ | 97 | `open_browser_url` | ✓ | 420 | synth/command |
| 45 | `real quick, read the contents of notes.txt` | `read_file` | `read_file` | ✓ | 2 | `read_file` | ✓ | 84 | `—` | ✗ | 863 | synth/command |
| 46 | `do me a favor and begin a deep work block` | `start_focus_session` | `llm_chat` | ✗ | 3 | `start_focus_session` | ✓ | 94 | `start_focus_session` | ✓ | 459 | synth/command |
| 47 | `cancel that thought` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 70 | `cancel_calendar_event` | ✗ | 825 | registry/hard_negative |
| 48 | `let's tldr this file` | `summarize_file` | `llm_chat` | ✗ | 3 | `summarize_file` | ✓ | 81 | `read_file` | ✗ | 429 | synth/command |
| 49 | `uh hey, close your ears` | `disable_voice` | `greet` | ✗ | 1 | `disable_voice` | ✓ | 74 | `shutdown_assistant` | ✗ | 361 | synth/query |
| 50 | `i need you to go ahead` | `confirm_yes` | `llm_chat` | ✗ | 3 | `confirm_yes` | ✓ | 63 | `confirm_yes` | ✓ | 406 | synth/command |
| 51 | `would you mind sharing the gmail backlog` | `summarize_inbox` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✓ | 97 | `summarize_file` | ✗ | 383 | synth/query |
| 52 | `any chance you could share the weather today` | `get_weather` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 78 | `get_weather` | ✓ | 371 | synth/query |
| 53 | `i need you to summarize this pdf` | `summarize_file` | `summarize_file` | ✓ | 2 | `summarize_file` | ✓ | 86 | `summarize_file` | ✓ | 451 | synth/command |
| 54 | `forget me not flowers` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 92 | `delete_memory` | ✗ | 350 | registry/hard_negative |
| 55 | `got a sec - what's on my desktop` | `list_folder_contents` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 88 | `list_folder_contents` | ✓ | 428 | synth/query |
| 56 | `got a sec - the charge` | `get_battery` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 90 | `get_battery` | ✓ | 338 | synth/query |
| 57 | `memory of last summer` | `llm_chat` | `search_file` | ✗ | 2 | `llm_chat` | ✓ | 92 | `get_friday_status` | ✗ | 419 | registry/hard_negative |
| 58 | `marital status update` | `llm_chat` | `search_file` | ✗ | 1 | `llm_chat` | ✓ | 76 | `get_friday_status` | ✗ | 430 | registry/hard_negative |
| 59 | `let's add a dentist appointment friday` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `create_calendar_event` | ✓ | 98 | `create_calendar_event` | ✓ | 395 | synth/command |
| 60 | `mind telling me what reminders i have` | `list_reminders` | `list_reminders` | ✓ | 1 | `llm_chat` | ✗ | 82 | `get_reminders` | ✗ | 397 | synth/query |
| 61 | `real quick, exit friday` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 2 | `shutdown_assistant` | ✓ | 67 | `shutdown_assistant` | ✓ | 361 | synth/command |
| 62 | `real quick, turn the volume up` | `set_volume` | `set_volume` | ✓ | 1 | `set_volume` | ✓ | 75 | `set_volume` | ✓ | 334 | synth/command |
| 63 | `do me a favor and google how to fix a leaky faucet` | `search_google` | `search_google` | ✓ | 1 | `search_google` | ✓ | 69 | `search_google` | ✓ | 409 | synth/command |
| 64 | `uh hey, will it rain tomorrow` | `get_weather` | `greet` | ✗ | 1 | `llm_chat` | ✗ | 82 | `get_weather` | ✓ | 355 | synth/query |
| 65 | `real quick, google the price of bitcoin` | `search_google` | `search_google` | ✓ | 1 | `llm_chat` | ✗ | 76 | `search_google` | ✓ | 421 | synth/command |
| 66 | `do me a favor and start vscode` | `launch_app` | `launch_app` | ✓ | 2 | `launch_app` | ✓ | 72 | `launch_app` | ✓ | 367 | synth/command |
| 67 | `any chance you could share computer status` | `get_system_status` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 82 | `get_system_status` | ✓ | 433 | synth/query |
| 68 | `let's take a screenshot` | `take_screenshot` | `take_screenshot` | ✓ | 1 | `take_screenshot` | ✓ | 78 | `take_screenshot` | ✓ | 377 | synth/command |
| 69 | `any chance you could move lunch to tuesday` | `move_calendar_event` | `llm_chat` | ✗ | 3 | `move_calendar_event` | ✓ | 128 | `move_calendar_event` | ✓ | 413 | synth/command |
| 70 | `play me like a fiddle` | `llm_chat` | `play_youtube` | ✗ | 1 | `llm_chat` | ✓ | 74 | `play_youtube_music` | ✗ | 426 | registry/hard_negative |
| 71 | `any chance you could turn the volume down` | `set_volume` | `set_volume` | ✓ | 1 | `set_volume` | ✓ | 74 | `set_volume` | ✓ | 377 | synth/command |
| 72 | `got a sec - friday's state` | `get_friday_status` | `llm_chat` | ✗ | 3 | `get_date` | ✗ | 67 | `get_friday_status` | ✓ | 419 | synth/query |
| 73 | `alright yeah` | `confirm_yes` | `llm_chat` | ✗ | 6 | `llm_chat` | ✗ | 70 | `confirm_yes` | ✓ | 494 | synth/confirm |
| 74 | `how about you turn off voice input` | `disable_voice` | `disable_voice` | ✓ | 2 | `disable_voice` | ✓ | 65 | `disable_voice` | ✓ | 357 | synth/command |
| 75 | `the end justifies the means` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 79 | `end_focus_session` | ✗ | 426 | registry/hard_negative |
| 76 | `actually, what's on my calendar` | `list_calendar_events` | `list_calendar_events` | ✓ | 1 | `list_calendar_events` | ✓ | 90 | `list_calendar_events` | ✓ | 425 | synth/query |
| 77 | `how about you add a dentist appointment friday` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `create_calendar_event` | ✓ | 92 | `create_calendar_event` | ✓ | 425 | synth/command |
| 78 | `let's stop dictation` | `end_dictation` | `end_dictation` | ✓ | 1 | `end_dictation` | ✓ | 85 | `end_dictation` | ✓ | 430 | synth/command |
| 79 | `the end of the workday` | `llm_chat` | `llm_chat` | ✓ | 3 | `end_focus_session` | ✗ | 90 | `shutdown_assistant` | ✗ | 377 | registry/hard_negative |
| 80 | `real quick, snap a screenshot` | `take_screenshot` | `take_screenshot` | ✓ | 1 | `llm_chat` | ✗ | 78 | `take_screenshot` | ✓ | 396 | synth/command |
| 81 | `do me a favor and open chrome` | `launch_app` | `launch_app` | ✓ | 2 | `launch_app` | ✓ | 109 | `launch_app` | ✓ | 375 | synth/command |
| 82 | `let's go ahead` | `confirm_yes` | `llm_chat` | ✗ | 3 | `confirm_yes` | ✓ | 65 | `confirm_no` | ✗ | 363 | synth/command |
| 83 | `any chance you could share battery level` | `get_battery` | `get_battery` | ✓ | 1 | `llm_chat` | ✗ | 78 | `get_battery` | ✓ | 448 | synth/query |
| 84 | `i can read you like a book` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 80 | `read_file` | ✗ | 365 | registry/hard_negative |
| 85 | `would you mind sharing how is the system` | `get_system_status` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 85 | `get_system_status` | ✓ | 438 | synth/query |
| 86 | `let's end transcribing` | `end_dictation` | `llm_chat` | ✗ | 3 | `end_dictation` | ✓ | 81 | `end_focus_session` | ✗ | 406 | synth/command |
| 87 | `let's open my documents folder` | `open_folder` | `open_file` | ✗ | 1 | `open_folder` | ✓ | 65 | `open_folder` | ✓ | 351 | synth/command |
| 88 | `would you delete the draft` | `manage_file` | `llm_chat` | ✗ | 3 | `manage_file` | ✓ | 68 | `delete_memory` | ✗ | 423 | synth/command |
| 89 | `how about you read that document aloud` | `read_file` | `read_file` | ✓ | 2 | `read_file` | ✓ | 70 | `read_latest_email` | ✗ | 402 | synth/command |
| 90 | `actually, delete the draft` | `manage_file` | `llm_chat` | ✗ | 2 | `manage_file` | ✓ | 63 | `manage_file` | ✓ | 394 | synth/command |
| 91 | `uh hey, the newest email` | `read_latest_email` | `greet` | ✗ | 1 | `read_latest_email` | ✓ | 93 | `read_latest_email` | ✓ | 395 | synth/query |
| 92 | `let's turn on the mic` | `enable_voice` | `enable_voice` | ✓ | 2 | `enable_voice` | ✓ | 73 | `enable_voice` | ✓ | 362 | synth/command |
| 93 | `any chance you could open your ears` | `enable_voice` | `launch_app` | ✗ | 2 | `enable_voice` | ✓ | 69 | `enable_voice` | ✓ | 435 | synth/command |
| 94 | `would you end this pomodoro` | `end_focus_session` | `llm_chat` | ✗ | 3 | `end_focus_session` | ✓ | 128 | `end_focus_session` | ✓ | 404 | synth/command |
| 95 | `uh hey, my inbox` | `summarize_inbox` | `greet` | ✗ | 1 | `summarize_inbox` | ✓ | 89 | `summarize_inbox` | ✓ | 411 | synth/query |
| 96 | `the suspect was charged with battery` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 82 | `get_battery` | ✗ | 401 | registry/hard_negative |
| 97 | `real quick, drop what i was dictating` | `cancel_dictation` | `llm_chat` | ✗ | 3 | `cancel_dictation` | ✓ | 82 | `end_dictation` | ✗ | 403 | synth/command |
| 98 | `yeah do it` | `confirm_yes` | `confirm_yes` | ✓ | 2 | `confirm_yes` | ✓ | 66 | `confirm_yes` | ✓ | 421 | synth/confirm |
| 99 | `hi was the highest grossing film` | `llm_chat` | `greet` | ✗ | 1 | `llm_chat` | ✓ | 80 | `get_cpu_ram` | ✗ | 395 | registry/hard_negative |
| 100 | `uh hey, the contents of documents` | `list_folder_contents` | `greet` | ✗ | 1 | `summarize_file` | ✗ | 78 | `list_folder_contents` | ✓ | 413 | synth/query |
| 101 | `real quick, give me a summary of that doc` | `summarize_file` | `summarize_file` | ✓ | 2 | `summarize_file` | ✓ | 84 | `summarize_file` | ✓ | 400 | synth/command |
| 102 | `would you fire up obs` | `launch_app` | `llm_chat` | ✗ | 3 | `launch_app` | ✓ | 68 | `launch_app` | ✓ | 389 | synth/command |
| 103 | `any chance you could end the dictation now` | `end_dictation` | `end_dictation` | ✓ | 1 | `end_dictation` | ✓ | 85 | `end_dictation` | ✓ | 443 | synth/command |
| 104 | `i need you to play the deep focus playlist` | `play_youtube_music` | `play_youtube_music` | ✓ | 1 | `play_youtube_music` | ✓ | 93 | `play_youtube_music` | ✓ | 399 | synth/command |
| 105 | `any chance you could summarize this pdf` | `summarize_file` | `summarize_file` | ✓ | 2 | `summarize_file` | ✓ | 81 | `summarize_file` | ✓ | 417 | synth/command |
| 106 | `would you mind sharing what mode you're in` | `get_friday_status` | `llm_chat` | ✗ | 3 | `show_memories` | ✗ | 147 | `focus_session_status` | ✗ | 428 | synth/query |
| 107 | `do me a favor and open that folder` | `open_folder` | `launch_app` | ✗ | 2 | `open_folder` | ✓ | 73 | `open_folder` | ✓ | 396 | synth/command |
| 108 | `any chance you could play jazz piano` | `play_youtube_music` | `play_youtube` | ✗ | 1 | `play_youtube_music` | ✓ | 88 | `play_youtube_music` | ✓ | 430 | synth/command |
| 109 | `i hate email chains` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 75 | `summarize_inbox` | ✗ | 429 | registry/hard_negative |
| 110 | `actually, processor load` | `get_cpu_ram` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 77 | `get_cpu_ram` | ✓ | 458 | synth/query |
| 111 | `real quick, add a dentist appointment friday` | `create_calendar_event` | `create_calendar_event` | ✓ | 7 | `create_calendar_event` | ✓ | 86 | `create_calendar_event` | ✓ | 400 | synth/command |
| 112 | `real quick - ram usage` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 1 | `llm_chat` | ✗ | 81 | `get_cpu_ram` | ✓ | 427 | synth/query |
| 113 | `i need you to set an alarm for nine am` | `set_reminder` | `llm_chat` | ✗ | 3 | `set_reminder` | ✓ | 72 | `set_reminder` | ✓ | 368 | synth/command |
| 114 | `would you make a quick note about the demo` | `save_note` | `save_note` | ✓ | 2 | `save_note` | ✓ | 78 | `save_note` | ✓ | 371 | synth/command |
| 115 | `would you mute the mic for a bit` | `disable_voice` | `set_volume` | ✗ | 2 | `disable_voice` | ✓ | 85 | `disable_voice` | ✓ | 433 | synth/command |
| 116 | `real quick - the first one` | `select_file_candidate` | `select_file_candidate` | ✓ | 2 | `llm_chat` | ✗ | 79 | `confirm_yes` | ✗ | 362 | synth/query |
| 117 | `i need you to cancel` | `confirm_no` | `llm_chat` | ✗ | 3 | `confirm_no` | ✓ | 76 | `cancel_calendar_event` | ✗ | 510 | synth/command |
| 118 | `actually, reschedule the meeting to four pm` | `move_calendar_event` | `move_calendar_event` | ✓ | 1 | `move_calendar_event` | ✓ | 137 | `move_calendar_event` | ✓ | 400 | synth/command |
| 119 | `do me a favor and play lofi study beats` | `play_youtube` | `llm_chat` | ✗ | 3 | `play_youtube_music` | ✗ | 105 | `play_youtube_music` | ✗ | 447 | synth/command |
| 120 | `actually, what you've learned about me` | `show_memories` | `llm_chat` | ✗ | 3 | `show_memories` | ✓ | 89 | `show_memories` | ✓ | 394 | synth/query |
| 121 | `any chance you could open chrome` | `launch_app` | `launch_app` | ✓ | 2 | `launch_app` | ✓ | 69 | `launch_app` | ✓ | 375 | synth/command |
| 122 | `let's save a note that the wifi password is changed` | `save_note` | `save_note` | ✓ | 2 | `save_note` | ✓ | 75 | `save_note` | ✓ | 415 | synth/command |
| 123 | `i'm overscheduled this month` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 80 | `set_reminder` | ✗ | 389 | registry/hard_negative |
| 124 | `would you mind sharing system status` | `get_system_status` | `get_system_status` | ✓ | 1 | `llm_chat` | ✗ | 81 | `get_system_status` | ✓ | 428 | synth/query |
| 125 | `do me a favor and save a note saying call the plumber` | `save_note` | `llm_chat` | ✗ | 3 | `save_note` | ✓ | 73 | `save_note` | ✓ | 365 | synth/command |
| 126 | `how about you cancel my meeting at three` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `cancel_calendar_event` | ✓ | 98 | `cancel_calendar_event` | ✓ | 394 | synth/command |
| 127 | `i need to create some space in my life` | `llm_chat` | `llm_chat` | ✓ | 4 | `llm_chat` | ✓ | 90 | `create_calendar_event` | ✗ | 444 | registry/hard_negative |
| 128 | `would you mind sharing what time it is` | `get_time` | `get_time` | ✓ | 1 | `llm_chat` | ✗ | 110 | `get_time` | ✓ | 391 | synth/query |
| 129 | `any chance you could forget what i just said` | `delete_memory` | `llm_chat` | ✗ | 3 | `delete_memory` | ✓ | 99 | `delete_memory` | ✓ | 392 | synth/command |
| 130 | `i need you to shut down friday` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 2 | `shutdown_assistant` | ✓ | 74 | `shutdown_assistant` | ✓ | 356 | synth/command |
| 131 | `real quick, find files named invoice` | `search_file` | `search_file` | ✓ | 1 | `search_file` | ✓ | 65 | `list_folder_contents` | ✗ | 420 | synth/command |
| 132 | `do me a favor and pause the music` | `browser_media_control` | `llm_chat` | ✗ | 3 | `browser_media_control` | ✓ | 103 | `start_focus_session` | ✗ | 745 | synth/command |
| 133 | `launch a missile in halo` | `llm_chat` | `launch_app` | ✗ | 2 | `launch_app` | ✗ | 63 | `launch_app` | ✗ | 354 | registry/hard_negative |
| 134 | `mind telling me the notes from yesterday` | `read_notes` | `llm_chat` | ✗ | 3 | `read_notes` | ✓ | 70 | `read_notes` | ✓ | 431 | synth/query |
| 135 | `mind telling me my alarms` | `list_reminders` | `llm_chat` | ✗ | 3 | `set_reminder` | ✗ | 61 | `set_reminder` | ✗ | 347 | synth/query |
| 136 | `you remind me of someone` | `llm_chat` | `set_reminder` | ✗ | 1 | `llm_chat` | ✓ | 78 | `set_reminder` | ✗ | 375 | registry/hard_negative |
| 137 | `share a thought worth thinking about` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 84 | `share` | ✗ | 332 | chitchat/seed |
| 138 | `real quick, switch to on demand listening` | `set_voice_mode` | `llm_chat` | ✗ | 3 | `set_voice_mode` | ✓ | 100 | `focus_session_status` | ✗ | 435 | synth/command |
| 139 | `uh hey, files in this folder` | `list_folder_contents` | `greet` | ✗ | 1 | `list_folder_contents` | ✓ | 92 | `list_folder_contents` | ✓ | 453 | synth/query |
| 140 | `start a fire in the pit` | `llm_chat` | `launch_app` | ✗ | 2 | `llm_chat` | ✓ | 76 | `start_focus_session` | ✗ | 427 | registry/hard_negative |
| 141 | `tell me what you'd do if you were human` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 133 | `get_friday_status` | ✗ | 455 | chitchat/seed |
| 142 | `lose focus` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 77 | `focus_session_status` | ✗ | 385 | registry/hard_negative |
| 143 | `okay no` | `confirm_no` | `llm_chat` | ✗ | 2 | `confirm_no` | ✓ | 65 | `confirm_no` | ✓ | 500 | synth/confirm |
| 144 | `would you turn the volume up` | `set_volume` | `set_volume` | ✓ | 1 | `set_volume` | ✓ | 68 | `set_volume` | ✓ | 406 | synth/command |
| 145 | `what's the one thing worth remembering today` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 90 | `get_memories` | ✗ | 429 | chitchat/seed |
| 146 | `well hey` | `greet` | `greet` | ✓ | 5 | `greet` | ✓ | 41 | `greet` | ✓ | 366 | synth/greet |
| 147 | `would you open github.com` | `open_browser_url` | `open_file` | ✗ | 2 | `open_browser_url` | ✓ | 90 | `open_browser_url` | ✓ | 418 | synth/command |
| 148 | `actually, turn off voice input` | `disable_voice` | `disable_voice` | ✓ | 2 | `disable_voice` | ✓ | 72 | `disable_voice` | ✓ | 380 | synth/command |
| 149 | `the movers come monday` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 70 | `gather_friday_args` | ✗ | 404 | registry/hard_negative |
| 150 | `would you mind sharing upcoming meetings` | `list_calendar_events` | `llm_chat` | ✗ | 3 | `list_reminders` | ✗ | 84 | `list_calendar_events` | ✓ | 395 | synth/query |
| 151 | `open the meeting with introductions` | `llm_chat` | `open_file` | ✗ | 2 | `open_file` | ✗ | 72 | `open_file` | ✗ | 452 | registry/hard_negative |
| 152 | `uh hey, the notes from yesterday` | `read_notes` | `greet` | ✗ | 1 | `read_notes` | ✓ | 68 | `read_notes` | ✓ | 371 | synth/query |
| 153 | `i need you to open discord` | `launch_app` | `launch_app` | ✓ | 2 | `launch_app` | ✓ | 75 | `open_browser_url` | ✗ | 450 | synth/command |
| 154 | `what's a fun fact you like` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 128 | `show_memories` | ✗ | 414 | chitchat/seed |
| 155 | `any chance you could share upcoming meetings` | `list_calendar_events` | `llm_chat` | ✗ | 3 | `list_reminders` | ✗ | 85 | `list_calendar_events` | ✓ | 454 | synth/query |
| 156 | `let's move that to downloads` | `manage_file` | `llm_chat` | ✗ | 3 | `manage_file` | ✓ | 69 | `manage_file` | ✓ | 406 | synth/command |
| 157 | `i'd love to know the most recent message` | `read_latest_email` | `llm_chat` | ✗ | 3 | `read_latest_email` | ✓ | 99 | `read_latest_email` | ✓ | 420 | synth/query |
| 158 | `uh hey, my notes` | `read_notes` | `greet` | ✗ | 1 | `read_notes` | ✓ | 69 | `read_notes` | ✓ | 422 | synth/query |
| 159 | `any chance you could give me a summary of that doc` | `summarize_file` | `summarize_file` | ✓ | 2 | `summarize_file` | ✓ | 91 | `summarize_file` | ✓ | 400 | synth/command |
| 160 | `i'd love to know the contents of documents` | `list_folder_contents` | `llm_chat` | ✗ | 3 | `show_memories` | ✗ | 88 | `list_folder_contents` | ✓ | 439 | synth/query |
| 161 | `cancel culture is real` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 78 | `cancel_calendar_event` | ✗ | 414 | registry/hard_negative |
| 162 | `i need you to set voice mode to wake word` | `set_voice_mode` | `set_voice_mode` | ✓ | 2 | `set_voice_mode` | ✓ | 133 | `enable_voice` | ✗ | 375 | synth/command |
| 163 | `would you mind sharing the forecast for the weekend` | `get_weather` | `get_weather` | ✓ | 2 | `llm_chat` | ✗ | 85 | `get_friday_status` | ✗ | 473 | synth/query |
| 164 | `real quick - my unread emails` | `summarize_inbox` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✓ | 128 | `summarize_inbox` | ✓ | 394 | synth/query |
| 165 | `any chance you could share the charge` | `get_battery` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 88 | `get_battery` | ✓ | 397 | synth/query |
| 166 | `real quick, play the new kendrick album` | `play_youtube_music` | `play_youtube_music` | ✓ | 1 | `play_youtube_music` | ✓ | 106 | `play_youtube_music` | ✓ | 407 | synth/command |
| 167 | `would you end the deep work block` | `end_focus_session` | `llm_chat` | ✗ | 3 | `end_focus_session` | ✓ | 89 | `end_focus_session` | ✓ | 429 | synth/command |
| 168 | `actually, the time` | `get_time` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 77 | `get_time` | ✓ | 358 | synth/query |
| 169 | `what's on your mind today` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 75 | `list_reminders` | ✗ | 382 | chitchat/seed |
| 170 | `let's start dictating` | `start_dictation` | `launch_app` | ✗ | 2 | `start_dictation` | ✓ | 82 | `start_dictation` | ✓ | 404 | synth/command |
| 171 | `would you mind sharing the notes from yesterday` | `read_notes` | `llm_chat` | ✗ | 3 | `read_notes` | ✓ | 69 | `read_notes` | ✓ | 363 | synth/query |
| 172 | `i need you to enable the microphone` | `enable_voice` | `enable_voice` | ✓ | 2 | `enable_voice` | ✓ | 72 | `enable_voice` | ✓ | 380 | synth/command |
| 173 | `how about you play the new kendrick album` | `play_youtube_music` | `play_youtube_music` | ✓ | 1 | `play_youtube_music` | ✓ | 94 | `play_youtube_music` | ✓ | 477 | synth/command |
| 174 | `would you start dictating` | `start_dictation` | `launch_app` | ✗ | 2 | `start_dictation` | ✓ | 87 | `start_dictation` | ✓ | 376 | synth/command |
| 175 | `actually, open my documents folder` | `open_folder` | `open_file` | ✗ | 2 | `open_folder` | ✓ | 73 | `open_folder` | ✓ | 401 | synth/command |
| 176 | `how about you start a pomodoro` | `start_focus_session` | `start_focus_session` | ✓ | 2 | `start_focus_session` | ✓ | 121 | `start_focus_session` | ✓ | 722 | synth/command |
| 177 | `do me a favor and launch spotify` | `launch_app` | `launch_app` | ✓ | 5 | `launch_app` | ✓ | 72 | `launch_app` | ✓ | 438 | synth/command |
| 178 | `would you snap a screenshot` | `take_screenshot` | `take_screenshot` | ✓ | 1 | `take_screenshot` | ✓ | 74 | `take_screenshot` | ✓ | 382 | synth/command |
| 179 | `do me a favor and move my dentist appointment to friday` | `move_calendar_event` | `move_calendar_event` | ✓ | 1 | `move_calendar_event` | ✓ | 95 | `move_calendar_event` | ✓ | 456 | synth/command |
| 180 | `i'd love to know today's date` | `get_date` | `get_date` | ✓ | 1 | `get_date` | ✓ | 76 | `get_date` | ✓ | 391 | synth/query |
| 181 | `open your mind to it` | `llm_chat` | `open_file` | ✗ | 2 | `llm_chat` | ✓ | 74 | `open_browser_url` | ✗ | 396 | registry/hard_negative |
| 182 | `would you mind sharing the clock` | `get_time` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 77 | `get_time` | ✓ | 426 | synth/query |
| 183 | `let's remind me about the deadline tomorrow` | `set_reminder` | `set_reminder` | ✓ | 1 | `set_reminder` | ✓ | 73 | `set_reminder` | ✓ | 391 | synth/command |
| 184 | `face the music` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 78 | `browser_media_control` | ✗ | 448 | registry/hard_negative |
| 185 | `any chance you could share the third file` | `select_file_candidate` | `llm_chat` | ✗ | 3 | `select_file_candidate` | ✓ | 96 | `select_file_candidate` | ✓ | 409 | synth/query |
| 186 | `real quick - the newest email` | `read_latest_email` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✗ | 101 | `read_latest_email` | ✓ | 419 | synth/query |
| 187 | `i need you to play some taylor swift` | `play_youtube_music` | `play_youtube` | ✗ | 1 | `play_youtube_music` | ✓ | 101 | `play_youtube_music` | ✓ | 421 | synth/command |
| 188 | `let's cancel this transcription` | `cancel_dictation` | `llm_chat` | ✗ | 3 | `cancel_dictation` | ✓ | 120 | `cancel_Transcription` | ✗ | 363 | synth/command |
| 189 | `got a sec - the first one` | `select_file_candidate` | `select_file_candidate` | ✓ | 3 | `llm_chat` | ✗ | 80 | `take_screenshot` | ✗ | 426 | synth/query |
| 190 | `real quick, forget the fact about my dog` | `delete_memory` | `llm_chat` | ✗ | 3 | `delete_memory` | ✓ | 77 | `delete_memory` | ✓ | 390 | synth/command |
| 191 | `uh hey, what you remember about me` | `show_memories` | `greet` | ✗ | 1 | `show_memories` | ✓ | 85 | `greet` | ✗ | 363 | synth/query |
| 192 | `actually, cancel this transcription` | `cancel_dictation` | `llm_chat` | ✗ | 3 | `cancel_dictation` | ✓ | 80 | `cancel_Transcription` | ✗ | 386 | synth/command |
| 193 | `would you grab the screen` | `take_screenshot` | `llm_chat` | ✗ | 3 | `take_screenshot` | ✓ | 63 | `take_screenshot` | ✓ | 374 | synth/command |
| 194 | `i'd love to know current time` | `get_time` | `get_time` | ✓ | 1 | `get_time` | ✓ | 75 | `get_time` | ✓ | 425 | synth/query |
| 195 | `let's pause the music` | `browser_media_control` | `llm_chat` | ✗ | 3 | `browser_media_control` | ✓ | 90 | `browser_media_control` | ✓ | 420 | synth/command |
| 196 | `i need you to end the focus session` | `end_focus_session` | `llm_chat` | ✗ | 3 | `end_focus_session` | ✓ | 95 | `end_focus_session` | ✓ | 443 | synth/command |
| 197 | `real quick, schedule a meeting tomorrow at three` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `create_calendar_event` | ✓ | 119 | `create_calendar_event` | ✓ | 431 | synth/command |
| 198 | `real quick, open the anthropic website` | `open_browser_url` | `open_file` | ✗ | 2 | `open_browser_url` | ✓ | 87 | `open_browser_url` | ✓ | 381 | synth/command |
| 199 | `would you play the obama farewell speech` | `play_youtube` | `play_youtube` | ✓ | 1 | `play_youtube_music` | ✗ | 125 | `play_youtube` | ✓ | 408 | synth/command |
| 200 | `would you set an alarm for nine am` | `set_reminder` | `llm_chat` | ✗ | 3 | `set_reminder` | ✓ | 91 | `set_reminder` | ✓ | 390 | synth/command |
| 201 | `real quick - close your ears` | `disable_voice` | `llm_chat` | ✗ | 3 | `disable_voice` | ✓ | 63 | `close_browser_media_control` | ✗ | 447 | synth/query |
| 202 | `would you cancel the dentist appointment` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `cancel_calendar_event` | ✓ | 105 | `cancel_calendar_event` | ✓ | 441 | synth/command |
| 203 | `i'd love to know how much focus time is left` | `focus_session_status` | `focus_session_status` | ✓ | 1 | `focus_session_status` | ✓ | 118 | `focus_session_status` | ✓ | 423 | synth/query |
| 204 | `i'd love to know battery level` | `get_battery` | `get_battery` | ✓ | 1 | `get_battery` | ✓ | 94 | `get_battery` | ✓ | 407 | synth/query |
| 205 | `real quick, play the latest mkbhd review` | `play_youtube` | `play_youtube` | ✓ | 1 | `play_youtube_music` | ✗ | 153 | `play_youtube_music` | ✗ | 389 | synth/command |
| 206 | `i'd love to know the one called report` | `select_file_candidate` | `llm_chat` | ✗ | 3 | `select_file_candidate` | ✓ | 140 | `get_friday_status` | ✗ | 430 | synth/query |
| 207 | `any chance you could share my latest email` | `read_latest_email` | `llm_chat` | ✗ | 3 | `read_latest_email` | ✓ | 168 | `read_latest_email` | ✓ | 408 | synth/query |
| 208 | `real quick - the day of the week` | `get_date` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 173 | `get_weather` | ✗ | 409 | synth/query |
| 209 | `uh hey, don't` | `confirm_no` | `greet` | ✗ | 1 | `confirm_no` | ✓ | 91 | `confirm_no` | ✓ | 365 | synth/query |
| 210 | `inbox zero is a myth` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 121 | `disable_voice` | ✗ | 354 | registry/hard_negative |
| 211 | `real quick, quit friday` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 2 | `shutdown_assistant` | ✓ | 102 | `shutdown_assistant` | ✓ | 386 | synth/command |
| 212 | `real quick - the forecast for the weekend` | `get_weather` | `get_weather` | ✓ | 2 | `llm_chat` | ✗ | 125 | `get_weather` | ✓ | 353 | synth/query |
| 213 | `sure thing no` | `confirm_no` | `llm_chat` | ✗ | 3 | `confirm_no` | ✓ | 112 | `confirm_no` | ✓ | 334 | synth/confirm |
| 214 | `actually, cancel the dictation and discard` | `cancel_dictation` | `cancel_dictation` | ✓ | 1 | `cancel_dictation` | ✓ | 140 | `cancel_dictation` | ✓ | 398 | synth/command |
| 215 | `well howdy` | `greet` | `llm_chat` | ✗ | 6 | `greet` | ✓ | 66 | `greet` | ✓ | 295 | synth/greet |
| 216 | `sure thing sure` | `confirm_yes` | `llm_chat` | ✗ | 2 | `confirm_yes` | ✓ | 137 | `confirm_yes` | ✓ | 315 | synth/confirm |
| 217 | `any chance you could exit friday` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 1 | `shutdown_assistant` | ✓ | 109 | `shutdown_assistant` | ✓ | 344 | synth/command |
| 218 | `she said yes to the proposal` | `llm_chat` | `llm_chat` | ✓ | 2 | `confirm_yes` | ✗ | 101 | `confirm_yes` | ✗ | 365 | registry/hard_negative |
| 219 | `would you mind sharing the date` | `get_date` | `llm_chat` | ✗ | 2 | `llm_chat` | ✗ | 130 | `get_date` | ✓ | 333 | synth/query |
| 220 | `let's cancel the dictation and discard` | `cancel_dictation` | `cancel_dictation` | ✓ | 1 | `cancel_dictation` | ✓ | 135 | `cancel_dictation` | ✓ | 372 | synth/command |
| 221 | `let's skip this track` | `browser_media_control` | `llm_chat` | ✗ | 3 | `browser_media_control` | ✓ | 131 | `browser_media_control` | ✓ | 358 | synth/command |
| 222 | `how about you start a work session` | `start_focus_session` | `launch_app` | ✗ | 2 | `start_focus_session` | ✓ | 155 | `start_focus_session` | ✓ | 790 | synth/command |
| 223 | `in summary the team did well` | `llm_chat` | `llm_chat` | ✓ | 3 | `summarize_inbox` | ✗ | 170 | `get_friday_status` | ✗ | 352 | registry/hard_negative |
| 224 | `any chance you could delete that memory` | `delete_memory` | `delete_memory` | ✓ | 1 | `delete_memory` | ✓ | 160 | `delete_memory` | ✓ | 391 | synth/command |
| 225 | `any wisdom to drop on me` | `llm_chat` | `llm_chat` | ✓ | 3 | `delete_memory` | ✗ | 123 | `set_reminder` | ✗ | 333 | chitchat/seed |
| 226 | `move on already` | `llm_chat` | `llm_chat` | ✓ | 3 | `confirm_no` | ✗ | 109 | `move_calendar_event` | ✗ | 358 | registry/hard_negative |
| 227 | `real quick, start listening` | `enable_voice` | `launch_app` | ✗ | 2 | `llm_chat` | ✗ | 125 | `—` | ✗ | 798 | synth/command |
| 228 | `any chance you could share what you remember about me` | `show_memories` | `llm_chat` | ✗ | 3 | `show_memories` | ✓ | 152 | `show_memories` | ✓ | 383 | synth/query |
| 229 | `do me a favor and cancel my meeting at three` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 2 | `cancel_calendar_event` | ✓ | 158 | `cancel_calendar_event` | ✓ | 448 | synth/command |
| 230 | `i'd love to know my preferences` | `show_memories` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 134 | `show_memories` | ✓ | 375 | synth/query |
| 231 | `i have a long todo list` | `llm_chat` | `llm_chat` | ✓ | 3 | `summarize_inbox` | ✗ | 206 | `list_folder_contents` | ✗ | 371 | registry/hard_negative |
| 232 | `actually, my unread emails` | `summarize_inbox` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✓ | 155 | `summarize_inbox` | ✓ | 355 | synth/query |
| 233 | `got a sec - your status` | `get_friday_status` | `get_friday_status` | ✓ | 1 | `get_time` | ✗ | 117 | `get_friday_status` | ✓ | 368 | synth/query |
| 234 | `actually, find a file called report` | `search_file` | `search_file` | ✓ | 1 | `search_file` | ✓ | 122 | `search_file` | ✓ | 386 | synth/command |
| 235 | `how about you schedule lunch with sara monday` | `create_calendar_event` | `llm_chat` | ✗ | 3 | `create_calendar_event` | ✓ | 143 | `create_calendar_event` | ✓ | 366 | synth/command |
| 236 | `okay nope` | `confirm_no` | `llm_chat` | ✗ | 3 | `confirm_no` | ✓ | 95 | `confirm_no` | ✓ | 335 | synth/confirm |
| 237 | `any chance you could cancel the dentist appointment` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 2 | `cancel_calendar_event` | ✓ | 151 | `cancel_calendar_event` | ✓ | 374 | synth/command |
| 238 | `what a time to be alive` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 187 | `get_time` | ✗ | 323 | registry/hard_negative |
| 239 | `do me a favor and start a work session` | `start_focus_session` | `launch_app` | ✗ | 3 | `start_focus_session` | ✓ | 160 | `start_focus_session` | ✓ | 392 | synth/command |
| 240 | `would you search for the best ramen near me` | `search_google` | `search_file` | ✗ | 3 | `search_file` | ✗ | 128 | `search_google` | ✓ | 342 | synth/command |
| 241 | `do me a favor and start taking dictation` | `start_dictation` | `launch_app` | ✗ | 2 | `start_dictation` | ✓ | 130 | `start_dictation` | ✓ | 359 | synth/command |
| 242 | `any chance you could share what reminders i have` | `list_reminders` | `list_reminders` | ✓ | 2 | `llm_chat` | ✗ | 142 | `list_reminders` | ✓ | 389 | synth/query |
| 243 | `would you mind sharing my notes` | `read_notes` | `read_notes` | ✓ | 2 | `read_notes` | ✓ | 120 | `read_notes` | ✓ | 323 | synth/query |
| 244 | `let's copy the report to desktop` | `manage_file` | `llm_chat` | ✗ | 3 | `manage_file` | ✓ | 122 | `manage_file` | ✓ | 325 | synth/command |
| 245 | `uh hey, the most recent message` | `read_latest_email` | `greet` | ✗ | 1 | `read_latest_email` | ✓ | 192 | `summarize_inbox` | ✗ | 369 | synth/query |
| 246 | `i need you to play that` | `browser_media_control` | `llm_chat` | ✗ | 3 | `play_youtube_music` | ✗ | 151 | `browser_media_control` | ✓ | 375 | synth/command |
| 247 | `any chance you could switch to persistent listening` | `set_voice_mode` | `llm_chat` | ✗ | 3 | `set_voice_mode` | ✓ | 167 | `focus_session_status` | ✗ | 363 | synth/command |
| 248 | `uh hey, my pending alerts` | `list_reminders` | `greet` | ✗ | 5 | `get_reminder` | ✗ | 118 | `list_reminders` | ✓ | 388 | synth/query |
| 249 | `real quick, start a work session` | `start_focus_session` | `launch_app` | ✗ | 2 | `start_focus_session` | ✓ | 142 | `start_focus_session` | ✓ | 375 | synth/command |
| 250 | `any chance you could share your status` | `get_friday_status` | `get_friday_status` | ✓ | 1 | `llm_chat` | ✗ | 144 | `get_friday_status` | ✓ | 379 | synth/query |
| 251 | `how about you switch to manual mode` | `set_voice_mode` | `llm_chat` | ✗ | 3 | `set_voice_mode` | ✓ | 169 | `set_voice_mode` | ✓ | 351 | synth/command |
| 252 | `well hi` | `greet` | `greet` | ✓ | 1 | `greet` | ✓ | 96 | `greet` | ✓ | 294 | synth/greet |
| 253 | `i'm searching for meaning` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 118 | `search_google` | ✗ | 330 | registry/hard_negative |
| 254 | `enabler is a strong word` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 127 | `enable_voice` | ✗ | 327 | registry/hard_negative |
| 255 | `would you mind sharing my inbox` | `summarize_inbox` | `llm_chat` | ✗ | 3 | `summarize_inbox` | ✓ | 160 | `summarize_inbox` | ✓ | 384 | synth/query |
| 256 | `uh hey, what's on my calendar` | `list_calendar_events` | `list_calendar_events` | ✓ | 1 | `list_calendar_events` | ✓ | 158 | `list_calendar_events` | ✓ | 387 | synth/query |
| 257 | `the factory is shutting down next year` | `llm_chat` | `llm_chat` | ✓ | 3 | `shutdown_assistant` | ✗ | 118 | `shutdown_assistant` | ✗ | 316 | registry/hard_negative |
| 258 | `how about you go ahead` | `confirm_yes` | `llm_chat` | ✗ | 3 | `confirm_yes` | ✓ | 114 | `confirm_yes` | ✓ | 320 | synth/command |
| 259 | `do me a favor and remind me about the deadline tomorrow` | `set_reminder` | `set_reminder` | ✓ | 1 | `llm_chat` | ✗ | 211 | `set_reminder` | ✓ | 365 | synth/command |
| 260 | `search me i don't know` | `llm_chat` | `search_file` | ✗ | 2 | `llm_chat` | ✓ | 122 | `search_google` | ✗ | 330 | registry/hard_negative |
| 261 | `any chance you could open my email tab` | `open_browser_url` | `launch_app` | ✗ | 2 | `open_browser_url` | ✓ | 144 | `open_browser_url` | ✓ | 372 | synth/command |
| 262 | `real quick - current time` | `get_time` | `get_time` | ✓ | 1 | `llm_chat` | ✗ | 118 | `get_time` | ✓ | 373 | synth/query |
| 263 | `do me a favor and turn the volume down` | `set_volume` | `set_volume` | ✓ | 1 | `set_volume` | ✓ | 129 | `set_volume` | ✓ | 334 | synth/command |
| 264 | `actually, schedule a meeting tomorrow at three` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `create_calendar_event` | ✓ | 158 | `create_calendar_event` | ✓ | 358 | synth/command |
| 265 | `would you mind sharing your status` | `get_friday_status` | `get_friday_status` | ✓ | 1 | `llm_chat` | ✗ | 138 | `get_friday_status` | ✓ | 405 | synth/query |
| 266 | `let's look for the budget spreadsheet` | `search_file` | `llm_chat` | ✗ | 3 | `search_file` | ✓ | 204 | `search_file` | ✓ | 327 | synth/command |
| 267 | `any chance you could share my notes` | `read_notes` | `read_notes` | ✓ | 2 | `read_notes` | ✓ | 103 | `read_notes` | ✓ | 328 | synth/query |
| 268 | `mind telling me the contents of documents` | `list_folder_contents` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 148 | `list_folder_contents` | ✓ | 397 | synth/query |
| 269 | `i need you to take a screenshot` | `take_screenshot` | `take_screenshot` | ✓ | 1 | `take_screenshot` | ✓ | 141 | `take_screenshot` | ✓ | 314 | synth/command |
| 270 | `no man is an island` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 125 | `browser_media_control` | ✗ | 378 | registry/hard_negative |
| 271 | `how about you search for the best ramen near me` | `search_google` | `search_file` | ✗ | 2 | `search_file` | ✗ | 125 | `search_google` | ✓ | 347 | synth/command |
| 272 | `would you open hacker news` | `open_browser_url` | `launch_app` | ✗ | 2 | `open_browser_url` | ✓ | 158 | `open_browser_url` | ✓ | 356 | synth/command |
| 273 | `real quick, google how to fix a leaky faucet` | `search_google` | `search_google` | ✓ | 1 | `llm_chat` | ✗ | 194 | `search_google` | ✓ | 382 | synth/command |
| 274 | `next time will be better` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 121 | `set_reminder` | ✗ | 321 | registry/hard_negative |
| 275 | `do me a favor and play that funny cat video` | `play_youtube` | `llm_chat` | ✗ | 3 | `play_youtube_music` | ✗ | 150 | `play_youtube` | ✓ | 338 | synth/command |
| 276 | `uh hey, my pomodoro timer` | `focus_session_status` | `greet` | ✗ | 1 | `focus_session_status` | ✓ | 143 | `focus_session_status` | ✓ | 391 | synth/query |
| 277 | `how about you set volume to max` | `set_volume` | `set_volume` | ✓ | 2 | `set_volume` | ✓ | 111 | `set_volume` | ✓ | 319 | synth/command |
| 278 | `actually, read what's in this file` | `read_file` | `read_file` | ✓ | 2 | `read_file` | ✓ | 112 | `read_file` | ✓ | 341 | synth/command |
| 279 | `got a sec - cpu usage` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 1 | `get_cpu_ram` | ✓ | 146 | `get_cpu_ram` | ✓ | 375 | synth/query |
| 280 | `how about you open the resume pdf` | `open_file` | `open_file` | ✓ | 2 | `open_file` | ✓ | 123 | `open_file` | ✓ | 344 | synth/command |
| 281 | `would you mind sharing what's on my desktop` | `list_folder_contents` | `llm_chat` | ✗ | 3 | `show_memories` | ✗ | 145 | `list_folder_contents` | ✓ | 370 | synth/query |
| 282 | `let's mute the tab` | `browser_media_control` | `set_volume` | ✗ | 1 | `browser_media_control` | ✓ | 144 | `browser_media_control` | ✓ | 419 | synth/command |
| 283 | `i need you to make a quick note about the demo` | `save_note` | `save_note` | ✓ | 1 | `save_note` | ✓ | 118 | `create_calendar_event` | ✗ | 368 | synth/command |
| 284 | `real quick - the charge` | `get_battery` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 123 | `get_battery` | ✓ | 327 | synth/query |
| 285 | `real quick - my schedule today` | `list_calendar_events` | `llm_chat` | ✗ | 6 | `llm_chat` | ✗ | 114 | `focus_session_status` | ✗ | 384 | synth/query |
| 286 | `let's stop taking dictation` | `end_dictation` | `llm_chat` | ✗ | 3 | `end_dictation` | ✓ | 137 | `end_dictation` | ✓ | 351 | synth/command |
| 287 | `the trade volume tripled` | `llm_chat` | `set_volume` | ✗ | 1 | `llm_chat` | ✓ | 125 | `set_volume` | ✗ | 310 | registry/hard_negative |
| 288 | `got a sec - what reminders i have` | `list_reminders` | `list_reminders` | ✓ | 2 | `set_reminder` | ✗ | 153 | `list_reminders` | ✓ | 346 | synth/query |
| 289 | `oh, yo` | `greet` | `llm_chat` | ✗ | 2 | `greet` | ✓ | 70 | `confirm_yes` | ✗ | 351 | synth/greet |
| 290 | `let's read the contents of notes.txt` | `read_file` | `llm_chat` | ✗ | 3 | `read_file` | ✓ | 117 | `read_file` | ✓ | 394 | synth/command |
| 291 | `musical notes are fun` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 115 | `set_reminder` | ✗ | 333 | registry/hard_negative |
| 292 | `i'd love to know what's on my calendar` | `list_calendar_events` | `list_calendar_events` | ✓ | 1 | `list_calendar_events` | ✓ | 156 | `list_calendar_events` | ✓ | 376 | synth/query |
| 293 | `real quick - how much focus time is left` | `focus_session_status` | `focus_session_status` | ✓ | 1 | `focus_session_status` | ✓ | 154 | `focus_session_status` | ✓ | 443 | synth/query |
| 294 | `any chance you could remind me about the deadline tomorrow` | `set_reminder` | `set_reminder` | ✓ | 1 | `set_reminder` | ✓ | 117 | `set_reminder` | ✓ | 337 | synth/command |
| 295 | `actually, end the work session` | `end_focus_session` | `llm_chat` | ✗ | 3 | `end_focus_session` | ✓ | 156 | `end_focus_session` | ✓ | 383 | synth/command |
| 296 | `actually, your status` | `get_friday_status` | `get_friday_status` | ✓ | 1 | `llm_chat` | ✗ | 163 | `get_friday_status` | ✓ | 345 | synth/query |
| 297 | `mind telling me processor load` | `get_cpu_ram` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 133 | `get_cpu_ram` | ✓ | 351 | synth/query |
| 298 | `actually, will it rain tomorrow` | `get_weather` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 117 | `get_weather` | ✓ | 337 | synth/query |
| 299 | `would you search for my resume` | `search_file` | `search_file` | ✓ | 3 | `search_file` | ✓ | 107 | `search_file` | ✓ | 346 | synth/command |
| 300 | `how about you open my notes file` | `open_file` | `open_file` | ✓ | 2 | `open_file` | ✓ | 101 | `open_file` | ✓ | 330 | synth/command |
| 301 | `real quick, save a note saying call the plumber` | `save_note` | `save_note` | ✓ | 2 | `save_note` | ✓ | 118 | `save_note` | ✓ | 351 | synth/command |
| 302 | `got a sec - the date` | `get_date` | `llm_chat` | ✗ | 3 | `get_date` | ✓ | 109 | `get_date` | ✓ | 335 | synth/query |
| 303 | `actually, the date` | `get_date` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 125 | `get_date` | ✓ | 325 | synth/query |
| 304 | `i need you to push that call to next week` | `move_calendar_event` | `llm_chat` | ✗ | 3 | `move_calendar_event` | ✓ | 228 | `move_calendar_event` | ✓ | 383 | synth/command |
| 305 | `would you start dictation` | `start_dictation` | `start_dictation` | ✓ | 2 | `start_dictation` | ✓ | 126 | `start_dictation` | ✓ | 375 | synth/command |
| 306 | `make some good memories this trip` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 128 | `set_reminder` | ✗ | 326 | registry/hard_negative |
| 307 | `let's read what's in this file` | `read_file` | `read_file` | ✓ | 2 | `read_file` | ✓ | 111 | `read_file` | ✓ | 375 | synth/command |
| 308 | `would you drop what i was dictating` | `cancel_dictation` | `llm_chat` | ✗ | 3 | `cancel_dictation` | ✓ | 120 | `end_dictation` | ✗ | 348 | synth/command |
| 309 | `do me a favor and jot down this idea` | `save_note` | `save_note` | ✓ | 2 | `save_note` | ✓ | 116 | `set_reminder` | ✗ | 335 | synth/command |
| 310 | `real quick, open my notes file` | `open_file` | `open_file` | ✓ | 1 | `open_file` | ✓ | 122 | `open_file` | ✓ | 445 | synth/command |
| 311 | `let's disable the microphone` | `disable_voice` | `disable_voice` | ✓ | 2 | `disable_voice` | ✓ | 169 | `disable_voice` | ✓ | 312 | synth/command |
| 312 | `how about you skip this track` | `browser_media_control` | `llm_chat` | ✗ | 3 | `browser_media_control` | ✓ | 138 | `browser_media_control` | ✓ | 388 | synth/command |
| 313 | `mind telling me how much focus time is left` | `focus_session_status` | `focus_session_status` | ✓ | 1 | `focus_session_status` | ✓ | 166 | `focus_session_status` | ✓ | 384 | synth/query |
| 314 | `real quick, drop that preference` | `delete_memory` | `llm_chat` | ✗ | 3 | `delete_memory` | ✓ | 103 | `delete_memory` | ✓ | 321 | synth/command |
| 315 | `would you open that folder` | `open_folder` | `open_file` | ✗ | 2 | `open_folder` | ✓ | 103 | `open_folder` | ✓ | 355 | synth/command |
| 316 | `first come first served` | `llm_chat` | `search_file` | ✗ | 2 | `llm_chat` | ✓ | 107 | `launch_app` | ✗ | 319 | registry/hard_negative |
| 317 | `i need you to stop dictation` | `end_dictation` | `end_dictation` | ✓ | 1 | `end_dictation` | ✓ | 133 | `end_dictation` | ✓ | 372 | synth/command |
| 318 | `any chance you could share my reminders` | `list_reminders` | `list_reminders` | ✓ | 2 | `share_reminders` | ✗ | 130 | `list_reminders` | ✓ | 374 | synth/query |
| 319 | `actually, ram usage` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 1 | `llm_chat` | ✗ | 199 | `get_cpu_ram` | ✓ | 360 | synth/query |
| 320 | `actually, find files named invoice` | `search_file` | `search_file` | ✓ | 2 | `search_file` | ✓ | 88 | `search_file` | ✓ | 327 | synth/command |
| 321 | `make me laugh real quick` | `llm_chat` | `search_file` | ✗ | 2 | `llm_chat` | ✓ | 119 | `set_voice_mode` | ✗ | 428 | chitchat/seed |
| 322 | `the folder chair broke` | `llm_chat` | `llm_chat` | ✓ | 6 | `llm_chat` | ✓ | 122 | `browser_media_control` | ✗ | 338 | registry/hard_negative |
| 323 | `she saved me a lot of trouble` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 130 | `manage_file` | ✗ | 334 | registry/hard_negative |
| 324 | `oh, hello` | `greet` | `greet` | ✓ | 1 | `greet` | ✓ | 70 | `greet` | ✓ | 285 | synth/greet |
| 325 | `let's start dictation` | `start_dictation` | `start_dictation` | ✓ | 2 | `start_dictation` | ✓ | 123 | `start_dictation` | ✓ | 367 | synth/command |
| 326 | `she's been disabled by the injury` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 147 | `disable_voice` | ✗ | 341 | registry/hard_negative |
| 327 | `real quick - don't` | `confirm_no` | `llm_chat` | ✗ | 3 | `llm_chat` | ✗ | 193 | `confirm_no` | ✓ | 344 | synth/query |
| 328 | `in any weather i'll be there` | `llm_chat` | `llm_chat` | ✓ | 3 | `llm_chat` | ✓ | 123 | `enable_voice` | ✗ | 331 | registry/hard_negative |
