import os
import sys
import time
import json
import logging
import requests
import asyncio
import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

__version__ = "1.6.0"

HISTORY_MAX_TURNS = 10   # keep last N user+model pairs (20 Content objects)
HISTORY_TTL_SECONDS = 3600  # clear idle sessions after 1 hour

conversation_histories: dict[int, list] = {}
conversation_last_active: dict[int, float] = {}

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, "..", "config.json")

try:
    with open(config_path, "r") as f:
        config = json.load(f)
        app_env = config.get("environment", "PROD").upper()
        rag_model_name = config["llm_models"]["rag"]
        classification_model_name = config["llm_models"]["classification"]
        domain_config = config.get("domains", {"Work": [], "Home": []})
except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
    logger.error(f"Failed to load config.json: {e}")
    sys.exit(1)

if app_env == "DEV":
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
    embedding = get_embedding(query_text)
    if not embedding:
        return {"error": "Failed to generate vector embedding for search."}

    url = f"{SUPABASE_URL}/rest/v1/rpc/query_thoughts"
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

def list_thoughts(limit: int = 12, status: str = None) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/thoughts?select=id,content,metadata&order=created_at.desc&limit={limit}"
    
    if status:
        url += f"&metadata->>status=eq.{status}"
        
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

def update_thought(thought_id: str, new_status: str = None, new_target_date: str = None) -> dict:
    """Update status and/or target_date of a thought. new_target_date must be YYYY-MM-DD or null."""
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
        updated_fields = []

        if new_status is not None:
            metadata["status"] = new_status
            updated_fields.append(f"status → {new_status}")
        if new_target_date is not None:
            metadata["target_date"] = new_target_date
            updated_fields.append(f"target_date → {new_target_date}")

        if not updated_fields:
            return {"error": "No fields to update. Provide new_status and/or new_target_date."}

        patch_url = f"{SUPABASE_URL}/rest/v1/thoughts?id=eq.{thought_id}"
        patch_headers = {**headers, "Content-Type": "application/json"}
        patch_resp = requests.patch(patch_url, headers=patch_headers, json={"metadata": metadata}, timeout=10)
        patch_resp.raise_for_status()

        return {"success": True, "message": f"Updated: {', '.join(updated_fields)}."}
    except requests.exceptions.RequestException as e:
        logger.error(f"update_thought failed: {e}")
        return {"error": str(e)}

AGENT_TOOLS = [search_thoughts, list_thoughts, update_thought]

def build_agent_config() -> types.GenerateContentConfig:
    today = datetime.date.today().isoformat()
    system_instruction = f"""
You are the Third Brain retrieval agent.
Use your tools to query the Supabase database to answer user questions.
TODAY IS: {today}

UPDATING TASKS:
- To update status or target_date, first find the exact database ID via search_thoughts or list_thoughts, then call update_thought.
- update_thought accepts new_status (e.g. 'Done', 'New', 'Review') and/or new_target_date (YYYY-MM-DD format).
- If the user says "last task" or "most recent", use list_thoughts(limit=1) to find it.
- Convert natural language dates (e.g. "next Monday", "end of month") to YYYY-MM-DD before calling update_thought.

LISTING TASKS:
- Default to showing only status 'New' unless the user asks for done, all, or review items.

GENERAL:
- Do not include UUIDs in responses unless explicitly requested.
"""
    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=AGENT_TOOLS,
    )

def extract_metadata(text: str) -> dict:
    today = datetime.date.today()
    next_week = today + datetime.timedelta(days=7)
    
    domain_keys = "|".join(domain_config.keys())
    domain_rules = "\n    ".join([f"- Map items mentioning {', '.join(keywords)} to '{domain}'." for domain, keywords in domain_config.items() if keywords])
    
    prompt = f"""Extract metadata for the following text.
    TODAY IS: {today.isoformat()}
    
    Return ONLY a valid JSON object with this exact schema:
    {{"type": "Task|Project|Admin|Idea", "domain": "{domain_keys}", "topics": ["tag1", "tag2"], "status": "New", "target_date": "YYYY-MM-DD or null"}}
    
    RULES:
    - Extract any explicitly mentioned target dates in YYYY-MM-DD format.
    - If the type is 'Task' and NO target date is explicitly mentioned, set 'target_date' to exactly one week from today: {next_week.isoformat()}.
    - Domain Routing Rules:
        {domain_rules}
    
    Text: {text}"""
    
    try:
        response = client.models.generate_content(
            model=classification_model_name, 
            contents=prompt
        )
        cleaned_text = response.text.strip().strip('```json').strip('```').strip()
        data = json.loads(cleaned_text)
        if "status" not in data:
            data["status"] = "New"
        return data
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return {"type": "Idea", "domain": "Home", "topics": [], "status": "New"}

def ingest_thought(text: str, status: str = "New") -> str:
    metadata = extract_metadata(text)
    metadata["status"] = status
    
    composite_text = f"Domain: {metadata.get('domain')}. Type: {metadata.get('type')}. Content: {text}"
    embedding = get_embedding(composite_text)
    
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
    chat_id = update.effective_chat.id
    text = msg.text or ""
    file_path = None
    uploaded_file = None

    now = time.time()
    if chat_id in conversation_last_active and now - conversation_last_active[chat_id] > HISTORY_TTL_SECONDS:
        conversation_histories.pop(chat_id, None)
        logger.info(f"Cleared stale conversation history for chat {chat_id}")
    conversation_last_active[chat_id] = now

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

    prompt = f"Classify the following message as 'INGESTION' (storing a fact, idea, or task) or 'RETRIEVAL' (asking a question, requesting a search, or updating a task status). Message: '{text}'"
    route_resp = await asyncio.to_thread(
        client.models.generate_content, 
        model=classification_model_name, 
        contents=prompt
    )
    intent = route_resp.text.strip().upper()
    
    if "INGESTION" in intent:
        logger.info("Routing to Ingestion pipeline.")
        
        bouncer_prompt = f"""Evaluate if the following text is a concrete task, actionable idea, or valuable technical fact (e.g., related to {', '.join(domain_config.keys())}).
        Return ONLY a valid JSON object with this exact schema:
        {{"action": "ACCEPT" | "REJECT", "confidence": <integer 0-100>, "reason": "Brief explanation if rejected or uncertain, empty string if clearly accepted"}}

        RULES:
        - REJECT vague statements, conversational filler, or clear typos.
        - ACCEPT concrete tasks, ideas, facts, or projects.
        - confidence: how certain you are this is worth capturing (0=clearly invalid, 100=clearly valuable).

        Text: {text}"""

        status = "New"
        try:
            bouncer_resp = await asyncio.to_thread(
                client.models.generate_content,
                model=classification_model_name,
                contents=bouncer_prompt
            )
            cleaned_bouncer = bouncer_resp.text.strip().strip('```json').strip('```').strip()
            bouncer_data = json.loads(cleaned_bouncer)

            if bouncer_data.get("action") == "REJECT":
                logger.info(f"Bouncer rejected input: {bouncer_data.get('reason')}")
                await msg.reply_text(f"Rejected: {bouncer_data.get('reason')}")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                return

            confidence = bouncer_data.get("confidence", 100)
            if confidence < 60:
                status = "Review"
                logger.info(f"Bouncer flagged for review (confidence={confidence}): {bouncer_data.get('reason')}")
        except Exception as e:
            logger.error(f"Bouncer evaluation failed: {e}")

        await msg.reply_text("Processing ingestion...")
        result = await asyncio.to_thread(ingest_thought, text, status)
        if status == "Review":
            await msg.reply_text(f"Saved to Review queue (low confidence). {result}")
        else:
            await msg.reply_text(result)
    else:
        logger.info("Routing to Retrieval pipeline.")
        try:
            history = conversation_histories.get(chat_id, [])
            chat = client.chats.create(model=rag_model_name, config=build_agent_config(), history=history)
            response = await asyncio.to_thread(chat.send_message, message=text)
            await msg.reply_text(response.text)
            conversation_histories[chat_id] = list(chat.history)[-(HISTORY_MAX_TURNS * 2):]
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            await msg.reply_text("Failed to retrieve or update information.")

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Agent encountered an error: {context.error}")
    if update and hasattr(update, "effective_message") and update.effective_message:
        try:
            await update.effective_message.reply_text("Temporary network or API failure. Please try again.")
        except Exception:
            pass

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
    app.add_error_handler(error_handler)
    
    app.run_polling()