import os
import sys
import json
import asyncio
import smtplib
import datetime
import logging
import requests
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google import genai
from telegram import Bot
from facts import load_facts

__version__ = "1.1.0"

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, "..", "config.json")

try:
    with open(config_path, "r") as f:
        config = json.load(f)
        app_env = config.get("environment", "PROD").upper()
        rag_model_name = config["llm_models"]["rag"]
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
CHAT_ID = os.environ.get("TELEGRAM_BOT_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
GMAIL_SENDER = os.environ.get("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
WORK_EMAIL = os.environ.get("WORK_EMAIL")
HOME_EMAIL = os.environ.get("HOME_EMAIL")

if not all([TELEGRAM_TOKEN, CHAT_ID, GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    logger.error("Missing required environment variables.")
    sys.exit(1)

email_enabled = all([GMAIL_SENDER, GMAIL_APP_PASSWORD, WORK_EMAIL, HOME_EMAIL])
if not email_enabled:
    logger.warning("Email env vars missing — email briefings disabled.")

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'timeout': None}
)

def get_open_items():
    today = datetime.date.today()
    limit_date_str = (today + datetime.timedelta(days=7)).isoformat()

    url = f"{SUPABASE_URL}/rest/v1/thoughts"
    params = {
        "select": "seq_id,content,metadata",
        "metadata->>status": "eq.New",
        "metadata->>type": "in.(Task,Project,Admin)",
        "or": f"(metadata->>target_date.is.null,metadata->>target_date.lte.{limit_date_str})"
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch from Supabase: {e}")
        return []

async def create_briefing_content(rows: list, domain_label: str = "all") -> str:
    if not rows:
        return ""

    today = datetime.date.today()
    today_str = today.isoformat()
    next_week_str = (today + datetime.timedelta(days=7)).isoformat()

    data_list = []
    for row in rows:
        meta = row.get("metadata", {})
        type_ = meta.get("type", "Task")
        t_date = meta.get("target_date")
        if type_ == "Task" and not t_date:
            t_date = next_week_str
        date_info = f"[Target: {t_date}]" if t_date else "[No Date]"
        summary = row.get("content", "").split("\n")[0][:100]
        seq_id = row.get("seq_id")
        seq_tag = f"[#{seq_id}] " if seq_id else ""
        data_list.append(f"- {seq_tag}{date_info} {type_}: {summary}")

    domain_context = f"({domain_label} tasks)" if domain_label != "all" else "(all tasks)"
    data_text = "\n".join(data_list)

    facts_context = load_facts()
    facts_section = (facts_context + "\n\n") if facts_context else ""

    prompt = f"""
    {facts_section}You are an executive assistant.
    TODAY IS: {today_str}

    Here are the user's active tasks {domain_context} filtered to overdue, due this week, or backlog:

    {data_text}

    Generate a 'Morning Briefing' for {'email' if domain_label != 'all' else 'Telegram'}.

    RULES:
    1. **Overdue Items:** If a target date is before {today_str}, flag it as 🚨 OVERDUE.
    2. **Priorities:** Pick the top 3 most important items (focus on Overdue or Due Today).
    3. **Grouping:** Group the rest logically (e.g., "📅 Coming Up", "📥 Backlog").
    4. **Style:** Punchy, motivational, use emojis. No markdown headers like '##'.
    5. **Item IDs:** Every item must include its #N identifier (e.g. #7) so the user can reference it later.
    """

    response = await client.aio.models.generate_content(
        model=rag_model_name,
        contents=prompt
    )
    return response.text

def send_email(to_addr: str, subject: str, body: str):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"ThirdBrain <{GMAIL_SENDER}>"
    msg["To"] = to_addr
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent to {to_addr}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_addr}: {e}")

async def send_briefing():
    all_rows = await asyncio.to_thread(get_open_items)

    work_rows = [r for r in all_rows if r.get("metadata", {}).get("domain") == "Work"]
    home_rows = [r for r in all_rows if r.get("metadata", {}).get("domain") == "Home"]

    # Telegram — combined
    if all_rows:
        telegram_msg = await create_briefing_content(all_rows, domain_label="all")
    else:
        telegram_msg = "🌅 Morning! Zero open loops for the week. Have a great day."

    bot = Bot(TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=CHAT_ID,
        text=telegram_msg,
        read_timeout=30.0,
        connect_timeout=30.0
    )
    logger.info("Telegram briefing sent.")

    # Emails — domain-split
    if email_enabled:
        today_str = datetime.date.today().strftime("%b %d")

        if work_rows:
            work_body = await create_briefing_content(work_rows, domain_label="Work")
            await asyncio.to_thread(send_email, WORK_EMAIL, f"Work Briefing — {today_str}", work_body)
        else:
            logger.info("No Work items — skipping work email.")

        if home_rows:
            home_body = await create_briefing_content(home_rows, domain_label="Home")
            await asyncio.to_thread(send_email, HOME_EMAIL, f"Home Briefing — {today_str}", home_body)
        else:
            logger.info("No Home items — skipping home email.")

if __name__ == '__main__':
    logger.info(f"Starting Third Brain Briefing v{__version__} [{RUN_MODE}]...")
    asyncio.run(send_briefing())
