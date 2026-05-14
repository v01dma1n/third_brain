#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC="$(dirname "$SCRIPT_DIR")"
REMOTE="tao14"
REMOTE_DEST="$REMOTE:~/bin/third_brain"
REMOTE_PYTHON="~/.pyenv/versions/ml-env/bin/python"

echo "Deploying src/ to $REMOTE..."

rsync -av "$SRC/src/" "$REMOTE_DEST/src/"

echo "Restarting Third Brain service on $REMOTE..."
ssh "$REMOTE" "systemctl --user restart third_brain"

if [ $? -eq 0 ]; then
    echo "Deployment successful."
else
    echo "Service restart failed. Check logs on $REMOTE:"
    echo "  ssh $REMOTE 'journalctl --user -u third_brain -n 20'"
fi
