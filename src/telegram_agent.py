import os
import sys
import json
import logging
import requests
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

__version__ = "1.1.0"

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

client = genai.Client(api_key=GEMINI_API_KEY)

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
    url = f"{SUPABASE_URL}/rest/v1/thoughts?select=id,content,metadata&order=created_at.desc&limit={limit}"
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

def update_thought(thought_id: str, new_status: str) -> dict:
    """Updates the status (e.g., 'Done', 'New', 'Review') of a specific thought by its ID."""
    get_url = f"{SUPABASE_URL}/rest/v1/thoughts?id=eq.{thought_id}&select=metadata"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        resp = requests.get(get_url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {"error": f"ID {thought_id} not found."}
            
        metadata = data[0].get("metadata", {})
        metadata["status"] = new_status
        
        patch_url = f"{SUPABASE_URL}/rest/v1/thoughts?id=eq.{thought_id}"
        patch_headers = {**headers, "Content-Type": "application/json"}
        patch_resp = requests.patch(patch_url, headers=patch_headers, json={"metadata": metadata}, timeout=10)
        patch_resp.raise_for_status()
        
        return {"success": True, "message": f"Thought {thought_id} marked as {new_status}."}
    except requests.exceptions.RequestException as e:
        logger.error(f"update_thought failed: {e}")
        return {"error": str(e)}

system_instruction = """
You are the Third Brain retrieval agent. 
Use your tools to query the Supabase database to answer user questions.
If a user asks to mark a task as done or update a status, use the update_thought.
Always summarize returned JSON data clearly.
"""

agent_config = types.GenerateContentConfig(
    system_instruction=system_instruction,
    tools=[search_thoughts, list_thoughts, update_thought],
)

def extract_metadata(text: str) -> dict:
    prompt = f"""Extract metadata for the following text.
    Return ONLY a valid JSON object with this exact schema:
    {{"type": "Task|Project|Idea", "domain": "Work|Home", "topics": ["tag1", "tag2"], 
    "status": "New", "target_date": "YYYY-MM-DD or null"}}
    Text: {text}"""
    try:
        response = client.models.generate_content(model=classification_model_name, contents=prompt)
        cleaned_text = response.text.strip().strip('```json').strip('```').strip()
        data = json.loads(cleaned_text)
        if "status" not in data:
            data["status"] = "New"
        return data
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return {"type": "Idea", "domain": "Home", "topics": [], "status": "New"}

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = msg.text or ""
    file_path = None
    uploaded_file = None

    if msg.voice:
        file = await context.bot.get_file(msg.voice.file_id)
        file_path = os.path.join(BASE_DIR, "voice_note.ogg")
        await file.download_to_drive(file_path)
        
        uploaded_file = await asyncio.to_thread(client.files.upload, file=file_path)

        transcription_resp = await asyncio.to_thread(
            client.models.generate_content,
            model=classification_model_name,
            contents=["Transcribe this audio exactly as spoken.", uploaded_file]
        )
        text = transcription_resp.text.strip()
        logger.info(f"Transcribed voice: {text}")

    prompt = f"""Classify the following message as 'INGESTION' (storing a fact, idea, or task) 
              or 'RETRIEVAL' (asking a question, requesting a search, or updating a task status). 
              Message: '{text}'"""
    route_resp = await asyncio.to_thread(client.models.generate_content, model=classification_model_name, contents=prompt)
    intent = route_resp.text.strip().upper()
    
    if "INGESTION" in intent:
        logger.info("Routing to Ingestion pipeline.")
        await msg.reply_text("Processing ingestion...")
        result = await asyncio.to_thread(ingest_thought, text)
        await msg.reply_text(result)
    else:
        logger.info("Routing to Retrieval pipeline.")
        try:
            chat = client.chats.create(model=rag_model_name, config=agent_config)
            response = await asyncio.to_thread(chat.send_message, text)
            await msg.reply_text(response.text)
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            await msg.reply_text("Failed to retrieve or update information.")

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

if __name__ == "__main__":
    logger.info(f"Starting Third Brain Telegram Agent v{__version__} [{RUN_MODE}]...")
    
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )
    
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    app.run_polling()