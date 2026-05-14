# FRIDAY Setup Guide — Linux

This guide walks you through installing FRIDAY on Linux **two ways**:

1. **[Automated path](#automated-path-recommended)** — run `setup.sh`. Idempotent, skips any step whose output is already on disk.
2. **[Fully manual path](#fully-manual-path)** — every step typed out, no scripts. Use this if you're auditing what gets installed or if `setup.sh` fails partway.

Either way, **Piper TTS is always installed manually** — see the [Manual: Piper TTS](#manual-piper-tts-required-for-voice-output) section near the end.

For Windows, see [SETUP_GUIDE_WINDOWS.md](SETUP_GUIDE_WINDOWS.md).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **OS** | Ubuntu 22.04+ / Debian 12+ / Kali rolling (other Linuxes work but unsupported) |
| **Python** | 3.10 – 3.13 (3.11 recommended) |
| **RAM** | 8 GB minimum, 16 GB recommended |
| **Disk** | ~10 GB free for models + cache (Piper voice is another ~60 MB) |
| **Audio** | PipeWire (preferred) or ALSA. `libportaudio2` is required either way |
| **Internet** | Required only during setup; FRIDAY is local-first at runtime |
| **GPU** | Optional. llama.cpp and faster-whisper auto-use CUDA when present |

---

## Automated path (recommended)

```bash
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
chmod +x setup.sh
./setup.sh
```

The script's six phases each check before doing work:

| Phase | What it checks | What it skips when already present |
|---|---|---|
| 1. System packages | `dpkg -s <pkg>` for each required and optional package | Phase as a whole if everything is installed |
| 2. Python venv | `.venv/bin/python3` exists & is executable | Venv re-creation |
| 3. Python deps | SHA-256 of `requirements.txt` vs `.venv/.requirements.sha256` | Full `pip install` |
| 4. Playwright Chromium | `~/.cache/ms-playwright/chromium-*` exists | Browser download |
| 5. Models | Each `models/<file>.gguf` exists and is non-empty | Per-file download |
| 6. Wake autostart | `~/.config/systemd/user/friday-wake.service` exists | Re-registration |

After `setup.sh` completes successfully, jump to **[Manual: Piper TTS](#manual-piper-tts-required-for-voice-output)** and then **[Starting FRIDAY](#starting-friday)**.

---

## Fully manual path

Every step the script does, typed out. Run these in order.

### Step 1 — Install system packages

```bash
sudo apt-get update
sudo apt-get install -y \
    libportaudio2 ffmpeg python3-venv python3-pip \
    libxcb-cursor0 wget tar curl \
    wmctrl xdotool grim spectacle xfce4-screenshooter scrot maim \
    x11-utils libnotify-bin libsndfile1
```

Required: the first row. Optional but recommended: the second and third rows (window manipulation, screenshot tools, notifications). FRIDAY degrades gracefully if any optional package is missing.

### Step 2 — Clone the repository

```bash
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
```

### Step 3 — Create the Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate

# Verify the venv binary is executable (fails on noexec mounts)
test -x .venv/bin/python3 && echo "venv OK" || echo "FAIL: noexec mount?"
```

If the verify line prints `FAIL`, your project sits on a `noexec` mount
(common on NTFS, exFAT, some loop-mounted volumes). Move FRIDAY to your
home directory or remount the volume with `exec` permissions.

### Step 4 — Install Python dependencies

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

This pulls in PyQt6, llama-cpp-python, faster-whisper, sentence-transformers, mem0ai (optional), and the rest. Plan for ~3 GB of downloads on a cold install.

### Step 5 — Install the Playwright Chromium runtime

```bash
python -m playwright install chromium
# If you also want OS dependencies for headless Chromium:
# python -m playwright install --with-deps chromium
```

Skip this step if you don't plan to use browser-automation tools (YouTube, web search, Workspace browser flow).

### Step 6 — Download AI models

Create the directories first:

```bash
mkdir -p logs data data/chroma models
```

Then fetch each model. All four are GGUF files loadable by llama-cpp-python.

```bash
# Chat model — Qwen3 1.7B abliterated (~1.1 GB)
wget -O models/mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf \
    "https://huggingface.co/mlabonne/Qwen3-1.7B-abliterated-GGUF/resolve/main/Qwen3-1.7B-abliterated.Q4_K_M.gguf?download=true"

# Tool / Mem0 extraction model — Qwen3 4B abliterated (~2.5 GB)
wget -O models/mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf \
    "https://huggingface.co/mlabonne/Qwen3-4B-abliterated-GGUF/resolve/main/Qwen3-4B-abliterated.Q4_K_M.gguf?download=true"

# Vision model — SmolVLM2 2.2B Instruct (~1.1 GB)
wget -O models/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf \
    "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf?download=true"

# Vision multimodal projector — required by SmolVLM2 (~600 MB)
wget -O models/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf \
    "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf?download=true"
```

> **If any of those URLs 404**, the model has likely moved — search HuggingFace for the same filename and update the URL. The local filenames must match what `config.yaml` references under `models.chat.path`, `models.tool.path`, `vision.model_path`, and `vision.mmproj_path`.

### Step 7 — Download the Faster-Whisper STT model

```bash
python scripts/download_stt_model.py
```

This pulls `Systran/faster-whisper-base.en` (~145 MB) into the standard HuggingFace cache at `~/.cache/huggingface/hub/`. No action needed if the cache already has it.

### Step 8 — Manual: Piper TTS (required for voice output)

See the [Manual: Piper TTS](#manual-piper-tts-required-for-voice-output) section below — the steps are identical for the automated and manual paths.

### Step 9 — (Optional) Register the wake-word service

If you want hands-free activation:

```bash
# 1. Get a free Picovoice access key:
#    https://console.picovoice.ai/
#
# 2. Add to your shell rc:
echo 'export FRIDAY_PORCUPINE_KEY="<your-key-here>"' >> ~/.bashrc
source ~/.bashrc

# 3. Register the systemd --user service:
python modules/voice_io/register_wake.py

# 4. Confirm:
systemctl --user status friday-wake.service
```

### Step 10 — (Optional) Enable Mem0 long-term memory

Edit `config.yaml`:

```yaml
memory:
  enabled: true   # was false
```

On the next launch, FRIDAY will spawn a local llama.cpp extraction server on port 8181 (using the Qwen3 4B model you already downloaded). User facts will start surfacing in chat prompts as "What you know about the user".

---

## Manual: Piper TTS (required for voice output)

The setup scripts no longer install Piper because choosing a binary
build (CPU architecture / GPU) and a voice (language, speaker, quality)
is a deliberate decision. FRIDAY won't speak until you complete this section.

### A) Download the Piper engine binary

1. Go to <https://github.com/rhasspy/piper/releases>
2. Download the build matching your CPU:
   - **x86_64 Linux** → `piper_amd64.tar.gz`
   - **aarch64 / Raspberry Pi 64-bit** → `piper_arm64.tar.gz`
   - **armv7 / Raspberry Pi 32-bit** → `piper_armv7l.tar.gz`
3. Extract it into `piper/` at the project root so `piper/piper` is executable:

```bash
# From the FRIDAY project root, with the tarball you just downloaded:
mkdir -p piper
tar -xf piper_amd64.tar.gz -C piper --strip-components=1
chmod +x piper/piper
piper/piper --help    # quick smoke test
```

Expected layout:

```
piper/
├── piper          (executable, this is what FRIDAY calls)
├── espeak-ng-data/
├── libespeak-ng.so.1
├── libonnxruntime.so.*
└── libpiper_phonemize.so.*
```

### B) Download a voice model

A voice is one `.onnx` file plus its `.onnx.json` config. Both must live in `models/` and the filename must match what `modules/voice_io/tts.py` resolves (default: `en_US-lessac-medium.onnx`).

Browse the catalogue at <https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium> (or pick a different speaker/language under `en/`, `de/`, `fr/`, etc.).

For the default lessac/medium voice (~63 MB onnx + 5 KB json):

```bash
wget -O models/en_US-lessac-medium.onnx \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true"

wget -O models/en_US-lessac-medium.onnx.json \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true"
```

If you pick a different voice, also rebuild `modules/voice_io/tts.py`'s
`model_path` references — or just override via `FRIDAY_PIPER_VOICE_NAME`
if that env var is supported in your build.

### C) Smoke test

```bash
echo "Hello, this is Friday." | piper/piper \
    --model models/en_US-lessac-medium.onnx --output_raw \
    | aplay -r 22050 -f S16_LE -t raw -
```

You should hear FRIDAY speak. If `aplay` isn't available, try `pw-cat`:

```bash
echo "Hello, this is Friday." | piper/piper \
    --model models/en_US-lessac-medium.onnx --output_raw \
    | pw-cat --playback --raw --rate 22050 --format s16 --channels 1 -
```

If both fail, FRIDAY's own `sounddevice` fallback will still work at runtime — no further action needed for the smoke test.

---

## Starting FRIDAY

```bash
source .venv/bin/activate
python main.py            # Desktop HUD (PyQt6)
python main.py --text     # Text-only CLI
python main.py --verbose  # Show runtime logs in the terminal
```

To stop: close the HUD window, or hit Ctrl+C in the terminal. The shutdown handler flushes the memory queue and stops the wake-word detector if running.

---

## Troubleshooting

### Audio: "could not find an input device"

```bash
python tests/test_audio_devices.py
```

Lists all detected microphones. Pick a device ID and set it in `config.yaml`:

```yaml
voice:
  input_device:
    id: 3
    kind: pipewire
    label: "Your mic name"
```

### Screenshots fail on Wayland

FRIDAY's fallback chain (in `modules/system_control/screenshot.py`):
Mutter ScreenCast → xdg-desktop-portal → GNOME Shell D-Bus → gnome-screenshot → grim → spectacle → X11 tools → pyautogui.

If all paths fail, install the one matching your desktop:

```bash
sudo apt-get install gnome-screenshot          # GNOME
sudo apt-get install grim slurp                # sway / Hyprland
sudo apt-get install kde-spectacle             # KDE Plasma
```

### TTS is silent

```bash
ls -la piper/piper                              # must exist and be executable
ls -la models/en_US-lessac-medium.onnx*         # both files must exist
which pw-cat aplay                              # at least one must be present
```

If `piper/piper` is missing, redo [Manual: Piper TTS](#manual-piper-tts-required-for-voice-output).

### Re-run a specific phase

`./setup.sh` is idempotent — re-running only does the missing pieces. If you want to force a single step:

- **Re-download a specific model**: delete the file and re-run `setup.sh`.
- **Re-install pip deps**: delete `.venv/.requirements.sha256` and re-run.
- **Re-install Playwright**: delete `~/.cache/ms-playwright/chromium-*` and re-run.

### `.venv/bin/python3` is not executable

Your project folder is on a `noexec` mount. Move to `~/` or remount with `exec`.

---

## What's New (2026-05-14 refresh)

- **Idempotent setup script** — every phase skips itself when its output is already on disk.
- **Updated model list** — Qwen3 1.7B / 4B abliterated + SmolVLM2 2.2B (the actual models FRIDAY ships with), not the old Gemma 2B / Qwen2.5 7B.
- **Piper removed from automated setup** — manual install instructions documented here for full reproducibility.
- **Routing false-trigger guards & memory pipeline fixes** — see [docs/architecture.md §0](docs/architecture.md#0-latest-refresh-2026-05-14).
- **First-class Windows support** — see [SETUP_GUIDE_WINDOWS.md](SETUP_GUIDE_WINDOWS.md).
