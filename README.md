# FRIDAY - AI Desktop Assistant

FRIDAY is a powerful, local-first AI desktop assistant with voice interaction, intent recognition, and system control capabilities.

## Features

- **Voice I/O:** Local STT (Faster-Whisper/Vosk) and TTS (Piper).
- **LLM Powered:** Uses Gemma 2B for intelligent command processing and chat.
- **System Control:** Manage applications, media playback, and get system info.
- **Privacy First:** Designed to run entirely on your local machine.

## Quick Start

1. **Clone the repo:**
   ```bash
   git clone https://github.com/SanthoshReddy352/FRIDAY.git
   cd FRIDAY
   ```

2. **Run Setup:**
   Follow the [Complete Setup Guide](SETUP_GUIDE.md) to install dependencies and download the necessary models.

3. **Start FRIDAY:**
   ```bash
   source .venv/bin/activate
   python main.py
   ```
   This now launches the terminal-first FRIDAY CLI. To open the older desktop window instead, run:
   ```bash
   python main.py --gui
   ```

## Documentation

- [Setup Guide](SETUP_GUIDE.md) - Detailed installation and model download instructions.
- [Project Structure](docs/structure.md) - (Coming soon) Overview of the codebase.

## License

This project is licensed under the MIT License.
