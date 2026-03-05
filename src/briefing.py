import os
import sys
import json
import asyncio
import datetime
import logging
import requests
from dotenv import load_dotenv
from google import genai
from telegram import Bot

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
load_dotenv(env_path)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_BOT_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not all([TELEGRAM_TOKEN, CHAT_ID, GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    logger.error("Missing required environment variables.")
    sys.exit(1)

config_path = os.path.join(BASE_DIR, "config.json")
try:
    with open(config_path, "r") as f:
        config = json.load(f)
        rag_model_name = config["llm_models"]["rag"]
except (FileNotFoundError, KeyError, json.JSONDecodeError):
    rag_model_name = "gemini-2.5-flash"

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'timeout': 60.0}
)

def get_open_items():
    """Fetches items with status 'New' from Supabase and filters by date."""
    url = f"{SUPABASE_URL}/rest/v1/thoughts?select=id,content,metadata&metadata->>status=eq.New"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        rows = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch from Supabase: {e}")
        return []

    today = datetime.date.today()
    limit_date = today + datetime.timedelta(days=7)
    
    filtered_rows = []
    for row in rows:
        meta = row.get("metadata", {})
        type_ = meta.get("type", "Idea")
        
        if type_ not in ["Task", "Project", "Admin"]:
            continue
            
        t_date_str = meta.get("target_date")
        include = False
        
        if not t_date_str:
            include = True
        else:
            try:
                t_date = datetime.date.fromisoformat(t_date_str)
                if t_date <= limit_date:
                    include = True
            except ValueError:
                include = True 
                
        if include:
            filtered_rows.append(row)
            
    return filtered_rows

def create_briefing_content(rows):
    if not rows:
        return "No active items in the Third Brain. All clear!"

    today_str = datetime.date.today().isoformat()
    
    data_list = []
    for row in rows:
        meta = row.get("metadata", {})
        t_date = meta.get("target_date")
        date_info = f"[Target: {t_date}]" if t_date else "[No Date]"
        type_ = meta.get("type", "Task")
        
        summary = row.get("content", "").split("\n")[0][:100]
        
        data_list.append(f"- {date_info} {type_}: {summary} (ID: {row['id']})")
    
    data_text = "\n".join(data_list)
    
    prompt = f"""
    You are an executive assistant. 
    TODAY IS: {today_str}
    
    Here are the user's active tasks (filtered to overdue, due this week, or backlog):
    
    {data_text}
    
    Generate a 'Morning Briefing' for Telegram.
    
    RULES:
    1. **Overdue Items:** If a target date is before {today_str}, flag it as 🚨 OVERDUE.
    2. **Priorities:** Pick the top 3 most important items (focus on Overdue or Due Today).
    3. **Grouping:** Group the rest logically (e.g., "📅 Coming Up", "📥 Backlog").
    4. **Style:** Punchy, motivational, use emojis. No markdown headers like '##'.
    """
    
    response = client.models.generate_content(
        model=rag_model_name,
        contents=prompt
    )
    return response.text

async def send_briefing():
    rows = get_open_items()
    
    if len(rows) > 0:
        message = create_briefing_content(rows)
    else:
        message = "🌅 Morning! Zero open loops for the week. Have a great day."

    bot = Bot(TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=CHAT_ID, 
        text=message, 
        read_timeout=30.0,
        connect_timeout=30.0
    )
    logger.info("Briefing sent.")

if __name__ == '__main__':
    logger.info(f"Starting Third Brain Briefing v{__version__} [{RUN_MODE}]...")
    asyncio.run(send_briefing())