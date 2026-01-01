#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Voice Dictation Installer ==="

# Check for python3-venv
if ! dpkg-query -W -f='${Status}' python3-venv 2>/dev/null | grep -q "install ok installed" && \
   ! dpkg-query -W -f='${Status}' python3.12-venv 2>/dev/null | grep -q "install ok installed"; then
    echo "Installing python3-venv..."
    sudo apt install -y python3-venv
fi

# Check for python3-dev (needed to build pynput/evdev)
if ! dpkg-query -W -f='${Status}' python3-dev 2>/dev/null | grep -q "install ok installed" && \
   ! dpkg-query -W -f='${Status}' python3.12-dev 2>/dev/null | grep -q "install ok installed"; then
    echo "Installing python3-dev..."
    sudo apt install -y python3-dev
fi

# Check for xdotool
if ! command -v xdotool &>/dev/null; then
    echo "Installing xdotool..."
    sudo apt install -y xdotool
fi

# Check for python3-gi (PyGObject for system tray)
if ! dpkg-query -W -f='${Status}' python3-gi 2>/dev/null | grep -q "install ok installed"; then
    echo "Installing python3-gi..."
    sudo apt install -y python3-gi gir1.2-ayatanaappindicator3-0.1
fi

# Create virtual environment (with system packages for gi access)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv --system-site-packages venv
elif ! grep -q "include-system-site-packages = true" venv/pyvenv.cfg 2>/dev/null; then
    echo "Recreating virtual environment with system packages..."
    rm -rf venv
    python3 -m venv --system-site-packages venv
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

# Install and start systemd user service
echo "Setting up systemd service..."
mkdir -p ~/.config/systemd/user
cp "$SCRIPT_DIR/dictate.service" ~/.config/systemd/user/

# Set up environment for systemctl --user if needed
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable dictate.service
    systemctl --user restart dictate.service
    echo "Service installed and started."
else
    echo "Note: Could not start service (no user session bus)."
    echo "The service will start automatically on next login,"
    echo "or run: systemctl --user enable --now dictate.service"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Service commands:"
echo "  systemctl --user status dictate   - Check status"
echo "  systemctl --user restart dictate  - Restart service"
echo "  systemctl --user stop dictate     - Stop service"
echo "  journalctl --user -u dictate -f   - View logs"
echo ""
echo "Controls:"
echo "  Hold Pause or backtick (\`) - Record"
echo "  Tap backtick               - Type backtick"
echo "  Double-tap backtick        - Undo last transcription"
