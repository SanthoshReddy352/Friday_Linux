<#
.SYNOPSIS
    FRIDAY Project Setup Script — Windows (PowerShell 5.1+ or PowerShell 7+).

.DESCRIPTION
    Idempotent: every step checks whether its outcome already exists on disk
    and skips itself when so. Re-running is safe. Each model is downloaded
    only if missing or zero-byte; use -Force to redownload.

    This script does NOT install Piper TTS or the Piper voice model — see
    SETUP_GUIDE_WINDOWS.md for the manual Piper steps. Piper requires a
    voice + architecture choice we shouldn't make for you.

.PARAMETER SkipModels
    Skip all AI-model downloads.

.PARAMETER SkipPlaywright
    Skip the Playwright Chromium download.

.PARAMETER Force
    Re-download models even if they already exist on disk.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -SkipModels
    .\setup.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipPlaywright,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

function Write-Section { param([string]$Msg) Write-Host "`n$Msg" -ForegroundColor Yellow }
function Write-Skip { param([string]$Msg) Write-Host "  [skip] $Msg already present." -ForegroundColor Green }
function Write-Doing { param([string]$Msg) Write-Host "  [do]   $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "  [warn] $Msg" -ForegroundColor DarkYellow }
function Write-Err { param([string]$Msg) Write-Host "  [fail] $Msg" -ForegroundColor Red }

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "          FRIDAY - Local AI Assistant             " -ForegroundColor Green
Write-Host "             Installation Script (Windows)        " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Each step checks before doing work - re-running is safe." -ForegroundColor DarkGray

# --- 1. Python check ------------------------------------------------------
Write-Section "[1/5] Verifying Python interpreter..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Err "Python not found on PATH. Install Python 3.10-3.13 from https://python.org and re-run."
    exit 1
}
$pyVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "  Found Python $pyVersion at $($python.Source)" -ForegroundColor Green
if ($pyVersion -lt "3.10" -or $pyVersion -gt "3.13") {
    Write-Warn "Python $pyVersion is outside the tested range (3.10 - 3.13). Continuing anyway."
}

# --- 2. Virtual environment ----------------------------------------------
Write-Section "[2/5] Python virtual environment..."
$VenvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if ((Test-Path $VenvPy) -and -not $Force) {
    Write-Skip ".venv\Scripts\python.exe"
} else {
    if (Test-Path ".venv") {
        Write-Warn ".venv exists but is incomplete - recreating."
        Remove-Item .venv -Recurse -Force
    }
    Write-Doing "Creating .venv..."
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create venv."
        exit 1
    }
}

if (-not (Test-Path $VenvPy)) {
    Write-Err "Venv python interpreter missing at $VenvPy"
    exit 1
}

# --- 3. Python dependencies ---------------------------------------------
Write-Section "[3/5] Python dependencies..."
if (-not (Test-Path "requirements.txt")) {
    Write-Err "requirements.txt not found in $(Get-Location)."
    exit 1
}

# Hash requirements.txt; skip pip install if hash matches last successful run.
$ReqHash = (Get-FileHash -Algorithm SHA256 requirements.txt).Hash
$ReqStamp = ".venv\.requirements.sha256"
$NeedInstall = $true
if ((Test-Path $ReqStamp) -and -not $Force) {
    $prev = (Get-Content $ReqStamp -ErrorAction SilentlyContinue).Trim()
    if ($prev -eq $ReqHash) {
        Write-Skip "Python dependencies (requirements.txt unchanged since last install)"
        $NeedInstall = $false
    }
}
if ($NeedInstall) {
    Write-Doing "pip install -r requirements.txt"
    & $VenvPy -m pip install --upgrade pip setuptools wheel
    & $VenvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "pip install failed - inspect the log above and re-run."
        exit 1
    }
    Set-Content -Path $ReqStamp -Value $ReqHash
}

# --- 4. Playwright -------------------------------------------------------
Write-Section "[4/5] Playwright Chromium runtime..."
$playwrightCache = Join-Path $env:USERPROFILE "AppData\Local\ms-playwright"
$hasChromium = $false
if (Test-Path $playwrightCache) {
    if (Get-ChildItem -Path $playwrightCache -Filter "chromium-*" -Directory -ErrorAction SilentlyContinue) {
        $hasChromium = $true
    }
}
if ($SkipPlaywright) {
    Write-Host "  Skipped (-SkipPlaywright)." -ForegroundColor DarkGray
} elseif ($hasChromium -and -not $Force) {
    Write-Skip "Chromium for Playwright (in $playwrightCache)"
} else {
    Write-Doing "playwright install chromium"
    & $VenvPy -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Playwright install failed. Run '$VenvPy -m playwright install chromium' manually later."
    }
}

# --- 5. AI models --------------------------------------------------------
Write-Section "[5/5] Local AI models..."
New-Item -ItemType Directory -Force -Path logs, data, "data\chroma", models | Out-Null

function Download-IfMissing {
    param(
        [string]$Dest,
        [string]$Url,
        [string]$Label
    )
    if ((Test-Path $Dest) -and -not $Force -and ((Get-Item $Dest).Length -gt 0)) {
        Write-Skip "$Label ($(Split-Path $Dest -Leaf))"
        return
    }
    Write-Doing "Downloading $Label..."
    try {
        # Disabling the progress UI makes large model downloads ~10x faster.
        $oldPref = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $Dest
        $ProgressPreference = $oldPref
    } catch {
        Write-Warn "Failed to download $Url - $_"
        if (Test-Path $Dest) { Remove-Item $Dest -Force }
    }
}

if ($SkipModels) {
    Write-Host "  Skipped (-SkipModels)." -ForegroundColor DarkGray
} else {
    # Chat: Qwen3 1.7B abliterated GGUF (mlabonne)
    Download-IfMissing -Dest "models\mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf" `
        -Url "https://huggingface.co/mlabonne/Qwen3-1.7B-abliterated-GGUF/resolve/main/Qwen3-1.7B-abliterated.Q4_K_M.gguf?download=true" `
        -Label "Qwen3 1.7B chat model"

    # Tool: Qwen3 4B abliterated GGUF (mlabonne)
    Download-IfMissing -Dest "models\mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf" `
        -Url "https://huggingface.co/mlabonne/Qwen3-4B-abliterated-GGUF/resolve/main/Qwen3-4B-abliterated.Q4_K_M.gguf?download=true" `
        -Label "Qwen3 4B tool model"

    # Vision: SmolVLM2 2.2B Instruct GGUF + mmproj (ggml-org)
    Download-IfMissing -Dest "models\SmolVLM2-2.2B-Instruct-Q4_K_M.gguf" `
        -Url "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/SmolVLM2-2.2B-Instruct-Q4_K_M.gguf?download=true" `
        -Label "SmolVLM2 2.2B vision model"

    Download-IfMissing -Dest "models\mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf" `
        -Url "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF/resolve/main/mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf?download=true" `
        -Label "SmolVLM2 multimodal projector"

    # STT: faster-whisper base.en (HF cache)
    $whisperCache = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
    $hasWhisper = $false
    if (Test-Path $whisperCache) {
        if (Get-ChildItem -Path $whisperCache -Filter "models--Systran--faster-whisper-base*" -Directory -ErrorAction SilentlyContinue) {
            $hasWhisper = $true
        }
    }
    if ($hasWhisper -and -not $Force) {
        Write-Skip "Faster-Whisper base.en in HuggingFace cache"
    } elseif (Test-Path "scripts\download_stt_model.py") {
        Write-Doing "Downloading Faster-Whisper STT model..."
        & $VenvPy scripts\download_stt_model.py
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Whisper download failed - re-run scripts\download_stt_model.py later."
        }
    }
}

Write-Host ""
Write-Host "  Piper TTS engine and voice are NOT installed by this script." -ForegroundColor DarkGray
Write-Host "  See SETUP_GUIDE_WINDOWS.md -> 'Manual: Piper TTS' before first launch." -ForegroundColor DarkGray

# --- Optional autostart ----------------------------------------------
Write-Section "Optional: Porcupine wake-word autostart"
$startupBat = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\friday_wake.bat"
if (Test-Path $startupBat) {
    Write-Skip "Wake-word .bat already in Startup folder"
} elseif (Test-Path "modules\voice_io\register_wake.py") {
    $answer = Read-Host "  Register the wake-word service to start at login? [y/N]"
    if ($answer -match '^[Yy]') {
        if (-not $env:FRIDAY_PORCUPINE_KEY) {
            Write-Warn "FRIDAY_PORCUPINE_KEY env var is not set. The shortcut will be installed"
            Write-Warn "but the detector will refuse to start until you set it via"
            Write-Warn "System Properties -> Environment Variables. Get a key at https://console.picovoice.ai/"
        }
        & $VenvPy "modules\voice_io\register_wake.py"
    } else {
        Write-Host "  Skipped. Run '$VenvPy modules\voice_io\register_wake.py' later if you change your mind." -ForegroundColor DarkGray
    }
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "            Automated setup complete             " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Next steps before first launch:"
Write-Host "  1. Install Piper        - see SETUP_GUIDE_WINDOWS.md -> 'Manual: Piper TTS'"
Write-Host "  2. Download a voice     - choose any Piper voice ONNX + JSON pair"
Write-Host ""
Write-Host "Then to start FRIDAY:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python main.py            # Desktop HUD"
Write-Host "  python main.py --text     # Text CLI"
Write-Host "==================================================" -ForegroundColor Cyan
