#!/bin/bash

# Resolve the project root by going one directory up from where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC="$(dirname "$SCRIPT_DIR")"
DEST="$HOME/bin/second_brain"

echo "Deploying code from DEV to PRD..."

cp "$SRC/src/"*.py "$DEST/src/"

if [ -f "$SRC/dashboard.sh" ]; then
    cp "$SRC/dashboard.sh" "$DEST/"
fi

echo "Restarting Second Brain service..."
systemctl --user restart second_brain

if [ $? -eq 0 ]; then
    echo "Deployment successful."
else
    echo "Service restart failed. Check logs:"
    echo "journalctl --user -u second_brain -n 20"
fi