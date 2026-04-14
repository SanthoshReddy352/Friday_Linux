# 🛡️ FRIDAY Setup Guide

Welcome to the **FRIDAY** project! This guide will help you install and configure your local AI assistant from scratch.

---

## 🚀 Quick Start (Ubuntu/Debian)

If you have Python 3 and Git installed, run:

```bash
git clone https://github.com/SanthoshReddy352/FRIDAY.git && cd FRIDAY
chmod +x setup.sh
./setup.sh
```

---

## 📋 Prerequisites

- **OS:** Linux (Ubuntu/Debian strongly recommended).
- **Python:** 3.10 to 3.13.
- **Hardware:** 8GB+ RAM recommended (for running local models).
- **Internet:** Required for initial setup and downloading models.

---

## 📦 Step 1: Clone & Automate

Clone the repository and run the automated setup script. This script handles virtual environment creation, system dependencies, and Python libraries.

```bash
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
chmod +x setup.sh
./setup.sh
```

> [!TIP]
> If the setup script fails due to "noexec" mount permissions, try moving the project folder to your home directory (`~/`) or remounting your drive with execution permissions.

---

## 🧠 Step 2: Download AI Models

FRIDAY runs entirely locally. You need to download the following models and place them in the `models/` directory.

| Model Type | File Name | Download Link |
| :--- | :--- | :--- |
| **LLM (Chat)** | `gemma-2b-it.gguf` | [Gemma 2B IT GGUF](https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf?download=true) |
| **LLM (Tools)** | `qwen2.5-7b-instruct.gguf` | [Qwen2.5 7B GGUF](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf?download=true) |
| **TTS (Voice)** | `en_US-lessac-medium.onnx` | [Piper Voice Model](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true) |
| **TTS (Config)** | `en_US-lessac-medium.onnx.json` | [Piper Voice Config](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true) |

> [!IMPORTANT]
> Ensure the files are named **exactly** as shown above or update your `config.yaml` to match.

---

## 🔊 Step 3: Setup Piper Voice Engine

To enable FRIDAY to speak, you need the Piper binary engine:

1.  **Download** the Linux AMD64 binary: [piper_amd64.tar.gz](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz)
2.  **Create** a folder named `piper` in the project root.
3.  **Extract** the contents into that folder.
4.  **Verify**: You should have a file at `piper/piper`.

---

## 🌐 Step 4: Browser Automation

FRIDAY uses Playwright for browser-based tasks (YouTube, web search). The setup script installs the Chromium binaries automatically, but if you encounter issues, run:

```bash
source .venv/bin/activate
python3 -m playwright install --with-deps chromium
```

---

## 🏁 Step 5: Start FRIDAY

Once everything is ready, launch the assistant:

```bash
source .venv/bin/activate
python main.py
```

To run in **Text-Only CLI mode**:
```bash
python main.py --text
```

---

## 🛠️ Troubleshooting

### Audio Issues
- Ensure `libportaudio2` is installed: `sudo apt install libportaudio2`
- Check if your microphone is recognized: `python tests/test_audio_devices.py`

### Permission Denied
- If `setup.sh` or `piper/piper` won't run: `chmod +x setup.sh piper/piper`

### Missing Modules
- Re-run the dependency sync: `pip install -r requirements.txt`
