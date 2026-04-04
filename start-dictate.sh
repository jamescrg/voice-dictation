#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kill any stale dictate.py processes not managed by this service
# (e.g. orphans from a crash during audio device cleanup)
stale_pids=$(pgrep -f "python.*dictate\.py" 2>/dev/null)
if [ -n "$stale_pids" ]; then
    echo "Killing stale dictate process(es): $stale_pids"
    kill $stale_pids 2>/dev/null
    sleep 1
    kill -9 $stale_pids 2>/dev/null
fi

exec "$SCRIPT_DIR/venv/bin/python" -u "$SCRIPT_DIR/dictate.py"
