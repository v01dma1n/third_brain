import os
from dotenv import load_dotenv
from google import genai

# --- Config & Smart Environment Loading ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if "projects/local" in BASE_DIR:
    RUN_MODE = "DEV 🔧"
    env_filename = ".second_brain_dev.env"
else:
    RUN_MODE = "PROD 🚀"
    env_filename = ".second_brain.env"

env_path = os.path.expanduser(f"~/{env_filename}")
print(f"Loading {RUN_MODE} config from: {env_path}")
load_dotenv(env_path)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_KEY:
    print("Set your GEMINI_API_KEY first.")
else:
    client = genai.Client(api_key=GEMINI_KEY)
    
    print("Available Models:")
    # The new SDK returns a simpler object. 
    # Most models returned by .list() support generation.
    try:
        for m in client.models.list():
            # Filter for common Gemini models to avoid clutter
            if "gemini" in m.name:
                print(f"- {m.name} ({m.display_name})")
    except Exception as e:
        print(f"Error listing models: {e}")
