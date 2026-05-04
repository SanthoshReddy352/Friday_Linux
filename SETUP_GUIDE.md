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

Clone the repository and run the automated setup script. This single script handles everything: virtual environment creation, system dependencies, Python libraries, and downloading all required AI models and binaries.

```bash
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
chmod +x setup.sh
./setup.sh
```

> [!TIP]
> If the setup script fails due to "noexec" mount permissions, try moving the project folder to your home directory (`~/`) or remounting your drive with execution permissions.

> [!NOTE]
> The setup script automatically downloads Piper TTS, Gemma 2B, Qwen 2.5 7B, and Faster Whisper models. This process may take a while depending on your internet connection.

---

## 🌐 Step 2: Browser Automation (Playwright)

FRIDAY uses Playwright for browser-based tasks (YouTube, web search). The setup script installs the Chromium binaries automatically. If you encounter any browser automation issues later, you can manually fix it by running:

```bash
source .venv/bin/activate
python3 -m playwright install --with-deps chromium
```

---

## 🏁 Step 3: Start FRIDAY

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

## 🧠 Appendix: Models Downloaded

For your reference, the `setup.sh` script automatically downloads the following models into the `models/` directory:

| Model Type | File Name | Download Link |
| :--- | :--- | :--- |
| **LLM (Chat)** | `gemma-2b-it.gguf` | [Gemma 2B IT GGUF](https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf?download=true) |
| **LLM (Tools)** | `qwen2.5-7b-instruct.gguf` | [Qwen2.5 7B GGUF](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf?download=true) |
| **TTS (Voice)** | `en_US-lessac-medium.onnx` | [Piper Voice Model](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true) |
| **TTS (Config)** | `en_US-lessac-medium.onnx.json` | [Piper Voice Config](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true) |

---

## 🛠️ Troubleshooting

### Audio Issues
- Ensure `libportaudio2` is installed: `sudo apt install libportaudio2`
- Check if your microphone is recognized: `python tests/test_audio_devices.py`

### Permission Denied
- If `setup.sh` won't run: `chmod +x setup.sh`

### Missing Modules
- Re-run the dependency sync: `pip install -r requirements.txt`
