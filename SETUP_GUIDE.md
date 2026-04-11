# FRIDAY Setup Guide

This guide will walk you through the process of setting up FRIDAY on a new Linux machine.

## Prerequisites

- **OS:** Linux (Ubuntu/Debian recommended)
- **Python:** 3.10 or higher
- **Git**
- **System Dependencies:**
  ```bash
  sudo apt-get update
  sudo apt-get install -y python3-venv python3-pip libxcb-cursor0 libportaudio2
  ```

## 1. Clone the Repository

```bash
git clone https://github.com/SanthoshReddy352/FRIDAY.git
cd FRIDAY
```

## 2. Automatic Environment Setup

Run the included setup script to create the virtual environment and install Python dependencies:

```bash
chmod +x setup.sh
./setup.sh
```

## 3. Download Model Files

You need to manually download the following models and place them in the `models/` directory.

### A. Large Language Model (Gemma 2B)
- **File:** `gemma-2-2b-it-Q4_K_M.gguf`
- **Link:** [Download from Hugging Face](https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf?download=true)
- **Destination:** `models/gemma-2b-it.gguf` (Rename if necessary)

### B. Text-to-Speech Voice (Piper)
Download both the ONNX model and the config file:
- **ONNX Model:** [en_US-lessac-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true)
- **Config File:** [en_US-lessac-medium.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true)
- **Destination:** `models/`

### C. Speech-to-Text (Vosk)
- **Link:** [vosk-model-small-en-us-0.15.zip](https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip)
- **Destination:** Extract inside `models/` and rename folder to `vosk-model-small`.

## 4. Download Piper Engine

The Piper engine binaries are required for voice output.
- **Link:** [piper_amd64.tar.gz (for Linux x86_64)](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz)
- **Steps:**
  1. Create a `piper` directory: `mkdir -p piper`
  2. Download and extract the archive into the `piper` directory.
  3. Ensure the structure looks like: `piper/piper`, `piper/libespeak-ng.so`, etc.

## 5. Running FRIDAY

Once all models and binaries are in place:

```bash
source .venv/bin/activate
python main.py
```

## Troubleshooting

- **Audio issues:** Ensure `libportaudio2` is installed.
- **Permission denied:** Ensure `setup.sh` and the `piper/piper` binary have execution permissions (`chmod +x`).
- **Missing Models:** Double-check that files are named exactly as expected by the code or update `config.yaml`.
