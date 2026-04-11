#!/bin/bash

# FRIDAY Project Setup Script for Linux

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting FRIDAY setup...${NC}"

# Check for Python 3
if ! command -v python3 &> /dev/null
then
    echo -e "${RED}Error: python3 could not be found. Please install Python 3.${NC}"
    exit 1
fi

# Create required directories
echo "Creating required directories..."
mkdir -p logs data models

# Check if .venv already exists
if [ -d ".venv" ]; then
    echo "Virtual environment .venv already exists. Skipping creation."
else
    echo "Creating virtual environment .venv..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to create virtual environment. Ensure 'python3-venv' is installed.${NC}"
        exit 1
    fi
fi

# Activate virtual environment and install dependencies
echo "Activating virtual environment..."
source .venv/bin/activate

echo "Updating pip..."
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install dependencies.${NC}"
        exit 1
    fi
else
    echo -e "${RED}Warning: requirements.txt not found. No dependencies installed.${NC}"
fi

echo -e "${GREEN}Setup complete!${NC}"
echo -e "To start the application:"
echo -e "  1. Activate the environment: ${GREEN}source .venv/bin/activate${NC}"
echo -e "  2. Run the application: ${GREEN}python main.py${NC}"
echo -e ""
echo -e "${RED}Note:${NC} Please ensure you have placed the necessary model files in the 'models/' directory."
echo -e "Required models:"
echo -e "  - gemma-2b-it.gguf"
echo -e "  - en_US-lessac-medium.onnx (and .json)"
