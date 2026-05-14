# FRIDAY Setup Guide — Windows

This guide walks you through installing FRIDAY on Windows 10 / Windows 11 **two ways**:

1. **[Automated path](#automated-path-recommended)** — run `setup.ps1`. Idempotent, skips any step whose output already exists.
2. **[Fully manual path](#fully-manual-path)** — every step typed out, no scripts.

Either way, **Piper TTS is always installed manually** — see [Manual: Piper TTS](#manual-piper-tts-required-for-voice-output) near the end.

For Linux, see [SETUP_GUIDE.md](SETUP_GUIDE.md).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **OS** | Windows 10 21H2+ or Windows 11 |
| **Python** | 3.10 – 3.13 from <https://python.org> with "Add to PATH" ticked |
| **PowerShell** | 5.1 (built-in) or 7+ |
| **Git** | <https://git-scm.com/download/win> |
| **RAM** | 8 GB minimum, 16 GB recommended |
| **Disk** | ~10 GB free for models + cache |
| **Build tools** | Most wheels are prebuilt for Windows. Only install **Visual C++ Build Tools 2022** from <https://visualstudio.microsoft.com/visual-cpp-build-tools/> if `pip install` complains about a missing compiler. |
| **Audio** | Default Windows audio stack works (WASAPI through `sounddevice`) |

---

## Automated path (recommended)

Open **PowerShell** in the FRIDAY folder:

```powershell
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
# One-time: allow scripts to run in this shell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

Available flags:

| Flag | Purpose |
|---|---|
| `-SkipModels` | Don't download any model files |
| `-SkipPlaywright` | Don't install Chromium for Playwright |
| `-Force` | Re-download/re-install everything even if already present |

Each phase checks before doing work:

| Phase | What it checks | What it skips when present |
|---|---|---|
| 1. Python | `python` on PATH, version 3.10–3.13 | Phase as a whole |
| 2. Venv | `.venv\Scripts\python.exe` exists | Venv re-creation |
| 3. Pip deps | SHA-256 of `requirements.txt` vs `.venv\.requirements.sha256` | Full `pip install` |
| 4. Playwright | `%LOCALAPPDATA%\ms-playwright\chromium-*` exists | Browser download |
| 5. Models | Each `models\<file>.gguf` exists and is non-empty | Per-file download |
| 6. Wake autostart | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\friday_wake.bat` exists | Re-registration |

After `setup.ps1` completes, jump to **[Manual: Piper TTS](#manual-piper-tts-required-for-voice-output)** and then **[Starting FRIDAY](#starting-friday)**.

---

## Fully manual path

### Step 1 — Install prerequisites

1. **Python 3.10–3.13** from <https://python.org/downloads/windows/>.
   During the installer, **tick "Add python.exe to PATH"**.
2. **Git for Windows** from <https://git-scm.com/download/win>.
3. Open a fresh PowerShell window and verify:

```powershell
python --version            # 3.10.x .. 3.13.x
git --version
```

### Step 2 — Clone the repository

```powershell
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
```

### Step 3 — Allow PowerShell scripts (one-time)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This only affects the current shell. To allow signed scripts permanently for your user account:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Step 4 — Create the virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Verify
.\.venv\Scripts\python.exe --version
```

### Step 5 — Install Python dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Expect ~3 GB of downloads on a fresh install. If pip complains about a missing C++ compiler, install **Visual C++ Build Tools 2022** (tick the "Desktop development with C++" workload) and re-run.

### Step 6 — Install the Playwright Chromium runtime

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Skip if you don't plan to use browser-automation tools.

### Step 7 — Download AI models

```powershell
New-Item -ItemType Directory -Force -Path logs, data, "data\chroma", models | Out-Null
```

Then download each file. The fastest path on PowerShell is `Invoke-WebRequest` with the progress UI **disabled** — leaving it on makes large files crawl:

```powershell
$ProgressPreference = 'SilentlyContinue'   # 10x speedup for big downloads

# Chat — Qwen3 1.7B abliterated (~1.1 GB)
Invoke-WebRequest -Uri "https://huggingface.co/mlabonne/Qwen3-1.7B-abliterated-GGUF/resolve/main/Qwen3-1.7B-abliterated.Q4_K_M.gguf?download=true" `
    -OutFile "models\mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf"

# Tool / Mem0 extraction — Qwen3 4B abliterated (~2.5 GB)
Invoke-WebRequest -Uri "https://huggingface.co/mlabonne/Qwen3-4B-abliterated-GGUF/resolve/main/Qwen3-4B-abliterated.Q4_K_M.gguf?download=true" `
    -OutFile "models\mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf"

# Vision — SmolVLM2 2.2B Instruct (~1.1 GB)
Invoke-WebRequest -Uri "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf?download=true" `
    -OutFile "models\SmolVLM2-2.2B-Instruct-Q4_K_M.gguf"

# Vision multimodal projector (~600 MB)
Invoke-WebRequest -Uri "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf?download=true" `
    -OutFile "models\mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf"
```

The local filenames must match what `config.yaml` references under `models.chat.path`, `models.tool.path`, `vision.model_path`, and `vision.mmproj_path`.

### Step 8 — Download the Faster-Whisper STT model

```powershell
.\.venv\Scripts\python.exe scripts\download_stt_model.py
```

This pulls `Systran/faster-whisper-base.en` (~145 MB) into `%USERPROFILE%\.cache\huggingface\hub\`.

### Step 9 — Manual: Piper TTS (required for voice output)

See [Manual: Piper TTS](#manual-piper-tts-required-for-voice-output) below.

### Step 10 — (Optional) Register the wake-word service

```powershell
# 1. Get a free Picovoice access key:
#    https://console.picovoice.ai/
#
# 2. Set as a USER env var (not just the session):
#    - Press Win+R, type sysdm.cpl, hit Enter
#    - Advanced tab -> Environment Variables
#    - User variables -> New
#      Name:  FRIDAY_PORCUPINE_KEY
#      Value: <your-key>
#    - OK, then open a FRESH PowerShell window
#
# 3. Verify the var is visible:
$env:FRIDAY_PORCUPINE_KEY

# 4. Register the .bat shortcut in the Startup folder:
.\.venv\Scripts\python.exe modules\voice_io\register_wake.py

# 5. Confirm:
Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\friday_wake.bat"
```

> Optional: if you have a Windows-specific Porcupine keyword `.ppn` from Picovoice, save it as `modules\voice_io\Wake-up-Friday_en_windows_v4_0_0.ppn`. The detector auto-prefers it; otherwise it falls back to the Linux-flagged `.ppn` shipped in the repo (which still works on Windows).

### Step 11 — (Optional) Enable Mem0 long-term memory

Edit `config.yaml` and flip:

```yaml
memory:
  enabled: true   # was false
```

FRIDAY will boot a local llama.cpp extraction server on port 8181 (using the Qwen3 4B model from Step 7) on the next launch. User facts start surfacing in chat prompts as "What you know about the user".

---

## Manual: Piper TTS (required for voice output)

FRIDAY uses Piper for offline voice output. The setup script does not install Piper because the choice of architecture and voice depends on your hardware and preference.

### A) Download the Piper engine binary

1. Open <https://github.com/rhasspy/piper/releases>
2. Download `piper_windows_amd64.zip` (under the latest release's Assets).
3. From PowerShell, extract it into the `piper\` folder at the project root:

```powershell
# From the FRIDAY project root, assuming the zip is in your Downloads:
$src = "$env:USERPROFILE\Downloads\piper_windows_amd64.zip"
Expand-Archive -Path $src -DestinationPath piper -Force

# Some Piper zips nest everything under a piper\ subfolder. Flatten if so:
$nested = Join-Path (Get-Location) "piper\piper"
if (Test-Path $nested) {
    Get-ChildItem $nested -Force | Move-Item -Destination (Join-Path (Get-Location) "piper") -Force
    Remove-Item $nested -Recurse -Force
}

# Smoke test
.\piper\piper.exe --help | Select-Object -First 5
```

Expected layout:

```
piper\
├── piper.exe          (executable, this is what FRIDAY calls)
├── espeak-ng-data\
├── onnxruntime.dll
└── piper_phonemize.dll
```

### B) Download a voice model

A voice is one `.onnx` file plus its `.onnx.json` config. Both must live in `models\` and the filename must match `modules\voice_io\tts.py`'s default: `en_US-lessac-medium.onnx`.

Browse <https://huggingface.co/rhasspy/piper-voices/tree/main> to pick a voice; the default lessac/medium English voice is:

```powershell
$ProgressPreference = 'SilentlyContinue'

Invoke-WebRequest `
    -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true" `
    -OutFile "models\en_US-lessac-medium.onnx"

Invoke-WebRequest `
    -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true" `
    -OutFile "models\en_US-lessac-medium.onnx.json"
```

### C) Smoke test

```powershell
"Hello, this is Friday." | .\piper\piper.exe `
    --model models\en_US-lessac-medium.onnx --output_raw `
    | .\.venv\Scripts\python.exe -c "import sys, sounddevice as sd; s=sd.RawOutputStream(samplerate=22050, channels=1, dtype='int16'); s.start(); [s.write(c) for c in iter(lambda: sys.stdin.buffer.read(4096), b'')]; s.stop(); s.close()"
```

You should hear FRIDAY speak. If you get no sound, check Windows volume mixer and the default playback device, then try the same command again — `sounddevice` will pick up whatever WASAPI defaults to.

---

## Starting FRIDAY

```powershell
.\.venv\Scripts\Activate.ps1
python main.py            # Desktop HUD (PyQt6)
python main.py --text     # Text-only CLI
python main.py --verbose  # With runtime logs visible
```

To stop: focus the HUD and close it, or Ctrl+C in the terminal.

---

## Windows-Specific Notes

### Audio devices

```powershell
python -c "import sounddevice; print(sounddevice.query_devices())"
```

Pick an input device ID and set it in `config.yaml`:

```yaml
voice:
  input_device:
    id: 3
    kind: wasapi
    label: "Realtek Audio"
```

### App-launch coverage

The launcher resolves binaries via `where` (Windows PATH + PATHEXT). Bundled registry covers:

- **Browsers**: Chrome, Edge, Brave, Chromium, Firefox
- **System**: File Explorer (`explorer.exe`), Windows Terminal (`wt.exe`), PowerShell, cmd.exe, Calculator (`calc.exe`), Notepad
- **Media**: VLC, mpv

For anything else, ensure it's on `PATH` or invoke with the full path:

```
> open "C:\Program Files\Slack\slack.exe"
```

### Screenshots

The Windows path uses `pyautogui` directly. Screenshots land in `%USERPROFILE%\Pictures\FRIDAY_Screenshots\`.

### Window manipulation

`wmctrl` / `xdotool` are Linux-only; browser automation on Windows launches windows but doesn't auto-position them. If you need that, install `pywinauto` and file a feature request.

---

## Troubleshooting

### "running scripts is disabled on this system"

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

(Per-shell. For a user-scope persistent setting use `-Scope CurrentUser -ExecutionPolicy RemoteSigned`.)

### `pip install` fails — "Microsoft Visual C++ 14.0 is required"

A dependency tried to build a wheel from source. Install **Visual C++ Build Tools 2022** from <https://visualstudio.microsoft.com/visual-cpp-build-tools/>, tick the "Desktop development with C++" workload, then re-run `setup.ps1` (or Step 5 of the manual path).

### Long-path errors during pip install

Some transitive deps create paths longer than 260 characters. Enable long paths once:

```powershell
# Run as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
    -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Sign out and back in for the change to take effect.

### Wake-word service not starting at login

- Confirm the `.bat` exists: `Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\friday_wake.bat"`
- Verify `FRIDAY_PORCUPINE_KEY` is a **User** env var (not just session): in a fresh shell run `$env:FRIDAY_PORCUPINE_KEY`
- Check `logs\wake_detector.log` for errors

### Piper exits immediately with a DLL error

The Windows Piper zip relies on `onnxruntime.dll` and Visual C++ 2015–2022 runtimes. Install both:

- Latest VC++ Redistributable: <https://aka.ms/vs/17/release/vc_redist.x64.exe>
- Confirm `piper\onnxruntime.dll` exists — re-extract the zip if missing.

---

## What's New (2026-05-14 refresh)

- **First-class Windows support**: app launcher, autostart, subprocess flags, and wake-word detector all handle Windows paths and process semantics.
- **Idempotent setup script** with `-SkipModels`, `-SkipPlaywright`, `-Force` flags.
- **Updated model list** — Qwen3 1.7B / 4B abliterated + SmolVLM2 2.2B, not the old Gemma 2B / Qwen2.5 7B.
- **Piper removed from automated setup** — manual install instructions documented here.
- Subprocess calls everywhere now use `encoding="utf-8", errors="replace"`, so non-ASCII output from Windows tools never crashes the parser.

For the architecture details, see [docs/architecture.md](docs/architecture.md).
