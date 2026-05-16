# Intent-routing benchmark — 2026-05-16 02:19 UTC

**Cases:** 240

**Models compared:** current, gemma, fn-gemma, qwen-1.7b, qwen-4b


## Headline metrics

| Model | Accuracy | Macro P | Macro R | Macro F1 | Micro F1 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| current | 82.9% | 0.840 | 0.800 | 0.806 | 0.829 | 2 | 13 |
| gemma | 6.2% | 0.160 | 0.073 | 0.079 | 0.065 | 437 | 1345 |
| fn-gemma | 0.0% | 0.000 | 0.000 | 0.000 | 0.000 | 382 | 1910 |
| qwen-1.7b | 0.0% | 0.000 | 0.000 | 0.000 | 0.000 | 3942 | 5749 |
| qwen-4b | 0.0% | 0.000 | 0.000 | 0.000 | 0.000 | 7810 | 9386 |

## Per-category accuracy

| Category | N | current ✓ | gemma ✓ | fn-gemma ✓ | qwen-1.7b ✓ | qwen-4b ✓ | current p50 | gemma p50 | fn-gemma p50 | qwen-1.7b p50 | qwen-4b p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| battery | 9 | 8/9 | 3/9 | 0/9 | 0/9 | 0/9 | 3ms | 437ms | 578ms | 3928ms | 7693ms |
| calendar | 23 | 19/23 | 0/23 | 0/23 | 0/23 | 0/23 | 2ms | 408ms | 395ms | 4086ms | 7757ms |
| chat | 12 | 12/12 | 0/12 | 0/12 | 0/12 | 0/12 | 12ms | 695ms | 413ms | 4304ms | 8009ms |
| confirm | 9 | 8/9 | 0/9 | 0/9 | 0/9 | 0/9 | 3ms | 432ms | 140ms | 3611ms | 7529ms |
| date | 9 | 8/9 | 0/9 | 0/9 | 0/9 | 0/9 | 3ms | 403ms | 752ms | 4063ms | 8105ms |
| dictation | 8 | 8/8 | 1/8 | 0/8 | 0/8 | 0/8 | 1ms | 488ms | 143ms | 3457ms | 7853ms |
| email | 6 | 6/6 | 0/6 | 0/6 | 0/6 | 0/6 | 5ms | 538ms | 404ms | 4252ms | 7960ms |
| files | 20 | 14/20 | 1/20 | 0/20 | 0/20 | 0/20 | 3ms | 371ms | 201ms | 3988ms | 7899ms |
| focus | 10 | 8/10 | 0/10 | 0/10 | 0/10 | 0/10 | 2ms | 480ms | 311ms | 3597ms | 7661ms |
| greet | 5 | 5/5 | 0/5 | 0/5 | 0/5 | 0/5 | 1ms | 422ms | 442ms | 3918ms | 7383ms |
| help | 9 | 3/9 | 0/9 | 0/9 | 0/9 | 0/9 | 13ms | 530ms | 161ms | 3729ms | 7601ms |
| launch | 8 | 8/8 | 0/8 | 0/8 | 0/8 | 0/8 | 3ms | 448ms | 258ms | 3682ms | 8000ms |
| media | 16 | 9/16 | 2/16 | 0/16 | 0/16 | 0/16 | 2ms | 432ms | 168ms | 4194ms | 7998ms |
| memory | 7 | 7/7 | 0/7 | 0/7 | 0/7 | 0/7 | 1ms | 446ms | 737ms | 3542ms | 7706ms |
| notes | 11 | 10/11 | 1/11 | 0/11 | 0/11 | 0/11 | 2ms | 417ms | 667ms | 4478ms | 7900ms |
| reminders | 13 | 11/13 | 0/13 | 0/13 | 0/13 | 0/13 | 2ms | 435ms | 568ms | 4038ms | 7764ms |
| screenshot | 7 | 6/7 | 0/7 | 0/7 | 0/7 | 0/7 | 2ms | 502ms | 262ms | 4069ms | 8515ms |
| status | 6 | 4/6 | 0/6 | 0/6 | 0/6 | 0/6 | 2ms | 493ms | 440ms | 3803ms | 8416ms |
| system | 11 | 10/11 | 5/11 | 0/11 | 0/11 | 0/11 | 11ms | 438ms | 269ms | 3983ms | 8139ms |
| time | 10 | 9/10 | 2/10 | 0/10 | 0/10 | 0/10 | 6ms | 458ms | 719ms | 3723ms | 7687ms |
| voice | 14 | 11/14 | 0/14 | 0/14 | 0/14 | 0/14 | 2ms | 407ms | 225ms | 4076ms | 7500ms |
| volume | 8 | 7/8 | 0/8 | 0/8 | 0/8 | 0/8 | 3ms | 462ms | 150ms | 3826ms | 7545ms |
| weather | 9 | 8/9 | 0/9 | 0/9 | 0/9 | 0/9 | 3ms | 433ms | 619ms | 4080ms | 8321ms |

## Per-tool metrics — `current`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 25 | 24 | 28 | 1 | 187 | 0.462 | 0.960 | 0.623 |
| `get_weather` | 9 | 8 | 0 | 1 | 231 | 1.000 | 0.889 | 0.941 |
| `create_calendar_event` | 8 | 6 | 0 | 2 | 232 | 1.000 | 0.750 | 0.857 |
| `get_time` | 8 | 7 | 0 | 1 | 232 | 1.000 | 0.875 | 0.933 |
| `save_note` | 8 | 7 | 0 | 1 | 232 | 1.000 | 0.875 | 0.933 |
| `set_reminder` | 8 | 6 | 0 | 2 | 232 | 1.000 | 0.750 | 0.857 |
| `get_battery` | 7 | 6 | 0 | 1 | 233 | 1.000 | 0.857 | 0.923 |
| `get_date` | 7 | 6 | 0 | 1 | 233 | 1.000 | 0.857 | 0.923 |
| `launch_app` | 7 | 7 | 1 | 0 | 232 | 0.875 | 1.000 | 0.933 |
| `set_volume` | 7 | 6 | 1 | 1 | 232 | 0.857 | 0.857 | 0.857 |
| `get_friday_status` | 6 | 4 | 0 | 2 | 234 | 1.000 | 0.667 | 0.800 |
| `list_calendar_events` | 6 | 5 | 0 | 1 | 234 | 1.000 | 0.833 | 0.909 |
| `manage_file` | 6 | 6 | 0 | 0 | 234 | 1.000 | 1.000 | 1.000 |
| `set_voice_mode` | 6 | 4 | 0 | 2 | 234 | 1.000 | 0.667 | 0.800 |
| `take_screenshot` | 6 | 6 | 1 | 0 | 233 | 0.857 | 1.000 | 0.923 |
| `cancel_calendar_event` | 5 | 5 | 0 | 0 | 235 | 1.000 | 1.000 | 1.000 |
| `get_cpu_ram` | 5 | 5 | 0 | 0 | 235 | 1.000 | 1.000 | 1.000 |
| `greet` | 5 | 5 | 0 | 0 | 235 | 1.000 | 1.000 | 1.000 |
| `list_reminders` | 5 | 5 | 2 | 0 | 233 | 0.714 | 1.000 | 0.833 |
| `show_capabilities` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `browser_media_control` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `disable_voice` | 4 | 3 | 1 | 1 | 235 | 0.750 | 0.750 | 0.750 |
| `enable_voice` | 4 | 4 | 0 | 0 | 236 | 1.000 | 1.000 | 1.000 |
| `get_system_status` | 4 | 3 | 0 | 1 | 236 | 1.000 | 0.750 | 0.857 |
| `move_calendar_event` | 4 | 3 | 0 | 1 | 236 | 1.000 | 0.750 | 0.857 |
| `read_notes` | 4 | 4 | 0 | 0 | 236 | 1.000 | 1.000 | 1.000 |
| `show_memories` | 4 | 4 | 0 | 0 | 236 | 1.000 | 1.000 | 1.000 |
| `start_focus_session` | 4 | 3 | 1 | 1 | 235 | 0.750 | 0.750 | 0.750 |
| `confirm_no` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `confirm_yes` | 3 | 2 | 0 | 1 | 237 | 1.000 | 0.667 | 0.800 |
| `delete_memory` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `end_dictation` | 3 | 3 | 1 | 0 | 236 | 0.750 | 1.000 | 0.857 |
| `end_focus_session` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `focus_session_status` | 3 | 2 | 0 | 1 | 237 | 1.000 | 0.667 | 0.800 |
| `list_folder_contents` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `play_youtube` | 3 | 2 | 0 | 1 | 237 | 1.000 | 0.667 | 0.800 |
| `read_latest_email` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `search_file` | 3 | 3 | 2 | 0 | 235 | 0.600 | 1.000 | 0.750 |
| `search_google` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `select_file_candidate` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `shutdown_assistant` | 3 | 2 | 0 | 1 | 237 | 1.000 | 0.667 | 0.800 |
| `start_dictation` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `summarize_inbox` | 3 | 3 | 0 | 0 | 237 | 1.000 | 1.000 | 1.000 |
| `cancel_dictation` | 2 | 2 | 0 | 0 | 238 | 1.000 | 1.000 | 1.000 |
| `open_browser_url` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_file` | 2 | 2 | 3 | 0 | 235 | 0.400 | 1.000 | 0.571 |
| `open_folder` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `play_youtube_music` | 2 | 2 | 0 | 0 | 238 | 1.000 | 1.000 | 1.000 |
| `read_file` | 2 | 1 | 0 | 1 | 238 | 1.000 | 0.500 | 0.667 |
| `summarize_file` | 2 | 2 | 0 | 0 | 238 | 1.000 | 1.000 | 1.000 |

## Per-tool metrics — `gemma`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 25 | 0 | 0 | 25 | 215 | 0.000 | 0.000 | 0.000 |
| `get_weather` | 9 | 0 | 0 | 9 | 231 | 0.000 | 0.000 | 0.000 |
| `create_calendar_event` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_time` | 8 | 2 | 0 | 6 | 232 | 1.000 | 0.250 | 0.400 |
| `save_note` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `set_reminder` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_battery` | 7 | 3 | 0 | 4 | 233 | 1.000 | 0.429 | 0.600 |
| `get_date` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `launch_app` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `set_volume` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_friday_status` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `list_calendar_events` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `manage_file` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `set_voice_mode` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `take_screenshot` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `cancel_calendar_event` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `get_cpu_ram` | 5 | 1 | 0 | 4 | 235 | 1.000 | 0.200 | 0.333 |
| `greet` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `list_reminders` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `show_capabilities` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `browser_media_control` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `disable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `enable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `get_system_status` | 4 | 4 | 206 | 0 | 30 | 0.019 | 1.000 | 0.037 |
| `move_calendar_event` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `read_notes` | 4 | 1 | 0 | 3 | 236 | 1.000 | 0.250 | 0.400 |
| `show_memories` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `start_focus_session` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `confirm_no` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `confirm_yes` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `delete_memory` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_focus_session` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `focus_session_status` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `list_folder_contents` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `play_youtube` | 3 | 1 | 0 | 2 | 237 | 1.000 | 0.333 | 0.500 |
| `read_latest_email` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_file` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_google` | 3 | 1 | 0 | 2 | 237 | 1.000 | 0.333 | 0.500 |
| `select_file_candidate` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `shutdown_assistant` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `start_dictation` | 3 | 1 | 0 | 2 | 237 | 1.000 | 0.333 | 0.500 |
| `summarize_inbox` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `cancel_dictation` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_browser_url` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_folder` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `play_youtube_music` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `read_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `summarize_file` | 2 | 1 | 0 | 1 | 238 | 1.000 | 0.500 | 0.667 |

## Per-tool metrics — `fn-gemma`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 25 | 0 | 0 | 25 | 215 | 0.000 | 0.000 | 0.000 |
| `get_weather` | 9 | 0 | 0 | 9 | 231 | 0.000 | 0.000 | 0.000 |
| `create_calendar_event` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_time` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `save_note` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `set_reminder` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_battery` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_date` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `launch_app` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `set_volume` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_friday_status` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `list_calendar_events` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `manage_file` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `set_voice_mode` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `take_screenshot` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `cancel_calendar_event` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `get_cpu_ram` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `greet` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `list_reminders` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `show_capabilities` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `browser_media_control` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `disable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `enable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `get_system_status` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `move_calendar_event` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `read_notes` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `show_memories` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `start_focus_session` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `confirm_no` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `confirm_yes` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `delete_memory` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_focus_session` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `focus_session_status` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `list_folder_contents` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `play_youtube` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `read_latest_email` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_file` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_google` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `select_file_candidate` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `shutdown_assistant` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `start_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `summarize_inbox` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `cancel_dictation` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_browser_url` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_folder` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `play_youtube_music` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `read_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `summarize_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |

## Per-tool metrics — `qwen-1.7b`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 25 | 0 | 0 | 25 | 215 | 0.000 | 0.000 | 0.000 |
| `get_weather` | 9 | 0 | 0 | 9 | 231 | 0.000 | 0.000 | 0.000 |
| `create_calendar_event` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_time` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `save_note` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `set_reminder` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_battery` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_date` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `launch_app` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `set_volume` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_friday_status` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `list_calendar_events` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `manage_file` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `set_voice_mode` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `take_screenshot` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `cancel_calendar_event` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `get_cpu_ram` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `greet` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `list_reminders` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `show_capabilities` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `browser_media_control` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `disable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `enable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `get_system_status` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `move_calendar_event` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `read_notes` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `show_memories` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `start_focus_session` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `confirm_no` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `confirm_yes` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `delete_memory` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_focus_session` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `focus_session_status` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `list_folder_contents` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `play_youtube` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `read_latest_email` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_file` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_google` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `select_file_candidate` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `shutdown_assistant` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `start_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `summarize_inbox` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `cancel_dictation` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_browser_url` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_folder` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `play_youtube_music` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `read_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `summarize_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |

## Per-tool metrics — `qwen-4b`

| Tool | Support | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `llm_chat` | 25 | 0 | 0 | 25 | 215 | 0.000 | 0.000 | 0.000 |
| `get_weather` | 9 | 0 | 0 | 9 | 231 | 0.000 | 0.000 | 0.000 |
| `create_calendar_event` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_time` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `save_note` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `set_reminder` | 8 | 0 | 0 | 8 | 232 | 0.000 | 0.000 | 0.000 |
| `get_battery` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_date` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `launch_app` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `set_volume` | 7 | 0 | 0 | 7 | 233 | 0.000 | 0.000 | 0.000 |
| `get_friday_status` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `list_calendar_events` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `manage_file` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `set_voice_mode` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `take_screenshot` | 6 | 0 | 0 | 6 | 234 | 0.000 | 0.000 | 0.000 |
| `cancel_calendar_event` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `get_cpu_ram` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `greet` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `list_reminders` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `show_capabilities` | 5 | 0 | 0 | 5 | 235 | 0.000 | 0.000 | 0.000 |
| `browser_media_control` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `disable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `enable_voice` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `get_system_status` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `move_calendar_event` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `read_notes` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `show_memories` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `start_focus_session` | 4 | 0 | 0 | 4 | 236 | 0.000 | 0.000 | 0.000 |
| `confirm_no` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `confirm_yes` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `delete_memory` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `end_focus_session` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `focus_session_status` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `list_folder_contents` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `play_youtube` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `read_latest_email` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_file` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `search_google` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `select_file_candidate` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `shutdown_assistant` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `start_dictation` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `summarize_inbox` | 3 | 0 | 0 | 3 | 237 | 0.000 | 0.000 | 0.000 |
| `cancel_dictation` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_browser_url` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `open_folder` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `play_youtube_music` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `read_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |
| `summarize_file` | 2 | 0 | 0 | 2 | 238 | 0.000 | 0.000 | 0.000 |

## Per-case detail

| # | Utterance | Expected | current | current ✓ | current ms | gemma | gemma ✓ | gemma ms | fn-gemma | fn-gemma ✓ | fn-gemma ms | qwen-1.7b | qwen-1.7b ✓ | qwen-1.7b ms | qwen-4b | qwen-4b ✓ | qwen-4b ms | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `what time is it` | `get_time` | `get_time` | ✓ | 9 | `get_system_status` | ✗ | 4985 | `—` | ✗ | 4218 | `—` | ✗ | 21636 | `—` | ✗ | 41379 |  |
| 2 | `tell me the time` | `get_time` | `get_time` | ✓ | 1 | `get_system_status` | ✗ | 445 | `—` | ✗ | 820 | `—` | ✗ | 3537 | `—` | ✗ | 7482 |  |
| 3 | `what's the time` | `get_time` | `get_time` | ✓ | 1 | `get_system_status` | ✗ | 1401 | `—` | ✗ | 2005 | `—` | ✗ | 4209 | `—` | ✗ | 10187 |  |
| 4 | `current time please` | `get_time` | `get_time` | ✓ | 1 | `get_system_status` | ✗ | 390 | `—` | ✗ | 617 | `—` | ✗ | 3731 | `—` | ✗ | 17033 |  |
| 5 | `do you know what time it is` | `get_time` | `get_time` | ✓ | 2 | `get_system_status` | ✗ | 471 | `—` | ✗ | 530 | `—` | ✗ | 4223 | `—` | ✗ | 7682 |  |
| 6 | `got the time` | `get_time` | `llm_chat` | ✗ | 10120 | `get_time` | ✓ | 878 | `—` | ✗ | 1016 | `—` | ✗ | 3554 | `—` | ✗ | 7542 |  |
| 7 | `give me the time` | `get_time` | `get_time` | ✓ | 17 | `get_time` | ✓ | 361 | `—` | ✗ | 490 | `—` | ✗ | 3397 | `—` | ✗ | 7683 |  |
| 8 | `Friday what time is it` | `get_time` | `get_time` | ✓ | 2 | `get_system_status` | ✗ | 802 | `—` | ✗ | 177 | `—` | ✗ | 3397 | `—` | ✗ | 8374 |  |
| 9 | `set my time zone to UTC` | `llm_chat` | `llm_chat` | ✓ | 10 | `get_system_status` | ✗ | 395 | `—` | ✗ | 393 | `—` | ✗ | 3715 | `—` | ✗ | 7692 | Negative — bare 'time' |
| 10 | `time to leave for dinner` | `llm_chat` | `llm_chat` | ✓ | 13 | `get_system_status` | ✗ | 359 | `—` | ✗ | 2015 | `—` | ✗ | 3808 | `—` | ✗ | 7551 | Negative — figurative |
| 11 | `what's today's date` | `get_date` | `get_date` | ✓ | 3 | `get_system_status` | ✗ | 352 | `—` | ✗ | 3438 | `—` | ✗ | 5136 | `—` | ✗ | 8507 |  |
| 12 | `today's date please` | `get_date` | `get_date` | ✓ | 2 | `get_system_status` | ✗ | 442 | `—` | ✗ | 167 | `—` | ✗ | 4216 | `—` | ✗ | 7520 |  |
| 13 | `what is the date today` | `get_date` | `get_date` | ✓ | 3 | `get_system_status` | ✗ | 338 | `—` | ✗ | 752 | `—` | ✗ | 3632 | `—` | ✗ | 7592 |  |
| 14 | `tell me today's date` | `get_date` | `get_date` | ✓ | 3 | `today` | ✗ | 309 | `—` | ✗ | 1547 | `—` | ✗ | 3934 | `—` | ✗ | 8130 |  |
| 15 | `what day is it` | `get_date` | `get_date` | ✓ | 2 | `get_system_status` | ✗ | 430 | `—` | ✗ | 504 | `—` | ✗ | 6345 | `—` | ✗ | 8341 |  |
| 16 | `current date` | `get_date` | `get_date` | ✓ | 2 | `get_system_status` | ✗ | 373 | `—` | ✗ | 1490 | `—` | ✗ | 3568 | `—` | ✗ | 8294 |  |
| 17 | `what day of the week is it` | `get_date` | `llm_chat` | ✗ | 10 | `get_system_status` | ✗ | 479 | `—` | ✗ | 1340 | `—` | ✗ | 4063 | `—` | ✗ | 7976 |  |
| 18 | `I have a date tonight` | `llm_chat` | `llm_chat` | ✓ | 12 | `get_system_status` | ✗ | 465 | `—` | ✗ | 418 | `—` | ✗ | 3903 | `—` | ✗ | 8105 | Negative — homonym |
| 19 | `the deadline is the 15th` | `llm_chat` | `llm_chat` | ✓ | 22 | `get_system_status` | ✗ | 403 | `—` | ✗ | 169 | `—` | ✗ | 4150 | `—` | ✗ | 7970 | Negative — date as noun |
| 20 | `battery status` | `get_battery` | `get_battery` | ✓ | 2 | `get_system_status` | ✗ | 321 | `—` | ✗ | 578 | `—` | ✗ | 3928 | `—` | ✗ | 7369 |  |
| 21 | `how's my battery` | `get_battery` | `get_battery` | ✓ | 2 | `get_system_status` | ✗ | 1770 | `—` | ✗ | 255 | `—` | ✗ | 3824 | `—` | ✗ | 7693 |  |
| 22 | `what's my battery percentage` | `get_battery` | `get_battery` | ✓ | 2 | `get_system_status` | ✗ | 431 | `—` | ✗ | 654 | `—` | ✗ | 5233 | `—` | ✗ | 7549 |  |
| 23 | `is my laptop charging` | `get_battery` | `llm_chat` | ✗ | 13 | `get_system_status` | ✗ | 1125 | `—` | ✗ | 703 | `—` | ✗ | 3969 | `—` | ✗ | 7280 |  |
| 24 | `how much battery do I have left` | `get_battery` | `get_battery` | ✓ | 3 | `get_battery` | ✓ | 512 | `—` | ✗ | 675 | `—` | ✗ | 3734 | `—` | ✗ | 8555 |  |
| 25 | `battery level please` | `get_battery` | `get_battery` | ✓ | 2 | `get_battery` | ✓ | 354 | `—` | ✗ | 948 | `—` | ✗ | 3593 | `—` | ✗ | 12061 |  |
| 26 | `show me the battery` | `get_battery` | `get_battery` | ✓ | 10 | `get_battery` | ✓ | 294 | `—` | ✗ | 146 | `—` | ✗ | 3676 | `—` | ✗ | 8472 |  |
| 27 | `the battery in my car died` | `llm_chat` | `llm_chat` | ✓ | 13 | `get_system_status` | ✗ | 437 | `—` | ✗ | 558 | `—` | ✗ | 4180 | `—` | ✗ | 7595 | Negative — figurative |
| 28 | `I bought a new battery yesterday` | `llm_chat` | `llm_chat` | ✓ | 14 | `get_system_status` | ✗ | 707 | `—` | ✗ | 197 | `—` | ✗ | 4247 | `—` | ✗ | 7741 | Negative — narrative |
| 29 | `cpu usage` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 2 | `get_system_status` | ✗ | 363 | `—` | ✗ | 149 | `—` | ✗ | 3737 | `—` | ✗ | 7552 |  |
| 30 | `show me ram usage` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 2 | `get_cpu_ram` | ✓ | 1036 | `—` | ✗ | 115 | `—` | ✗ | 4227 | `—` | ✗ | 7490 |  |
| 31 | `how much memory am I using` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 11 | `get_system_status` | ✗ | 428 | `—` | ✗ | 537 | `—` | ✗ | 3927 | `—` | ✗ | 7647 |  |
| 32 | `system performance` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 32 | `get_system_status` | ✗ | 348 | `—` | ✗ | 310 | `—` | ✗ | 5806 | `—` | ✗ | 8007 |  |
| 33 | `cpu load` | `get_cpu_ram` | `get_cpu_ram` | ✓ | 2 | `get_system_status` | ✗ | 630 | `—` | ✗ | 850 | `—` | ✗ | 5567 | `—` | ✗ | 10974 |  |
| 34 | `my computer's performance has dropped` | `llm_chat` | `llm_chat` | ✓ | 12 | `get_system_status` | ✗ | 318 | `—` | ✗ | 152 | `—` | ✗ | 4719 | `—` | ✗ | 9434 | Negative |
| 35 | `I forgot what I had for memory yesterday` | `llm_chat` | `llm_chat` | ✓ | 11 | `get_system_status` | ✗ | 710 | `—` | ✗ | 935 | `—` | ✗ | 3832 | `—` | ✗ | 8796 | Negative — figurative memory |
| 36 | `system status` | `get_system_status` | `get_system_status` | ✓ | 2 | `get_system_status` | ✓ | 1038 | `—` | ✗ | 269 | `—` | ✗ | 3729 | `—` | ✗ | 9386 |  |
| 37 | `system health` | `get_system_status` | `get_system_status` | ✓ | 2 | `get_system_status` | ✓ | 397 | `—` | ✗ | 145 | `—` | ✗ | 3983 | `—` | ✗ | 7862 |  |
| 38 | `give me a system overview` | `get_system_status` | `get_system_status` | ✓ | 11 | `get_system_status` | ✓ | 438 | `—` | ✗ | 131 | `—` | ✗ | 3811 | `—` | ✗ | 9591 |  |
| 39 | `how is the machine doing` | `get_system_status` | `llm_chat` | ✗ | 13 | `get_system_status` | ✓ | 441 | `—` | ✗ | 334 | `—` | ✗ | 4273 | `—` | ✗ | 8139 |  |
| 40 | `friday status` | `get_friday_status` | `get_friday_status` | ✓ | 2 | `get_system_status` | ✗ | 1039 | `—` | ✗ | 280 | `—` | ✗ | 4003 | `—` | ✗ | 8389 |  |
| 41 | `are you ready friday` | `get_friday_status` | `get_friday_status` | ✓ | 2 | `get_system_status` | ✗ | 916 | `—` | ✗ | 307 | `—` | ✗ | 4230 | `—` | ✗ | 7850 |  |
| 42 | `are you online` | `get_friday_status` | `llm_chat` | ✗ | 12 | `get_system_status` | ✗ | 509 | `—` | ✗ | 1723 | `—` | ✗ | 3575 | `—` | ✗ | 8933 |  |
| 43 | `check friday` | `get_friday_status` | `get_friday_status` | ✓ | 2 | `get_system_status` | ✗ | 328 | `—` | ✗ | 844 | `—` | ✗ | 3973 | `—` | ✗ | 8050 |  |
| 44 | `your status` | `get_friday_status` | `get_friday_status` | ✓ | 2 | `get_system_status` | ✗ | 476 | `—` | ✗ | 573 | `—` | ✗ | 3633 | `—` | ✗ | 8911 |  |
| 45 | `is everything loaded` | `get_friday_status` | `llm_chat` | ✗ | 13 | `get_system_status` | ✗ | 369 | `—` | ✗ | 138 | `—` | ✗ | 3557 | `—` | ✗ | 8444 |  |
| 46 | `what's the weather in Mumbai` | `get_weather` | `get_weather` | ✓ | 3 | `get_system_status` | ✗ | 354 | `—` | ✗ | 619 | `—` | ✗ | 3817 | `—` | ✗ | 8905 |  |
| 47 | `weather in Bangalore` | `get_weather` | `get_weather` | ✓ | 2 | `get_system_status` | ✗ | 709 | `—` | ✗ | 169 | `—` | ✗ | 3785 | `—` | ✗ | 8851 |  |
| 48 | `how's the weather today` | `get_weather` | `get_weather` | ✓ | 2 | `get_system_status` | ✗ | 506 | `—` | ✗ | 1102 | `—` | ✗ | 8479 | `—` | ✗ | 7846 |  |
| 49 | `is it going to rain tomorrow` | `get_weather` | `llm_chat` | ✗ | 27 | `get_system_status` | ✗ | 469 | `—` | ✗ | 433 | `—` | ✗ | 3733 | `—` | ✗ | 8252 |  |
| 50 | `what's the temperature outside` | `get_weather` | `get_weather` | ✓ | 3 | `get_system_status` | ✗ | 372 | `—` | ✗ | 224 | `—` | ✗ | 4080 | `—` | ✗ | 8314 |  |
| 51 | `forecast for Delhi tomorrow` | `get_weather` | `get_weather` | ✓ | 3 | `get_system_status` | ✗ | 634 | `—` | ✗ | 675 | `—` | ✗ | 4890 | `—` | ✗ | 7607 |  |
| 52 | `is it sunny in New York` | `get_weather` | `get_weather` | ✓ | 11 | `get_system_status` | ✗ | 304 | `—` | ✗ | 1228 | `—` | ✗ | 4682 | `—` | ✗ | 10052 |  |
| 53 | `what's the wheather like` | `get_weather` | `get_weather` | ✓ | 3 | `get_system_status` | ✗ | 433 | `—` | ✗ | 381 | `—` | ✗ | 4086 | `—` | ✗ | 8321 | STT typo |
| 54 | `weather forecast please` | `get_weather` | `get_weather` | ✓ | 10 | `get_system_status` | ✗ | 318 | `—` | ✗ | 646 | `—` | ✗ | 3648 | `—` | ✗ | 8356 |  |
| 55 | `open calculator` | `launch_app` | `launch_app` | ✓ | 4 | `calculator` | ✗ | 292 | `—` | ✗ | 808 | `—` | ✗ | 3496 | `—` | ✗ | 9815 |  |
| 56 | `launch firefox` | `launch_app` | `launch_app` | ✓ | 3 | `firefox` | ✗ | 804 | `—` | ✗ | 126 | `—` | ✗ | 3886 | `—` | ✗ | 7564 |  |
| 57 | `start the terminal` | `launch_app` | `launch_app` | ✓ | 9 | `get_system_status` | ✗ | 402 | `—` | ✗ | 138 | `—` | ✗ | 3542 | `—` | ✗ | 7565 |  |
| 58 | `bring up the file manager` | `launch_app` | `launch_app` | ✓ | 2 | `get_system_status` | ✗ | 408 | `—` | ✗ | 505 | `—` | ✗ | 4506 | `—` | ✗ | 7782 |  |
| 59 | `open vscode for me` | `launch_app` | `launch_app` | ✓ | 3 | `vscode` | ✗ | 1109 | `—` | ✗ | 377 | `—` | ✗ | 3683 | `—` | ✗ | 8097 |  |
| 60 | `launch chromium` | `launch_app` | `launch_app` | ✓ | 1 | `chromium` | ✗ | 286 | `—` | ✗ | 119 | `—` | ✗ | 3933 | `—` | ✗ | 7903 |  |
| 61 | `open spotify and discord` | `launch_app` | `launch_app` | ✓ | 2 | `spotify` | ✗ | 488 | `—` | ✗ | 139 | `—` | ✗ | 3636 | `—` | ✗ | 8575 | Multi-app |
| 62 | `I deleted my screenshot folder` | `llm_chat` | `llm_chat` | ✓ | 9 | `get_system_status` | ✗ | 519 | `—` | ✗ | 2212 | `—` | ✗ | 3681 | `—` | ✗ | 8265 | Negative |
| 63 | `take a screenshot` | `take_screenshot` | `take_screenshot` | ✓ | 2 | `get_system_status` | ✗ | 841 | `—` | ✗ | 713 | `—` | ✗ | 5510 | `—` | ✗ | 7884 |  |
| 64 | `capture the screen` | `take_screenshot` | `take_screenshot` | ✓ | 7 | `get_system_status` | ✗ | 441 | `—` | ✗ | 262 | `—` | ✗ | 3731 | `—` | ✗ | 8433 |  |
| 65 | `screenshot please` | `take_screenshot` | `take_screenshot` | ✓ | 2 | `get_system_status` | ✗ | 467 | `—` | ✗ | 152 | `—` | ✗ | 4069 | `—` | ✗ | 8890 |  |
| 66 | `grab a screen capture` | `take_screenshot` | `take_screenshot` | ✓ | 2 | `get_system_status` | ✗ | 443 | `—` | ✗ | 139 | `—` | ✗ | 4475 | `—` | ✗ | 8515 |  |
| 67 | `snap a screenshot` | `take_screenshot` | `take_screenshot` | ✓ | 2 | `get_system_status` | ✗ | 644 | `—` | ✗ | 1029 | `—` | ✗ | 3591 | `—` | ✗ | 7764 |  |
| 68 | `take a picture of my screen` | `take_screenshot` | `take_screenshot` | ✓ | 8 | `get_system_status` | ✗ | 502 | `—` | ✗ | 891 | `—` | ✗ | 3926 | `—` | ✗ | 8664 |  |
| 69 | `I lost the screenshot I took earlier` | `llm_chat` | `take_screenshot` | ✗ | 11 | `get_system_status` | ✗ | 1350 | `—` | ✗ | 156 | `—` | ✗ | 4625 | `—` | ✗ | 15735 | Negative |
| 70 | `set volume to 50` | `set_volume` | `set_volume` | ✓ | 3 | `get_system_status` | ✗ | 377 | `—` | ✗ | 149 | `—` | ✗ | 3663 | `—` | ✗ | 7535 |  |
| 71 | `turn the volume up` | `set_volume` | `set_volume` | ✓ | 3 | `get_system_status` | ✗ | 470 | `name` | ✗ | 167 | `—` | ✗ | 3760 | `—` | ✗ | 8694 |  |
| 72 | `mute` | `set_volume` | `set_volume` | ✓ | 2 | `get_system_status` | ✗ | 340 | `—` | ✗ | 152 | `—` | ✗ | 3865 | `—` | ✗ | 7431 |  |
| 73 | `unmute` | `set_volume` | `set_volume` | ✓ | 2 | `get_system_status` | ✗ | 445 | `—` | ✗ | 813 | `—` | ✗ | 3836 | `—` | ✗ | 7505 |  |
| 74 | `lower the volume` | `set_volume` | `set_volume` | ✓ | 2 | `get_system_status` | ✗ | 1300 | `—` | ✗ | 116 | `—` | ✗ | 4626 | `—` | ✗ | 7561 |  |
| 75 | `increase volume by 10` | `set_volume` | `set_volume` | ✓ | 2 | `get_system_status` | ✗ | 1297 | `—` | ✗ | 142 | `—` | ✗ | 5749 | `—` | ✗ | 7720 |  |
| 76 | `make it louder` | `set_volume` | `llm_chat` | ✗ | 10 | `get_system_status` | ✗ | 481 | `—` | ✗ | 1400 | `—` | ✗ | 3783 | `—` | ✗ | 7425 |  |
| 77 | `raise the question with the team` | `llm_chat` | `llm_chat` | ✓ | 8 | `get_system_status` | ✗ | 454 | `—` | ✗ | 118 | `—` | ✗ | 3815 | `—` | ✗ | 7555 | Negative |
| 78 | `set voice mode to manual` | `set_voice_mode` | `set_voice_mode` | ✓ | 2 | `get_system_status` | ✗ | 1025 | `—` | ✗ | 162 | `—` | ✗ | 4288 | `—` | ✗ | 7548 |  |
| 79 | `set voice to manual` | `set_voice_mode` | `set_voice_mode` | ✓ | 2 | `get_system_status` | ✗ | 372 | `—` | ✗ | 118 | `—` | ✗ | 4573 | `—` | ✗ | 8115 | Issue 2 — 'mode' dropped |
| 80 | `switch voice on demand` | `set_voice_mode` | `set_voice_mode` | ✓ | 2 | `get_system_status` | ✗ | 436 | `—` | ✗ | 2171 | `—` | ✗ | 3406 | `—` | ✗ | 7347 | Issue 2 |
| 81 | `change voice mode to persistent` | `set_voice_mode` | `set_voice_mode` | ✓ | 2 | `get_system_status` | ✗ | 740 | `—` | ✗ | 179 | `—` | ✗ | 4289 | `—` | ✗ | 7774 |  |
| 82 | `use wake word mode` | `set_voice_mode` | `llm_chat` | ✗ | 8 | `wake word mode` | ✗ | 378 | `—` | ✗ | 150 | `—` | ✗ | 5073 | `—` | ✗ | 7743 |  |
| 83 | `turn off the voice mode` | `set_voice_mode` | `disable_voice` | ✗ | 2 | `get_system_status` | ✗ | 595 | `—` | ✗ | 202 | `—` | ✗ | 3688 | `—` | ✗ | 7508 |  |
| 84 | `enable voice` | `enable_voice` | `enable_voice` | ✓ | 2 | `get_system_status` | ✗ | 348 | `—` | ✗ | 190 | `—` | ✗ | 4826 | `—` | ✗ | 7262 |  |
| 85 | `turn the microphone on` | `enable_voice` | `enable_voice` | ✓ | 6 | `get_system_status` | ✗ | 483 | `—` | ✗ | 248 | `—` | ✗ | 4017 | `—` | ✗ | 7570 |  |
| 86 | `start listening` | `enable_voice` | `enable_voice` | ✓ | 3 | `get_system_status` | ✗ | 351 | `—` | ✗ | 1295 | `—` | ✗ | 3816 | `—` | ✗ | 7572 |  |
| 87 | `Friday wake up` | `enable_voice` | `enable_voice` | ✓ | 2 | `get_system_status` | ✗ | 606 | `—` | ✗ | 162 | `—` | ✗ | 3589 | `—` | ✗ | 7383 |  |
| 88 | `disable voice` | `disable_voice` | `disable_voice` | ✓ | 2 | `get_system_status` | ✗ | 331 | `—` | ✗ | 3466 | `—` | ✗ | 4598 | `—` | ✗ | 7397 |  |
| 89 | `turn the microphone off` | `disable_voice` | `disable_voice` | ✓ | 7 | `get_system_status` | ✗ | 377 | `—` | ✗ | 399 | `—` | ✗ | 3822 | `—` | ✗ | 7357 |  |
| 90 | `stop listening` | `disable_voice` | `disable_voice` | ✓ | 2 | `get_system_status` | ✗ | 327 | `—` | ✗ | 623 | `—` | ✗ | 4041 | `—` | ✗ | 7491 |  |
| 91 | `mute the mic` | `disable_voice` | `set_volume` | ✗ | 1 | `get_system_status` | ✗ | 440 | `—` | ✗ | 2081 | `—` | ✗ | 4112 | `—` | ✗ | 7371 |  |
| 92 | `remind me to drink water in 15 minutes` | `set_reminder` | `set_reminder` | ✓ | 4 | `get_system_status` | ✗ | 420 | `—` | ✗ | 656 | `—` | ✗ | 4007 | `—` | ✗ | 7804 |  |
| 93 | `set a reminder for 5 pm` | `set_reminder` | `set_reminder` | ✓ | 1 | `get_system_status` | ✗ | 416 | `—` | ✗ | 405 | `—` | ✗ | 4038 | `—` | ✗ | 8850 |  |
| 94 | `remind me to call mom at 4pm` | `set_reminder` | `set_reminder` | ✓ | 1 | `get_system_status` | ✗ | 325 | `—` | ✗ | 841 | `—` | ✗ | 5261 | `—` | ✗ | 8367 |  |
| 95 | `remind me about the gym` | `set_reminder` | `set_reminder` | ✓ | 1 | `get_system_status` | ✗ | 3128 | `—` | ✗ | 371 | `—` | ✗ | 3730 | `—` | ✗ | 7774 |  |
| 96 | `set a 10 minute reminder` | `set_reminder` | `list_reminders` | ✗ | 8 | `get_system_status` | ✗ | 399 | `—` | ✗ | 195 | `—` | ✗ | 4378 | `—` | ✗ | 8169 |  |
| 97 | `remind me to take medicine at 9 every night` | `set_reminder` | `set_reminder` | ✓ | 2 | `get_system_status` | ✗ | 502 | `—` | ✗ | 647 | `—` | ✗ | 3935 | `—` | ✗ | 7764 |  |
| 98 | `remind me` | `set_reminder` | `set_reminder` | ✓ | 1 | `get_system_status` | ✗ | 372 | `—` | ✗ | 383 | `—` | ✗ | 4131 | `—` | ✗ | 7186 |  |
| 99 | `set up a reminer to stretch` | `set_reminder` | `list_reminders` | ✗ | 7 | `get_system_status` | ✗ | 445 | `—` | ✗ | 532 | `—` | ✗ | 3930 | `—` | ✗ | 7845 | STT typo |
| 100 | `list my reminders` | `list_reminders` | `list_reminders` | ✓ | 2 | `get_system_status` | ✗ | 1345 | `—` | ✗ | 2729 | `—` | ✗ | 3893 | `—` | ✗ | 7398 | Issue 7 |
| 101 | `what are my reminders` | `list_reminders` | `list_reminders` | ✓ | 2 | `get_system_status` | ✗ | 435 | `—` | ✗ | 705 | `—` | ✗ | 3854 | `—` | ✗ | 7529 |  |
| 102 | `show me my reminders` | `list_reminders` | `list_reminders` | ✓ | 7 | `get_system_status` | ✗ | 328 | `—` | ✗ | 755 | `—` | ✗ | 4942 | `—` | ✗ | 7578 |  |
| 103 | `upcoming reminders` | `list_reminders` | `list_reminders` | ✓ | 2 | `get_system_status` | ✗ | 450 | `—` | ✗ | 504 | `—` | ✗ | 4317 | `—` | ✗ | 7333 |  |
| 104 | `what reminders do I have` | `list_reminders` | `list_reminders` | ✓ | 2 | `get_system_status` | ✗ | 482 | `—` | ✗ | 568 | `—` | ✗ | 4510 | `—` | ✗ | 7473 |  |
| 105 | `what's on my calendar` | `list_calendar_events` | `list_calendar_events` | ✓ | 2 | `get_system_status` | ✗ | 405 | `—` | ✗ | 990 | `—` | ✗ | 5274 | `—` | ✗ | 7560 | Issue 7 |
| 106 | `list calendar events` | `list_calendar_events` | `list_calendar_events` | ✓ | 1 | `get_system_status` | ✗ | 381 | `—` | ✗ | 941 | `—` | ✗ | 4364 | `—` | ✗ | 7601 |  |
| 107 | `show me my agenda` | `list_calendar_events` | `list_calendar_events` | ✓ | 7 | `get_system_status` | ✗ | 364 | `—` | ✗ | 600 | `—` | ✗ | 3904 | `—` | ✗ | 7486 |  |
| 108 | `what's my schedule today` | `list_calendar_events` | `list_calendar_events` | ✓ | 9 | `get_system_status` | ✗ | 343 | `—` | ✗ | 1479 | `—` | ✗ | 4664 | `—` | ✗ | 7626 |  |
| 109 | `any meetings today` | `list_calendar_events` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 307 | `—` | ✗ | 270 | `—` | ✗ | 5167 | `—` | ✗ | 8407 |  |
| 110 | `upcoming events` | `list_calendar_events` | `list_calendar_events` | ✓ | 2 | `get_system_status` | ✗ | 423 | `—` | ✗ | 191 | `—` | ✗ | 3834 | `—` | ✗ | 7466 |  |
| 111 | `schedule a meeting in 15 minutes` | `create_calendar_event` | `create_calendar_event` | ✓ | 2 | `get_system_status` | ✗ | 388 | `—` | ✗ | 1053 | `—` | ✗ | 4000 | `—` | ✗ | 7596 | Issue 11 — title=Meeting |
| 112 | `add a calendar event Lunch tomorrow at noon` | `create_calendar_event` | `create_calendar_event` | ✓ | 2 | `get_system_status` | ✗ | 434 | `—` | ✗ | 395 | `—` | ✗ | 4091 | `—` | ✗ | 7712 |  |
| 113 | `create a calendar event titled Q4 review at 3pm` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 396 | `—` | ✗ | 304 | `—` | ✗ | 4216 | `—` | ✗ | 8692 |  |
| 114 | `create a calender evnet` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 488 | `—` | ✗ | 197 | `—` | ✗ | 3772 | `—` | ✗ | 8858 | Issue 8 — STT typo |
| 115 | `book a dentist appointment for Friday at 3pm` | `create_calendar_event` | `create_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 1043 | `—` | ✗ | 466 | `—` | ✗ | 4037 | `—` | ✗ | 7740 |  |
| 116 | `put a meeting on the calendar tomorrow at 10am` | `create_calendar_event` | `llm_chat` | ✗ | 9 | `get_system_status` | ✗ | 470 | `—` | ✗ | 345 | `—` | ✗ | 5364 | `—` | ✗ | 8071 |  |
| 117 | `schedule a 1 on 1 with Sam` | `create_calendar_event` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 607 | `—` | ✗ | 795 | `—` | ✗ | 3719 | `—` | ✗ | 7812 |  |
| 118 | `set up an event for next Monday` | `create_calendar_event` | `create_calendar_event` | ✓ | 2 | `get_system_status` | ✗ | 486 | `—` | ✗ | 176 | `—` | ✗ | 3720 | `—` | ✗ | 7757 |  |
| 119 | `move my 3pm to 4pm` | `move_calendar_event` | `move_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 379 | `—` | ✗ | 159 | `—` | ✗ | 3871 | `—` | ✗ | 7615 |  |
| 120 | `reschedule the standup to 11am` | `move_calendar_event` | `move_calendar_event` | ✓ | 2 | `get_system_status` | ✗ | 477 | `—` | ✗ | 584 | `—` | ✗ | 4079 | `—` | ✗ | 8381 |  |
| 121 | `shift the dentist to next week` | `move_calendar_event` | `llm_chat` | ✗ | 10 | `get_system_status` | ✗ | 408 | `—` | ✗ | 173 | `—` | ✗ | 4696 | `—` | ✗ | 7798 |  |
| 122 | `push the gym block back an hour` | `move_calendar_event` | `move_calendar_event` | ✓ | 2 | `get_system_status` | ✗ | 678 | `—` | ✗ | 308 | `—` | ✗ | 4555 | `—` | ✗ | 7806 |  |
| 123 | `cancel the next event` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 410 | `—` | ✗ | 162 | `—` | ✗ | 4328 | `—` | ✗ | 7494 |  |
| 124 | `cancel the dentist appointment` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 484 | `—` | ✗ | 1964 | `—` | ✗ | 3532 | `—` | ✗ | 8113 |  |
| 125 | `delete the 3pm meeting` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 356 | `—` | ✗ | 666 | `—` | ✗ | 4208 | `—` | ✗ | 7572 |  |
| 126 | `remove tomorrow's standup` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 390 | `—` | ✗ | 223 | `—` | ✗ | 3752 | `—` | ✗ | 8124 |  |
| 127 | `drop the gym block` | `cancel_calendar_event` | `cancel_calendar_event` | ✓ | 1 | `get_system_status` | ✗ | 395 | `—` | ✗ | 502 | `—` | ✗ | 4086 | `—` | ✗ | 7772 |  |
| 128 | `save note milk eggs bread` | `save_note` | `end_dictation` | ✗ | 1 | `get_system_status` | ✗ | 417 | `—` | ✗ | 828 | `—` | ✗ | 4578 | `—` | ✗ | 7683 |  |
| 129 | `make a quick note that I owe Sam 20 dollars` | `save_note` | `save_note` | ✓ | 2 | `get_system_status` | ✗ | 470 | `—` | ✗ | 474 | `—` | ✗ | 4478 | `—` | ✗ | 8065 |  |
| 130 | `note this down: ship the PR by Friday` | `save_note` | `save_note` | ✓ | 2 | `get_system_status` | ✗ | 443 | `—` | ✗ | 2994 | `—` | ✗ | 4090 | `—` | ✗ | 7946 |  |
| 131 | `remember that I prefer dark mode` | `save_note` | `save_note` | ✓ | 2 | `get_system_status` | ✗ | 490 | `—` | ✗ | 652 | `—` | ✗ | 4107 | `—` | ✗ | 7900 |  |
| 132 | `jot down: pick up dry cleaning` | `save_note` | `save_note` | ✓ | 2 | `get_system_status` | ✗ | 366 | `—` | ✗ | 667 | `—` | ✗ | 3866 | `—` | ✗ | 7713 |  |
| 133 | `add to my notes: read the new RFC` | `save_note` | `save_note` | ✓ | 2 | `get_system_status` | ✗ | 424 | `—` | ✗ | 462 | `—` | ✗ | 3601 | `—` | ✗ | 7608 |  |
| 134 | `save a note about the meeting` | `save_note` | `save_note` | ✓ | 3 | `get_system_status` | ✗ | 365 | `—` | ✗ | 840 | `—` | ✗ | 4374 | `—` | ✗ | 9385 |  |
| 135 | `read my notes` | `read_notes` | `read_notes` | ✓ | 1 | `read_notes` | ✓ | 455 | `—` | ✗ | 694 | `—` | ✗ | 5364 | `—` | ✗ | 8743 |  |
| 136 | `show me my notes` | `read_notes` | `read_notes` | ✓ | 11 | `get_system_status` | ✗ | 321 | `—` | ✗ | 133 | `—` | ✗ | 4668 | `—` | ✗ | 8968 |  |
| 137 | `list my notes` | `read_notes` | `read_notes` | ✓ | 2 | `get_system_status` | ✗ | 355 | `—` | ✗ | 563 | `—` | ✗ | 4949 | `—` | ✗ | 7653 |  |
| 138 | `what notes do I have` | `read_notes` | `read_notes` | ✓ | 10 | `get_system_status` | ✗ | 354 | `—` | ✗ | 907 | `—` | ✗ | 5682 | `—` | ✗ | 7656 |  |
| 139 | `create a file` | `manage_file` | `manage_file` | ✓ | 3 | `get_system_status` | ✗ | 484 | `—` | ✗ | 1274 | `—` | ✗ | 4249 | `—` | ✗ | 7413 |  |
| 140 | `create a file named ideas.md` | `manage_file` | `manage_file` | ✓ | 3 | `get_system_status` | ✗ | 362 | `—` | ✗ | 170 | `—` | ✗ | 4127 | `—` | ✗ | 7758 |  |
| 141 | `make a new file called todo.txt` | `manage_file` | `manage_file` | ✓ | 3 | `get_system_status` | ✗ | 403 | `—` | ✗ | 429 | `—` | ✗ | 4226 | `—` | ✗ | 9175 |  |
| 142 | `save that to a file called reverse.py` | `manage_file` | `manage_file` | ✓ | 3 | `reverse.py` | ✗ | 1465 | `—` | ✗ | 141 | `—` | ✗ | 4329 | `—` | ✗ | 7843 | Issue 10 |
| 143 | `write the answer to notes.md` | `manage_file` | `manage_file` | ✓ | 3 | `get_system_status` | ✗ | 412 | `—` | ✗ | 190 | `—` | ✗ | 4779 | `—` | ✗ | 7947 |  |
| 144 | `append second line to scratch.md` | `manage_file` | `manage_file` | ✓ | 3 | `get_system_status` | ✗ | 307 | `—` | ✗ | 163 | `—` | ✗ | 3957 | `—` | ✗ | 7833 | Issue 5 |
| 145 | `open the README file` | `open_file` | `open_file` | ✓ | 2 | `get_system_status` | ✗ | 402 | `—` | ✗ | 131 | `—` | ✗ | 3752 | `—` | ✗ | 8012 |  |
| 146 | `open notes.md` | `open_file` | `open_file` | ✓ | 2 | `notes.md` | ✗ | 197 | `—` | ✗ | 213 | `—` | ✗ | 4967 | `—` | ✗ | 7743 |  |
| 147 | `read me the latest report` | `read_file` | `read_file` | ✓ | 1 | `get_system_status` | ✗ | 413 | `—` | ✗ | 232 | `—` | ✗ | 3601 | `—` | ✗ | 7841 |  |
| 148 | `show the contents of config.yaml` | `read_file` | `llm_chat` | ✗ | 11 | `config.yaml` | ✗ | 315 | `—` | ✗ | 137 | `—` | ✗ | 4377 | `—` | ✗ | 8015 |  |
| 149 | `summarize that file for me` | `summarize_file` | `summarize_file` | ✓ | 2 | `summarize_file` | ✓ | 347 | `—` | ✗ | 158 | `—` | ✗ | 3853 | `—` | ✗ | 8239 |  |
| 150 | `give me a summary of the report` | `summarize_file` | `summarize_file` | ✓ | 2 | `get_system_status` | ✗ | 324 | `—` | ✗ | 325 | `—` | ✗ | 3710 | `—` | ✗ | 8093 |  |
| 151 | `find the resume pdf` | `search_file` | `search_file` | ✓ | 8 | `get_system_status` | ✗ | 338 | `—` | ✗ | 791 | `—` | ✗ | 3634 | `—` | ✗ | 8584 |  |
| 152 | `search for budget xlsx` | `search_file` | `search_file` | ✓ | 8 | `get_system_status` | ✗ | 379 | `—` | ✗ | 150 | `—` | ✗ | 3946 | `—` | ✗ | 7750 |  |
| 153 | `locate my driver's license image` | `search_file` | `search_file` | ✓ | 9 | `get_system_status` | ✗ | 350 | `—` | ✗ | 1165 | `—` | ✗ | 7075 | `—` | ✗ | 8055 |  |
| 154 | `what's in my Downloads folder` | `list_folder_contents` | `llm_chat` | ✗ | 9 | `get_system_status` | ✗ | 510 | `—` | ✗ | 542 | `—` | ✗ | 4262 | `—` | ✗ | 7852 |  |
| 155 | `list the desktop` | `list_folder_contents` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 302 | `—` | ✗ | 151 | `—` | ✗ | 3634 | `—` | ✗ | 7794 |  |
| 156 | `show me the documents folder` | `list_folder_contents` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 343 | `—` | ✗ | 154 | `—` | ✗ | 3834 | `—` | ✗ | 8193 |  |
| 157 | `open the downloads folder` | `open_folder` | `open_file` | ✗ | 2 | `get_system_status` | ✗ | 394 | `—` | ✗ | 743 | `—` | ✗ | 4018 | `—` | ✗ | 8677 |  |
| 158 | `open my projects folder` | `open_folder` | `open_file` | ✗ | 2 | `get_system_status` | ✗ | 414 | `—` | ✗ | 842 | `—` | ✗ | 3560 | `—` | ✗ | 7325 |  |
| 159 | `play sahiba on youtube` | `play_youtube` | `play_youtube` | ✓ | 1 | `play sahiba on youtube` | ✗ | 353 | `—` | ✗ | 140 | `—` | ✗ | 3654 | `—` | ✗ | 7627 |  |
| 160 | `play despacito on youtube` | `play_youtube` | `play_youtube` | ✓ | 1 | `play_youtube` | ✓ | 548 | `—` | ✗ | 185 | `—` | ✗ | 5981 | `—` | ✗ | 7551 |  |
| 161 | `pull up that song on youtube` | `play_youtube` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 466 | `—` | ✗ | 133 | `—` | ✗ | 3727 | `—` | ✗ | 8289 |  |
| 162 | `play sahiba on youtube music` | `play_youtube_music` | `play_youtube_music` | ✓ | 2 | `play sahiba on youtube music` | ✗ | 332 | `—` | ✗ | 175 | `—` | ✗ | 4233 | `—` | ✗ | 8012 |  |
| 163 | `play lofi on youtube music` | `play_youtube_music` | `play_youtube_music` | ✓ | 1 | `—` | ✗ | 1415 | `—` | ✗ | 153 | `—` | ✗ | 4031 | `—` | ✗ | 7770 |  |
| 164 | `google capital of france` | `search_google` | `search_google` | ✓ | 1 | `search_google` | ✓ | 439 | `—` | ✗ | 134 | `—` | ✗ | 3712 | `—` | ✗ | 9074 |  |
| 165 | `search google for python typing` | `search_google` | `search_google` | ✓ | 1 | `get_system_status` | ✗ | 339 | `—` | ✗ | 161 | `—` | ✗ | 4271 | `—` | ✗ | 7902 |  |
| 166 | `look up the weather on google` | `search_google` | `search_google` | ✓ | 1 | `get_system_status` | ✗ | 1434 | `—` | ✗ | 612 | `—` | ✗ | 3772 | `—` | ✗ | 8236 |  |
| 167 | `open github.com` | `open_browser_url` | `open_file` | ✗ | 2 | `get_system_status` | ✗ | 374 | `—` | ✗ | 266 | `—` | ✗ | 4038 | `—` | ✗ | 11004 |  |
| 168 | `go to nytimes.com` | `open_browser_url` | `llm_chat` | ✗ | 9 | `get_system_status` | ✗ | 428 | `—` | ✗ | 132 | `—` | ✗ | 3619 | `—` | ✗ | 7842 |  |
| 169 | `pause` | `browser_media_control` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 436 | `—` | ✗ | 301 | `—` | ✗ | 4155 | `—` | ✗ | 8107 |  |
| 170 | `resume the video` | `browser_media_control` | `llm_chat` | ✗ | 10 | `get_system_status` | ✗ | 652 | `—` | ✗ | 195 | `—` | ✗ | 5314 | `—` | ✗ | 7747 |  |
| 171 | `skip 30 seconds forward` | `browser_media_control` | `search_file` | ✗ | 7 | `get_system_status` | ✗ | 327 | `—` | ✗ | 122 | `—` | ✗ | 9722 | `—` | ✗ | 8564 |  |
| 172 | `next track` | `browser_media_control` | `search_file` | ✗ | 2 | `get_system_status` | ✗ | 383 | `—` | ✗ | 161 | `—` | ✗ | 10065 | `—` | ✗ | 7689 |  |
| 173 | `next year is my promotion` | `llm_chat` | `llm_chat` | ✓ | 9 | `get_system_status` | ✗ | 676 | `—` | ✗ | 186 | `—` | ✗ | 8181 | `—` | ✗ | 8472 | Issue 9 — must NOT hijack |
| 174 | `remember that I work as a backend engineer at Acme` | `save_note` | `save_note` | ✓ | 2 | `get_system_status` | ✗ | 415 | `—` | ✗ | 844 | `—` | ✗ | 9400 | `—` | ✗ | 7985 | Issue 9 |
| 175 | `read my latest email` | `read_latest_email` | `read_latest_email` | ✓ | 1 | `get_system_status` | ✗ | 862 | `—` | ✗ | 628 | `—` | ✗ | 13193 | `—` | ✗ | 7888 |  |
| 176 | `what's the newest email in my inbox` | `read_latest_email` | `read_latest_email` | ✓ | 7 | `get_system_status` | ✗ | 440 | `—` | ✗ | 1910 | `—` | ✗ | 10800 | `—` | ✗ | 7581 |  |
| 177 | `read the most recent email` | `read_latest_email` | `read_latest_email` | ✓ | 8 | `get_system_status` | ✗ | 636 | `—` | ✗ | 2689 | `—` | ✗ | 3677 | `—` | ✗ | 7892 |  |
| 178 | `summarize my inbox` | `summarize_inbox` | `summarize_inbox` | ✓ | 2 | `summarize_email` | ✗ | 1399 | `—` | ✗ | 154 | `—` | ✗ | 4270 | `—` | ✗ | 8029 |  |
| 179 | `give me an inbox summary` | `summarize_inbox` | `summarize_inbox` | ✓ | 2 | `get_system_status` | ✗ | 326 | `—` | ✗ | 155 | `—` | ✗ | 4235 | `—` | ✗ | 8366 |  |
| 180 | `summarize all my unread emails` | `summarize_inbox` | `summarize_inbox` | ✓ | 7 | `summarize_email` | ✗ | 343 | `—` | ✗ | 180 | `—` | ✗ | 3675 | `—` | ✗ | 8255 |  |
| 181 | `start a focus session` | `start_focus_session` | `start_focus_session` | ✓ | 3 | `get_system_status` | ✗ | 351 | `—` | ✗ | 118 | `—` | ✗ | 3641 | `—` | ✗ | 7808 |  |
| 182 | `begin a pomodoro` | `start_focus_session` | `start_focus_session` | ✓ | 2 | `get_system_status` | ✗ | 545 | `—` | ✗ | 208 | `—` | ✗ | 3939 | `—` | ✗ | 7672 |  |
| 183 | `focus mode on` | `start_focus_session` | `start_focus_session` | ✓ | 1 | `get_system_status` | ✗ | 431 | `—` | ✗ | 119 | `—` | ✗ | 3913 | `—` | ✗ | 8249 |  |
| 184 | `start a 25 minute focus block` | `start_focus_session` | `launch_app` | ✗ | 3 | `get_system_status` | ✗ | 669 | `—` | ✗ | 200 | `—` | ✗ | 4018 | `—` | ✗ | 7580 |  |
| 185 | `end focus` | `end_focus_session` | `end_focus_session` | ✓ | 1 | `get_system_status` | ✗ | 643 | `—` | ✗ | 132 | `—` | ✗ | 5135 | `—` | ✗ | 7651 |  |
| 186 | `stop the focus session` | `end_focus_session` | `end_focus_session` | ✓ | 7 | `get_system_status` | ✗ | 412 | `—` | ✗ | 414 | `—` | ✗ | 3423 | `—` | ✗ | 7383 |  |
| 187 | `exit focus mode` | `end_focus_session` | `end_focus_session` | ✓ | 2 | `get_system_status` | ✗ | 525 | `—` | ✗ | 937 | `—` | ✗ | 3465 | `—` | ✗ | 8110 |  |
| 188 | `how much focus is left` | `focus_session_status` | `focus_session_status` | ✓ | 1 | `get_system_status` | ✗ | 324 | `—` | ✗ | 682 | `—` | ✗ | 3504 | `—` | ✗ | 7533 |  |
| 189 | `time left in focus` | `focus_session_status` | `focus_session_status` | ✓ | 7 | `get_system_status` | ✗ | 436 | `—` | ✗ | 896 | `—` | ✗ | 3485 | `—` | ✗ | 7632 |  |
| 190 | `am I in focus mode` | `focus_session_status` | `start_focus_session` | ✗ | 2 | `get_system_status` | ✗ | 1264 | `—` | ✗ | 1175 | `—` | ✗ | 3554 | `—` | ✗ | 8128 |  |
| 191 | `take a memo` | `start_dictation` | `start_dictation` | ✓ | 1 | `get_system_status` | ✗ | 322 | `—` | ✗ | 131 | `—` | ✗ | 3418 | `—` | ✗ | 7890 |  |
| 192 | `start dictation` | `start_dictation` | `start_dictation` | ✓ | 2 | `start_dictation` | ✓ | 401 | `—` | ✗ | 148 | `—` | ✗ | 3451 | `—` | ✗ | 7937 |  |
| 193 | `begin a journal entry` | `start_dictation` | `start_dictation` | ✓ | 1 | `get_system_status` | ✗ | 349 | `—` | ✗ | 139 | `—` | ✗ | 3462 | `—` | ✗ | 7817 |  |
| 194 | `Friday end memo` | `end_dictation` | `end_dictation` | ✓ | 1 | `get_system_status` | ✗ | 434 | `—` | ✗ | 201 | `—` | ✗ | 4152 | `—` | ✗ | 8445 |  |
| 195 | `stop dictation` | `end_dictation` | `end_dictation` | ✓ | 2 | `get_system_status` | ✗ | 542 | `—` | ✗ | 1114 | `—` | ✗ | 4268 | `—` | ✗ | 7465 |  |
| 196 | `finish the memo` | `end_dictation` | `end_dictation` | ✓ | 2 | `get_system_status` | ✗ | 1716 | `—` | ✗ | 137 | `—` | ✗ | 3449 | `—` | ✗ | 7519 |  |
| 197 | `cancel memo` | `cancel_dictation` | `cancel_dictation` | ✓ | 2 | `get_system_status` | ✗ | 1607 | `—` | ✗ | 134 | `—` | ✗ | 3449 | `—` | ✗ | 7448 |  |
| 198 | `discard the dictation` | `cancel_dictation` | `cancel_dictation` | ✓ | 1 | `get_system_status` | ✗ | 2316 | `—` | ✗ | 151 | `—` | ✗ | 3962 | `—` | ✗ | 7994 |  |
| 199 | `what do you remember about me` | `show_memories` | `show_memories` | ✓ | 1 | `get_system_status` | ✗ | 446 | `—` | ✗ | 878 | `—` | ✗ | 3526 | `—` | ✗ | 7929 |  |
| 200 | `what do you know about me` | `show_memories` | `show_memories` | ✓ | 1 | `get_system_status` | ✗ | 300 | `—` | ✗ | 723 | `—` | ✗ | 3875 | `—` | ✗ | 7889 |  |
| 201 | `show me my memories` | `show_memories` | `show_memories` | ✓ | 1 | `get_system_status` | ✗ | 400 | `—` | ✗ | 1138 | `—` | ✗ | 3481 | `—` | ✗ | 7908 |  |
| 202 | `what are my preferences` | `show_memories` | `show_memories` | ✓ | 1 | `get_system_status` | ✗ | 704 | `—` | ✗ | 1055 | `—` | ✗ | 3734 | `—` | ✗ | 7459 |  |
| 203 | `forget what I told you` | `delete_memory` | `delete_memory` | ✓ | 1 | `get_system_status` | ✗ | 461 | `—` | ✗ | 351 | `—` | ✗ | 3863 | `—` | ✗ | 7706 |  |
| 204 | `delete that memory` | `delete_memory` | `delete_memory` | ✓ | 1 | `get_system_status` | ✗ | 363 | `—` | ✗ | 391 | `—` | ✗ | 3524 | `—` | ✗ | 7444 |  |
| 205 | `stop remembering my address` | `delete_memory` | `delete_memory` | ✓ | 2 | `get_system_status` | ✗ | 500 | `—` | ✗ | 737 | `—` | ✗ | 3542 | `—` | ✗ | 7574 |  |
| 206 | `what can you do` | `show_capabilities` | `llm_chat` | ✗ | 8 | `get_system_status` | ✗ | 491 | `—` | ✗ | 161 | `—` | ✗ | 3536 | `—` | ✗ | 7447 |  |
| 207 | `list your tools` | `show_capabilities` | `llm_chat` | ✗ | 21 | `get_system_status` | ✗ | 530 | `—` | ✗ | 152 | `—` | ✗ | 4060 | `—` | ✗ | 7737 |  |
| 208 | `what features do you have` | `show_capabilities` | `llm_chat` | ✗ | 13 | `get_system_status` | ✗ | 447 | `—` | ✗ | 671 | `—` | ✗ | 4666 | `—` | ✗ | 7601 |  |
| 209 | `show me your commands` | `show_capabilities` | `llm_chat` | ✗ | 13 | `get_system_status` | ✗ | 969 | `—` | ✗ | 510 | `—` | ✗ | 3729 | `—` | ✗ | 7507 |  |
| 210 | `tell me what you can do` | `show_capabilities` | `llm_chat` | ✗ | 13 | `get_system_status` | ✗ | 394 | `—` | ✗ | 154 | `—` | ✗ | 3735 | `—` | ✗ | 7663 |  |
| 211 | `help me understand quantum entanglement` | `llm_chat` | `llm_chat` | ✓ | 15 | `get_system_status` | ✗ | 446 | `—` | ✗ | 196 | `—` | ✗ | 4071 | `—` | ✗ | 7627 | T-19.7 — must NOT show capabilities |
| 212 | `goodbye friday` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 3 | `get_system_status` | ✗ | 672 | `—` | ✗ | 229 | `—` | ✗ | 3371 | `—` | ✗ | 7338 |  |
| 213 | `bye` | `shutdown_assistant` | `shutdown_assistant` | ✓ | 3 | `get_system_status` | ✗ | 843 | `—` | ✗ | 141 | `—` | ✗ | 3366 | `—` | ✗ | 7408 |  |
| 214 | `shut down` | `shutdown_assistant` | `llm_chat` | ✗ | 17 | `get_system_status` | ✗ | 1337 | `—` | ✗ | 139 | `—` | ✗ | 3656 | `—` | ✗ | 8658 |  |
| 215 | `yes` | `confirm_yes` | `confirm_yes` | ✓ | 3 | `get_system_status` | ✗ | 793 | `—` | ✗ | 533 | `—` | ✗ | 3710 | `—` | ✗ | 7712 |  |
| 216 | `yeah do it` | `confirm_yes` | `confirm_yes` | ✓ | 11 | `get_system_status` | ✗ | 432 | `—` | ✗ | 104 | `—` | ✗ | 4259 | `—` | ✗ | 7735 |  |
| 217 | `sure go ahead` | `confirm_yes` | `llm_chat` | ✗ | 13 | `get_system_status` | ✗ | 1086 | `—` | ✗ | 139 | `—` | ✗ | 3428 | `—` | ✗ | 8322 |  |
| 218 | `no` | `confirm_no` | `confirm_no` | ✓ | 3 | `get_system_status` | ✗ | 379 | `—` | ✗ | 699 | `—` | ✗ | 3905 | `—` | ✗ | 7529 |  |
| 219 | `nope` | `confirm_no` | `confirm_no` | ✓ | 3 | `get_system_status` | ✗ | 392 | `—` | ✗ | 114 | `—` | ✗ | 3486 | `—` | ✗ | 7445 |  |
| 220 | `cancel` | `confirm_no` | `confirm_no` | ✓ | 3 | `get_system_status` | ✗ | 761 | `—` | ✗ | 140 | `—` | ✗ | 3415 | `—` | ✗ | 7505 |  |
| 221 | `the first one` | `select_file_candidate` | `select_file_candidate` | ✓ | 2 | `get_system_status` | ✗ | 437 | `—` | ✗ | 158 | `—` | ✗ | 3755 | `—` | ✗ | 7507 |  |
| 222 | `the second one` | `select_file_candidate` | `select_file_candidate` | ✓ | 3 | `get_system_status` | ✗ | 355 | `—` | ✗ | 138 | `—` | ✗ | 3449 | `—` | ✗ | 7275 |  |
| 223 | `the pdf one` | `select_file_candidate` | `select_file_candidate` | ✓ | 2 | `pdf` | ✗ | 380 | `—` | ✗ | 807 | `—` | ✗ | 3611 | `—` | ✗ | 7691 |  |
| 224 | `hello` | `greet` | `greet` | ✓ | 2 | `get_system_status` | ✗ | 362 | `—` | ✗ | 442 | `—` | ✗ | 3956 | `—` | ✗ | 7148 |  |
| 225 | `hi there` | `greet` | `greet` | ✓ | 1 | `get_system_status` | ✗ | 338 | `—` | ✗ | 685 | `—` | ✗ | 3557 | `—` | ✗ | 7383 |  |
| 226 | `hey friday` | `greet` | `greet` | ✓ | 1 | `get_system_status` | ✗ | 422 | `—` | ✗ | 646 | `—` | ✗ | 5534 | `—` | ✗ | 7650 |  |
| 227 | `good morning` | `greet` | `greet` | ✓ | 1 | `get_system_status` | ✗ | 1018 | `—` | ✗ | 156 | `—` | ✗ | 3918 | `—` | ✗ | 7375 |  |
| 228 | `good evening friday` | `greet` | `greet` | ✓ | 1 | `get_system_status` | ✗ | 571 | `—` | ✗ | 200 | `—` | ✗ | 3502 | `—` | ✗ | 7588 |  |
| 229 | `tell me a story` | `llm_chat` | `llm_chat` | ✓ | 9 | `get_system_status` | ✗ | 712 | `—` | ✗ | 420 | `—` | ✗ | 4667 | `—` | ✗ | 9555 |  |
| 230 | `explain how photosynthesis works` | `llm_chat` | `llm_chat` | ✓ | 10 | `—` | ✗ | 888 | `—` | ✗ | 185 | `—` | ✗ | 4363 | `—` | ✗ | 7955 |  |
| 231 | `why is the sky blue` | `llm_chat` | `llm_chat` | ✓ | 8 | `get_system_status` | ✗ | 472 | `—` | ✗ | 354 | `—` | ✗ | 3589 | `—` | ✗ | 7978 |  |
| 232 | `what's the meaning of life` | `llm_chat` | `llm_chat` | ✓ | 9 | `get_system_status` | ✗ | 742 | `—` | ✗ | 702 | `—` | ✗ | 3960 | `—` | ✗ | 8186 |  |
| 233 | `I'm feeling tired today` | `llm_chat` | `llm_chat` | ✓ | 9 | `get_system_status` | ✗ | 645 | `—` | ✗ | 406 | `—` | ✗ | 5088 | `—` | ✗ | 7737 |  |
| 234 | `do you think AI will replace jobs` | `llm_chat` | `llm_chat` | ✓ | 12 | `get_system_status` | ✗ | 788 | `—` | ✗ | 1083 | `—` | ✗ | 4760 | `—` | ✗ | 8060 |  |
| 235 | `give me a joke` | `llm_chat` | `llm_chat` | ✓ | 13 | `get_system_status` | ✗ | 471 | `—` | ✗ | 886 | `—` | ✗ | 4573 | `—` | ✗ | 7831 |  |
| 236 | `what should I have for dinner` | `llm_chat` | `llm_chat` | ✓ | 13 | `get_system_status` | ✗ | 492 | `—` | ✗ | 573 | `—` | ✗ | 3596 | `—` | ✗ | 7764 |  |
| 237 | `I am bored` | `llm_chat` | `llm_chat` | ✓ | 12 | `get_system_status` | ✗ | 332 | `—` | ✗ | 150 | `—` | ✗ | 3541 | `—` | ✗ | 8448 |  |
| 238 | `tell me about general relativity` | `llm_chat` | `llm_chat` | ✓ | 13 | `get_system_status` | ✗ | 1007 | `—` | ✗ | 142 | `—` | ✗ | 4885 | `—` | ✗ | 8039 |  |
| 239 | `how do I learn rust` | `llm_chat` | `llm_chat` | ✓ | 12 | `learn_rust` | ✗ | 1112 | `—` | ✗ | 792 | `—` | ✗ | 3563 | `—` | ✗ | 8260 |  |
| 240 | `write a haiku` | `llm_chat` | `llm_chat` | ✓ | 20 | `write_haiku` | ✗ | 678 | `—` | ✗ | 185 | `—` | ✗ | 4246 | `—` | ✗ | 7896 |  |
