#!/bin/bash

# 1. Get the directory where THIS script is currently located
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR" || exit

echo "🧠 Launching Second Brain Dashboard"
echo "📂 Context: $PROJECT_DIR"

# STRATEGY 1: Check for pyenv configuration (.python-version)
# If this file exists, we let pyenv handle the version/env automatically.
if [ -f ".python-version" ] && command -v pyenv >/dev/null; then
    echo "✅ Detected pyenv config (.python-version)"
    exec pyenv exec streamlit run src/dashboard.py

# STRATEGY 2: Check if ANY virtual environment is already active
# This works if you manually ran 'pyenv activate <id>' before running the script.
elif [[ -n "$VIRTUAL_ENV" ]]; then
    echo "✅ Using active environment: $(basename "$VIRTUAL_ENV")"
    exec streamlit run src/dashboard.py

# STRATEGY 3: Check for a local 'ml-env' folder (Legacy/Venv)
elif [ -f "ml-env/bin/activate" ]; then
    echo "🔌 Activating local ml-env..."
    source ml-env/bin/activate
    exec streamlit run src/dashboard.py

# STRATEGY 4: Fallback
else
    echo "⚠️ No specific environment found. Attempting to run with system python..."
    exec streamlit run src/dashboard.py
fi