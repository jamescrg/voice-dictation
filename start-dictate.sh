#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prevent duplicate instances
if pidof -x "$(basename "$0")" -o $$ >/dev/null 2>&1 || pgrep -f "python.*dictate\.py" >/dev/null 2>&1; then
    echo "Voice dictation is already running."
    exit 0
fi

exec "$SCRIPT_DIR/venv/bin/python" -u "$SCRIPT_DIR/dictate.py"
