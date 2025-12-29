#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Voice Dictation Installer ==="

# Check for python3-venv
if ! dpkg -l python3-venv &>/dev/null && ! dpkg -l python3.12-venv &>/dev/null; then
    echo "Installing python3-venv..."
    sudo apt install -y python3-venv
fi

# Check for xdotool
if ! command -v xdotool &>/dev/null; then
    echo "Installing xdotool..."
    sudo apt install -y xdotool
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Install dependencies
echo "Installing Python dependencies..."
./venv/bin/pip install -q groq sounddevice numpy pynput

# Check for .env
if [ ! -f ".env" ]; then
    echo ""
    echo "IMPORTANT: Copy .env.example to .env and add your Groq API key:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    echo "Get your API key at: https://console.groq.com/keys"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Usage:"
echo "  ./start-dictate.sh    - Run dictation"
echo ""
echo "Controls:"
echo "  Hold Pause or backtick (\`) - Record"
echo "  Tap backtick               - Type backtick"
echo "  Double-tap backtick        - Undo last transcription"
