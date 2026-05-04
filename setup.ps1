<#
.SYNOPSIS
    FRIDAY Project Setup Script for Windows
.DESCRIPTION
    This script automates the setup of the FRIDAY AI Assistant on Windows.
#>

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "          FRIDAY - Advanced AI Assistant          " -ForegroundColor Green
Write-Host "               Installation Script (Windows)      " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Virtual Environment Setup
Write-Host "`n[1/5] Setting up Python virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "Virtual environment .venv already exists. Skipping creation."
} else {
    Write-Host "Creating virtual environment .venv..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

# 2. Python Dependency Installation
Write-Host "`n[2/5] Installing Python dependencies..." -ForegroundColor Yellow
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
if (Test-Path "requirements.txt") {
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to install Python dependencies." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Error: requirements.txt not found!" -ForegroundColor Red
    exit 1
}

# 3. Browser Automation Setup
Write-Host "`n[3/5] Setting up Browser Automation (Playwright)..." -ForegroundColor Yellow
& ".\.venv\Scripts\python.exe" -m playwright install chromium

# 4. Model and Binary Downloads
Write-Host "`n[4/5] Downloading AI Models and Binaries..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path logs, data, models | Out-Null

Write-Host "Downloading Models (this may take a while depending on your internet connection)...`n"

# 1. Gemma 2B IT GGUF
if (-Not (Test-Path "models\gemma-2b-it.gguf")) {
    Write-Host "Downloading Gemma 2B IT..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf?download=true" -OutFile "models\gemma-2b-it.gguf"
} else {
    Write-Host "Gemma 2B IT already exists."
}

# 2. Qwen2.5 7B Instruct GGUF
if (-Not (Test-Path "models\qwen2.5-7b-instruct.gguf")) {
    Write-Host "Downloading Qwen2.5 7B Instruct..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf?download=true" -OutFile "models\qwen2.5-7b-instruct.gguf"
} else {
    Write-Host "Qwen2.5 7B Instruct already exists."
}

# 3. Faster Whisper Model
Write-Host "Downloading Faster Whisper Model..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" scripts\download_stt_model.py

# 5. Snap-to-Start Integration
Write-Host "`n[5/5] Configuring Snap-to-Start (Autostart)..." -ForegroundColor Yellow
if (Test-Path "modules\voice_io\register_autostart.py") {
    & ".\.venv\Scripts\python.exe" modules\voice_io\register_autostart.py
} else {
    Write-Host "Warning: Autostart registration script not found." -ForegroundColor Red
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "            Setup Complete Successfully!           " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "To start FRIDAY:"
Write-Host "  1. .\.venv\Scripts\activate"
Write-Host "  2. python main.py"
Write-Host "`nNote: Models have been automatically downloaded to the models\ directory." -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Cyan
