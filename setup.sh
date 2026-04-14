#!/bin/bash

# FRIDAY Project Setup Script for Linux
# Optimized for Ubuntu/Debian based systems

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}          FRIDAY - Advanced AI Assistant          ${NC}"
echo -e "${GREEN}               Installation Script                ${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. System Dependency Check
echo -e "\n${YELLOW}[1/5] Checking system dependencies...${NC}"
if [ -f /etc/os-release ]; then
    if grep -iq "ubuntu\|debian" /etc/os-release; then
        echo -e "Detected Debian/Ubuntu-based system. Checking required packages..."
        MISSING_PKGS=()
        for pkg in libportaudio2 ffmpeg wmctrl xdotool python3-venv python3-pip libxcb-cursor0; do
            if ! dpkg -s $pkg >/dev/null 2>&1; then
                MISSING_PKGS+=($pkg)
            fi
        done

        if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
            echo -e "${YELLOW}The following system packages are missing: ${MISSING_PKGS[*]}${NC}"
            read -p "Would you like to install them now? (sudo access required) [Y/n]: " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                sudo apt-get update
                sudo apt-get install -y "${MISSING_PKGS[@]}"
            else
                echo -e "${RED}Warning: Some features may not work without these packages.${NC}"
            fi
        else
            echo -e "${GREEN}All system packages are already installed.${NC}"
        fi
    else
        echo -e "${YELLOW}Non-Debian system detected. Please manually ensure you have: libportaudio2, ffmpeg, wmctrl, xdotool.${NC}"
    fi
fi

# 2. Virtual Environment Setup
echo -e "\n${YELLOW}[2/5] Setting up Python virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo "Virtual environment .venv already exists. Skipping creation."
else
    echo "Creating virtual environment .venv..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to create virtual environment.${NC}"
        exit 1
    fi
fi

# Activate virtual environment
source .venv/bin/activate

# Check for execution permissions (common issue on NFTS/dual-boot)
if ! [ -x ".venv/bin/python3" ]; then
    echo -e "${RED}Error: Virtual environment binaries are not executable.${NC}"
    echo -e "This usually happens on drives mounted with 'noexec' (e.g., some NTFS mounts)."
    echo -e "Try remounting the drive with 'exec' permissions or moving the project to your home directory.${NC}"
    exit 1
fi

# 3. Python Dependency Installation
echo -e "\n${YELLOW}[3/5] Installing Python dependencies...${NC}"
python3 -m pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    python3 -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install Python dependencies.${NC}"
        exit 1
    fi
else
    echo -e "${RED}Error: requirements.txt not found!${NC}"
    exit 1
fi

# 4. Browser Automation Setup
echo -e "\n${YELLOW}[4/5] Setting up Browser Automation (Playwright)...${NC}"
python3 -m playwright install chromium
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Warning: Playwright browser installation failed. You may need to run 'playwright install chromium' manually later.${NC}"
fi

# 5. Final Configuration & Permissions
echo -e "\n${YELLOW}[5/5] Finalizing setup...${NC}"
mkdir -p logs data models

# Fix permissions for Piper if it exists
if [ -f "piper/piper" ]; then
    echo "Setting execution permissions for Piper binary..."
    chmod +x piper/piper
fi

echo -e "\n${BLUE}==================================================${NC}"
echo -e "${GREEN}            Setup Complete Successfully!           ${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "To start FRIDAY:"
echo -e "  1. ${CYAN}source .venv/bin/activate${NC}"
echo -e "  2. ${CYAN}python main.py${NC}"
echo -e ""
echo -e "${YELLOW}Note:${NC} Don't forget to place your model files in the ${BLUE}models/${NC} directory."
echo -e "See ${GREEN}SETUP_GUIDE.md${NC} for details on where to download models."
echo -e "${BLUE}==================================================${NC}"
