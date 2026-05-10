import os
import sys
import json
import logging
import datetime
import requests
from dotenv import load_dotenv
from google import genai

__version__ = "1.0.0"

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, "..", "config.json")
FACTS_DIR = os.path.join(BASE_DIR, "..", "facts")
INFERRED_FACTS_PATH = os.path.join(FACTS_DIR, "inferred_facts.md")

try:
    with open(config_path, "r") as f:
        config = json.load(f)
        app_env = config.get("environment", "PROD").upper()
        classification_model_name = config["llm_models"]["classification"]
except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
    logger.error(f"Failed to load config.json: {e}")
    sys.exit(1)

env_filename = ".third_brain_dev.env" if app_env == "DEV" else ".third_brain.env"
load_dotenv(os.path.expanduser(f"~/{env_filename}"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not all([GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    logger.error("Missing required environment variables.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)


def fetch_recent_thoughts() -> list[str]:
    cutoff = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    url = f"{SUPABASE_URL}/rest/v1/thoughts"
    params = {
        "select": "content",
        "created_at": f"gte.{cutoff}",
        "metadata->>status": "not.in.(Cancelled,Done)",
        "order": "created_at.desc",
        "limit": "500",
    }
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return [row["content"] for row in resp.json() if row.get("content")]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch thoughts: {e}")
        return []


def load_existing_inferred() -> tuple[str, list[str]]:
    try:
        with open(INFERRED_FACTS_PATH, "r") as f:
            raw = f.read().strip()
    except FileNotFoundError:
        return "", []

    facts = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("- "):
            facts.append(line[2:])
    return raw, facts


def infer_new_facts(thoughts: list[str], existing_raw: str) -> list[dict]:
    thoughts_text = "\n".join(f"- {t}" for t in thoughts)
    existing_block = existing_raw if existing_raw else "(none yet)"

    prompt = f"""You are analyzing a personal knowledge base to extract stable facts about its owner.

Below is a list of captured thoughts (tasks, projects, ideas, admin items).

Extract stable, reusable facts about this person — their work, life context, \
recurring themes, preferences, and domain expertise.

Rules:
- Only extract facts that appear repeatedly or are clearly stable
- Facts must be generalizations, not specific tasks
- Ignore one-off events
- Do not contradict facts already established (provided below)
- Return JSON only, no preamble, no markdown

Existing inferred facts (do not duplicate):
{existing_block}

Thoughts:
{thoughts_text}

Return:
{{
  "facts": [
    {{
      "content": "fact in plain language",
      "confidence": 0.0-1.0
    }}
  ]
}}"""

    try:
        response = client.models.generate_content(
            model=classification_model_name,
            contents=prompt,
        )
        cleaned = response.text.strip().strip("```json").strip("```").strip()
        return json.loads(cleaned).get("facts", [])
    except Exception as e:
        logger.error(f"Fact inference failed: {e}")
        return []


def write_inferred_facts(existing_facts: list[str], new_facts: list[dict]) -> int:
    existing_keys = set()
    for f in existing_facts:
        existing_keys.add(f.split(" (confidence:")[0].strip().lower())

    all_fact_lines = list(existing_facts)
    added = 0
    for fact in new_facts:
        content = fact.get("content", "").strip()
        confidence = fact.get("confidence", 0)
        if confidence >= 0.7 and content and content.lower() not in existing_keys:
            all_fact_lines.append(f"{content} (confidence: {confidence:.1f})")
            existing_keys.add(content.lower())
            added += 1

    now = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Personal Facts — Inferred",
        f"# Last updated: {now}",
        "",
    ] + [f"- {line}" for line in all_fact_lines]

    with open(INFERRED_FACTS_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    logger.info(f"Wrote {len(all_fact_lines)} facts ({added} new) to {INFERRED_FACTS_PATH}")
    return added


if __name__ == "__main__":
    logger.info(f"Starting fact inference v{__version__}...")

    thoughts = fetch_recent_thoughts()
    logger.info(f"Fetched {len(thoughts)} thoughts from last 90 days.")

    if not thoughts:
        logger.info("No thoughts to analyze. Exiting.")
        sys.exit(0)

    existing_raw, existing_facts = load_existing_inferred()
    logger.info(f"Found {len(existing_facts)} existing inferred facts.")

    new_facts = infer_new_facts(thoughts, existing_raw)
    logger.info(f"Gemini returned {len(new_facts)} candidate facts.")

    added = write_inferred_facts(existing_facts, new_facts)
    logger.info(f"Done. {added} new facts added.")
