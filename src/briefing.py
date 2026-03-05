import os
import sys
import sqlite3
import asyncio
import datetime
import logging
from dotenv import load_dotenv
from google import genai
from telegram import Bot

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "..", "db", "brain.db")

if "projects/local" in BASE_DIR:
    env_filename = ".second_brain_dev.env"
else:
    env_filename = ".second_brain.env"
load_dotenv(os.path.expanduser(f"~/{env_filename}"))

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
CHAT_ID = os.environ.get("TELEGRAM_BOT_CHAT_ID") 

if not CHAT_ID:
    logger.error("TELEGRAM_BOT_CHAT_ID is missing in .env")
    exit(1)

# --- 1. Fetch Open Loops ---
def get_open_items():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Logic:
    # 1. Status is 'New'
    # 2. Date is NULL (Backlog) OR Date is <= Today + 7 Days
    # 3. Sort by Date ASC (Overdue first), then ID
    c.execute('''
        SELECT id, type, summary, target_date 
        FROM entries 
        WHERE status = 'New' 
        AND (target_date IS NULL OR target_date <= date('now', '+7 days', 'localtime'))
        ORDER BY 
            CASE WHEN target_date IS NULL THEN 1 ELSE 0 END, 
            target_date ASC, 
            id DESC
        LIMIT 50
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

# --- 2. Generate Briefing ---
def create_briefing_content(rows):
    if not rows:
        return "No active items in the Second Brain. All clear!"

    client = genai.Client(api_key=GEMINI_KEY)
    
    # Get Today's Date for the AI context
    today_str = datetime.date.today().isoformat()
    
    # Format data for the LLM
    data_list = []
    for row in rows:
        date_info = f"[Target: {row['target_date']}]" if row['target_date'] else "[No Date]"
        data_list.append(f"- {date_info} {row['type']}: {row['summary']} (ID: {row['id']})")
    
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
        model="gemini-3-flash-preview",
        contents=prompt
    )
    return response.text

# --- 3. Send to Telegram ---
async def send_briefing():
    rows = get_open_items()
    
    # Only run AI if there is actual data
    if len(rows) > 0:
        message = create_briefing_content(rows)
    else:
        message = "🌅 Morning! Zero open loops for the week. Have a great day."

    bot = Bot(BOT_TOKEN)
    await bot.send_message(
        chat_id=CHAT_ID, 
        text=message, 
        read_timeout=30.0,
        connect_timeout=30.0)
    logger.info("Briefing sent.")

if __name__ == '__main__':
    if not BOT_TOKEN or not GEMINI_KEY:
        logger.error("Env vars missing.")
        exit(1)
        
    asyncio.run(send_briefing())