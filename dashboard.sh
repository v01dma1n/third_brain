#!/bin/bash

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR" || exit

echo "🧠 Launching Third Brain Dashboard"
echo "📂 Context: $PROJECT_DIR"

if [ -f ".python-version" ] && command -v pyenv >/dev/null; then
    echo "✅ Detected pyenv config (.python-version)"
    exec pyenv exec streamlit run src/dashboard.py
elif [[ -n "$VIRTUAL_ENV" ]]; then
    echo "✅ Using active environment: $(basename "$VIRTUAL_ENV")"
    exec streamlit run src/dashboard.py
else
    echo "⚠️ No specific environment found. Attempting with pyenv ml-env..."
    exec /home/voidmain/.pyenv/versions/ml-env/bin/streamlit run src/dashboard.py
fi
