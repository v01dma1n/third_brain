import os
import sys
import json
import logging
import requests
import telebot
import google.generativeai as genai
from dotenv import load_dotenv

__version__ = "1.0.0"

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if "projects/" in BASE_DIR:
    RUN_MODE = "DEV 🔧"
    env_filename = ".third_brain_dev.env"
else:
    RUN_MODE = "PROD 🚀"
    env_filename = ".third_brain.env"

env_path = os.path.expanduser(f"~/{env_filename}")
logger.info(f"Loading {RUN_MODE} config from: {env_path}")
load_dotenv(env_path)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not all([TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY]):
    logger.error("Missing required environment variables.")
    sys.exit(1)

config_path = os.path.join(BASE_DIR, "..", "config.json")
try:
    with open(config_path, "r") as f:
        config = json.load(f)
        rag_model_name = config["llm_models"]["rag"]
        classification_model_name = config["llm_models"]["classification"]
except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
    logger.error(f"Failed to load models from config.json: {e}")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_embedding(text: str) -> list:
    url = "https://openrouter.ai/api/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/text-embedding-3-small",
        "input": text
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Embedding generation failed: {e}")
        return []

def search_thoughts(query_text: str) -> dict:
    """Searches the database for thoughts matching the query text semantically."""
    embedding = get_embedding(query_text)
    if not embedding:
        return {"error": "Failed to generate vector embedding for search."}

    url = f"{SUPABASE_URL}/rest/v1/rpc/match_thoughts"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {"query_embedding": embedding, "match_count": 5}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"search_thoughts failed: {e}")
        return {"error": str(e)}

def list_thoughts(limit: int = 5) -> dict:
    """Retrieves the most recent thoughts saved in the database."""
    url = f"{SUPABASE_URL}/rest/v1/thoughts?select=content,metadata&order=created_at.desc&limit={limit}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"list_thoughts failed: {e}")
        return {"error": str(e)}

agent_model = genai.GenerativeModel(
    model_name=rag_model_name,
    tools=[search_thoughts, list_thoughts],
    system_instruction="You are the Third Brain retrieval agent. Use your tools to query the Supabase database to answer user questions. Summarize the returned JSON data clearly."
)

router_model = genai.GenerativeModel(model_name=classification_model_name)

def route_intent(text: str) -> str:
    prompt = f"Classify the following message as 'INGESTION' (storing a fact, idea, or task) or 'RETRIEVAL' (asking a question or requesting a search). Message: '{text}'"
    response = router_model.generate_content(prompt)
    return response.text.strip().upper()

def extract_metadata(text: str) -> dict:
    prompt = f"""Extract metadata for the following text. 
    Return ONLY a valid JSON object with this exact schema:
    {{"type": "Task|Project|Idea", "domain": "Work|Home", "topics": ["tag1", "tag2"]}}
    Text: {text}"""
    try:
        response = router_model.generate_content(prompt)
        cleaned_text = response.text.strip().strip('```json').strip('```').strip()
        return json.loads(cleaned_text)
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return {"type": "Idea", "domain": "Home", "topics": []}

def ingest_thought(text: str) -> str:
    metadata = extract_metadata(text)
    embedding = get_embedding(text)
    
    if not embedding:
        return "Failed to generate embedding. Thought not saved."
        
    url = f"{SUPABASE_URL}/rest/v1/thoughts"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    payload = {
        "content": text,
        "metadata": metadata,
        "embedding": embedding
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return f"Saved successfully. Domain: {metadata.get('domain')}, Type: {metadata.get('type')}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Database insertion failed: {e}")
        return "Database insertion failed."

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text
    intent = route_intent(text)
    
    if "INGESTION" in intent:
        logger.info("Routing to Ingestion pipeline.")
        bot.reply_to(message, "Processing ingestion...")
        result = ingest_thought(text)
        bot.reply_to(message, result)
    else:
        logger.info("Routing to Retrieval pipeline.")
        try:
            chat = agent_model.start_chat(enable_automatic_function_calling=True)
            response = chat.send_message(text)
            bot.reply_to(message, response.text)
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            bot.reply_to(message, "Failed to retrieve information.")

if __name__ == "__main__":
    logger.info(f"Starting Third Brain Telegram Agent v{__version__} [{RUN_MODE}]...")
    bot.infinity_polling()