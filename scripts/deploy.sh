#!/bin/bash

# Resolve the project root by going one directory up from where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC="$(dirname "$SCRIPT_DIR")"
DEST="$HOME/bin/third_brain"

echo "Deploying code from DEV to PRD..."

mkdir -p "$DEST/src"

cp "$SRC/src/"*.py "$DEST/src/"

if [ -f "$SRC/config.json" ]; then
    cp "$SRC/config.json" "$DEST/"
fi

echo "Restarting Third Brain service..."
systemctl --user restart third_brain

if [ $? -eq 0 ]; then
    echo "Deployment successful."
else
    echo "Service restart failed. Check logs:"
    echo "journalctl --user -u third_brain -n 20"
fi