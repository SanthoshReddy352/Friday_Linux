#!/usr/bin/env bash
# FRIDAY Project Setup Script — Linux
# Idempotent: every step skips itself when its outcome already exists on disk.
# Tested on Ubuntu / Debian / Kali.
#
# This script does NOT install Piper TTS or the Piper voice model — see
# SETUP_GUIDE.md for the manual steps (they involve choosing an architecture
# and a voice, and we don't want to make that decision for you).

set -u
# Don't `set -e` — we want to print friendly errors and keep going past
# non-fatal failures (e.g. an optional package that doesn't exist on this distro).

# --- Colors ----------------------------------------------------------------
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; DIM='\033[2m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; DIM=''; NC=''
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "${SCRIPT_DIR}"

echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}          FRIDAY - Local AI Assistant            ${NC}"
echo -e "${GREEN}             Installation Script (Linux)         ${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${DIM}Each step checks before doing work — re-running is safe.${NC}"

# --- Helper: skip-aware status print --------------------------------------
already() { echo -e "  ${GREEN}[skip]${NC} $1 already present."; }
doing()   { echo -e "  ${CYAN}[do]${NC}   $1"; }
warn()    { echo -e "  ${YELLOW}[warn]${NC} $1"; }
fail()    { echo -e "  ${RED}[fail]${NC} $1"; }

# --- 1. System dependencies -----------------------------------------------
echo -e "\n${YELLOW}[1/6] Checking system dependencies...${NC}"
if [ -f /etc/os-release ] && grep -iq "ubuntu\|debian\|kali" /etc/os-release; then
    REQUIRED_PKGS=(
        libportaudio2 ffmpeg python3-venv python3-pip
        libxcb-cursor0 wget tar curl
    )
    OPTIONAL_PKGS=(
        wmctrl xdotool grim spectacle xfce4-screenshooter scrot maim
        x11-utils libnotify-bin libsndfile1
    )
    MISSING_PKGS=()
    for pkg in "${REQUIRED_PKGS[@]}" "${OPTIONAL_PKGS[@]}"; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            MISSING_PKGS+=("$pkg")
        fi
    done
    if [ ${#MISSING_PKGS[@]} -eq 0 ]; then
        already "all required and optional system packages"
    else
        warn "Missing: ${MISSING_PKGS[*]}"
        read -p "  Install them now (sudo required) [Y/n]? " -n 1 -r reply; echo
        if [[ -z "$reply" || "$reply" =~ ^[Yy]$ ]]; then
            sudo apt-get update
            sudo apt-get install -y "${MISSING_PKGS[@]}" || \
                warn "Some packages failed to install — continuing."
        else
            warn "Continuing without installing — some features may not work."
        fi
    fi
else
    warn "Non-Debian system. Install manually: libportaudio2 ffmpeg python3-venv python3-pip wget tar curl"
fi

# --- 2. Python venv -------------------------------------------------------
echo -e "\n${YELLOW}[2/6] Python virtual environment...${NC}"
if [ -d ".venv" ] && [ -x ".venv/bin/python3" ]; then
    already ".venv/bin/python3"
else
    if [ -d ".venv" ]; then
        warn ".venv exists but bin/python3 is missing or not executable — recreating."
        rm -rf .venv
    fi
    doing "Creating .venv..."
    python3 -m venv .venv || { fail "venv creation failed (is python3-venv installed?)"; exit 1; }
fi

if [ ! -x ".venv/bin/python3" ]; then
    fail ".venv/bin/python3 is not executable."
    fail "  This usually means the project is on a 'noexec' mount (NTFS, exFAT)."
    fail "  Move the project to your home directory or remount with 'exec'."
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
VENV_PY="${SCRIPT_DIR}/.venv/bin/python3"

# --- 3. Python deps -------------------------------------------------------
echo -e "\n${YELLOW}[3/6] Python dependencies...${NC}"
if [ ! -f "requirements.txt" ]; then
    fail "requirements.txt not found in $(pwd)."
    exit 1
fi

# Cheap heuristic: hash requirements.txt and skip if the hash is already
# recorded as installed by a prior successful run.
REQ_HASH=$(sha256sum requirements.txt | awk '{print $1}')
REQ_STAMP=".venv/.requirements.sha256"
if [ -f "$REQ_STAMP" ] && [ "$(cat "$REQ_STAMP")" = "$REQ_HASH" ]; then
    already "Python dependencies (requirements.txt unchanged since last install)"
else
    doing "pip install -r requirements.txt"
    "$VENV_PY" -m pip install --upgrade pip setuptools wheel
    if "$VENV_PY" -m pip install -r requirements.txt; then
        echo "$REQ_HASH" > "$REQ_STAMP"
    else
        fail "pip install failed — inspect the log above and re-run."
        exit 1
    fi
fi

# --- 4. Playwright Chromium ----------------------------------------------
echo -e "\n${YELLOW}[4/6] Playwright Chromium runtime...${NC}"
# Playwright caches browsers under ~/.cache/ms-playwright/chromium-<rev>/
if compgen -G "${HOME}/.cache/ms-playwright/chromium-*" > /dev/null; then
    already "Chromium for Playwright (in ~/.cache/ms-playwright)"
else
    doing "playwright install chromium"
    if ! "$VENV_PY" -m playwright install chromium; then
        warn "Playwright install failed. Run '$VENV_PY -m playwright install chromium' later."
    fi
fi

# --- 5. AI models --------------------------------------------------------
echo -e "\n${YELLOW}[5/6] Local AI models...${NC}"
mkdir -p logs data data/chroma models

# Idempotent downloader: skip if target exists and is non-empty.
download_if_missing() {
    local dest="$1"; local url="$2"; local label="$3"
    if [ -f "$dest" ] && [ -s "$dest" ]; then
        already "$label ($(basename "$dest"))"
        return 0
    fi
    doing "Downloading $label..."
    if ! wget --progress=bar:force -O "$dest" "$url"; then
        fail "Download failed: $url"
        rm -f "$dest"
        return 1
    fi
}

# Chat: Qwen3 1.7B abliterated GGUF (mlabonne)
download_if_missing models/mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf \
    "https://huggingface.co/mlabonne/Qwen3-1.7B-abliterated-GGUF/resolve/main/Qwen3-1.7B-abliterated.Q4_K_M.gguf?download=true" \
    "Qwen3 1.7B chat model"

# Tool: Qwen3 4B abliterated GGUF (mlabonne) — also doubles as the Mem0 extraction model
download_if_missing models/mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf \
    "https://huggingface.co/mlabonne/Qwen3-4B-abliterated-GGUF/resolve/main/Qwen3-4B-abliterated.Q4_K_M.gguf?download=true" \
    "Qwen3 4B tool model"

# Vision: SmolVLM2 2.2B Instruct GGUF + mmproj (ggml-org)
download_if_missing models/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf \
    "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf?download=true" \
    "SmolVLM2 2.2B vision model"

download_if_missing models/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf \
    "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf?download=true" \
    "SmolVLM2 multimodal projector"

# STT: faster-whisper base.en (downloaded into HF cache via Python script)
WHISPER_MARKER="${HOME}/.cache/huggingface/hub/models--Systran--faster-whisper-base.en"
if [ -d "$WHISPER_MARKER" ] || ls "${HOME}/.cache/huggingface/hub" 2>/dev/null | grep -q "faster-whisper-base"; then
    already "Faster-Whisper base.en in HuggingFace cache"
elif [ -f scripts/download_stt_model.py ]; then
    doing "Downloading Faster-Whisper STT model..."
    "$VENV_PY" scripts/download_stt_model.py || \
        warn "Whisper model download failed — re-run scripts/download_stt_model.py later."
fi

echo
echo -e "  ${DIM}Piper TTS engine and voice are NOT installed by this script.${NC}"
echo -e "  ${DIM}See SETUP_GUIDE.md → 'Manual: Piper TTS' before first launch.${NC}"

# --- 6. Optional autostart -----------------------------------------------
echo -e "\n${YELLOW}[6/6] Optional: Porcupine wake-word autostart (systemd --user)${NC}"
if [ -f "$HOME/.config/systemd/user/friday-wake.service" ]; then
    already "friday-wake.service (systemd --user)"
elif [ -f "modules/voice_io/register_wake.py" ]; then
    read -p "  Register the wake-word service to autostart at login? [y/N]: " -n 1 -r reply; echo
    if [[ "$reply" =~ ^[Yy]$ ]]; then
        if [ -z "${FRIDAY_PORCUPINE_KEY:-}" ]; then
            warn "FRIDAY_PORCUPINE_KEY is not set. The service will install but won't start"
            warn "until you set the env var. Get a free key at https://console.picovoice.ai/"
        fi
        "$VENV_PY" modules/voice_io/register_wake.py || \
            warn "Autostart registration failed — see output above."
    else
        echo -e "  ${DIM}Skipped. Run 'python modules/voice_io/register_wake.py' later if you change your mind.${NC}"
    fi
else
    warn "modules/voice_io/register_wake.py not found — wake autostart unavailable."
fi

echo
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}            Automated setup complete             ${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "Next steps before first launch:"
echo -e "  1. ${CYAN}Install Piper${NC}        — see ${BLUE}SETUP_GUIDE.md → 'Manual: Piper TTS'${NC}"
echo -e "  2. ${CYAN}Download a voice${NC}     — choose any Piper voice ONNX + JSON pair"
echo -e ""
echo -e "Then to start FRIDAY:"
echo -e "  ${CYAN}source .venv/bin/activate${NC}"
echo -e "  ${CYAN}python main.py${NC}              # Desktop HUD"
echo -e "  ${CYAN}python main.py --text${NC}       # Text CLI"
echo -e "${BLUE}==================================================${NC}"
