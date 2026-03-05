import os
import sys
import logging
import sqlite3
import json
import datetime
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

__version__ = "0.3.0"

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
    env_filename = ".second_brain_dev.env"
else:
    RUN_MODE = "PROD 🚀"
    env_filename = ".second_brain.env"

env_path = os.path.expanduser(f"~/{env_filename}")
logger.info(f"Loading {RUN_MODE} config from: {env_path}")
load_dotenv(env_path)

config_path = os.path.join(BASE_DIR, "..", "config.json")
with open(config_path) as f:
    config = json.load(f)
    model_rag = config["llm_models"]["rag"]
    model_classification = config["llm_models"]["classification"]

DB_FOLDER = os.path.join(BASE_DIR, "..", "db")
DB_FILE = os.path.join(DB_FOLDER, "brain.db")

os.makedirs(DB_FOLDER, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

def get_embedding(text: str) -> list:
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY missing.")
        return []
    
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
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return []

def sync_to_supabase(content: str, metadata: dict):
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Supabase credentials missing.")
        return
        
    embedding = get_embedding(content)
    if not embedding:
        return
        
    endpoint = f"{SUPABASE_URL}/rest/v1/thoughts"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    data = {
        "content": content,
        "embedding": embedding,
        "metadata": metadata
    }
    
    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
        logger.info("Thought synced to Open Brain.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to sync to Supabase: {str(e)}")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            type TEXT,
            domain TEXT, 
            summary TEXT,
            details TEXT,
            target_date TEXT,
            tags TEXT,
            status TEXT DEFAULT 'New'
        )
    ''')
    
    conn.commit()
    conn.close()

def save_entry(data, status="New"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    tags_str = ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else ""
    
    t_date = data.get("target_date")
    if t_date == "None" or not t_date:
        t_date = None

    c.execute('''
        INSERT INTO entries (type, domain, summary, details, target_date, tags, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get("type"), 
        data.get("domain", "Home"), 
        data.get("summary"), 
        data.get("details"), 
        t_date,
        tags_str, 
        status
    ))
    conn.commit()
    entry_id = c.lastrowid
    conn.close()
    return entry_id

def get_active_projects():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT DISTINCT summary FROM entries WHERE type='Project' AND status='New'")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_brain_context(limit=200):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, type, domain, summary, details, target_date
        FROM entries 
        WHERE status != 'Done'
        ORDER BY id DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    context_text = "--- BEGIN OPEN LOOPS ---\n"
    for row in rows:
        date_info = f" [Due: {row['target_date']}]" if row['target_date'] else ""
        context_text += f"[{row['domain']}] {row['type']}: {row['summary']}{date_info}\n"
    context_text += "--- END OPEN LOOPS ---"
    return context_text

client = genai.Client(api_key=GEMINI_KEY)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""
🤖 **Second Brain v{__version__}**

**📥 CAPTURE**
• Just type text or send voice notes.
• **Dates:** Say "Buy milk next Friday" and I'll extract the date.

**📋 LISTS**
• /todo - All active tasks
• /work - Work tasks only
• /home - Home tasks only
• /review - See items held by Bouncer

**⚡ ACTIONS**
• `/done123` - Mark item 123 as Done
• `/edit123 New Text` - Rename item 123
• `/move123` - Toggle Work ↔ Home
• `/confirm123` - Force approve a Review item

**🧠 QUERY**
• `/ask <question>` - Search your brain
• `/version` - Check bot status
    """
    await update.effective_message.reply_text(msg, parse_mode='Markdown')

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"🤖 **Second Brain**\nVersion: `{__version__}`\nMode: **{RUN_MODE}**")

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.effective_message.text
    try:
        parts = msg_text.split(" ", 1)
        command_part = parts[0]
        entry_id = int(command_part.replace("/edit", ""))
        
        if len(parts) < 2:
            await update.effective_message.reply_text(f"📝 **Usage:**\n`/edit{entry_id} New Text Here`", parse_mode='Markdown')
            return
            
        new_text = parts[1]

    except ValueError:
        await update.effective_message.reply_text("❌ Invalid command format.")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT type, domain, summary, details, tags FROM entries WHERE id = ?", (entry_id,))
    row = c.fetchone()
    
    if not row:
        await update.effective_message.reply_text(f"❌ ID {entry_id} not found.")
        conn.close()
        return

    c.execute("UPDATE entries SET summary = ?, status = 'New' WHERE id = ?", (new_text, entry_id))
    conn.commit()
    conn.close()
    
    metadata = {
        "type": row[0],
        "domain": row[1],
        "topics": row[4].split(",") if row[4] else [],
        "source": "telegram"
    }
    sync_to_supabase(f"{new_text}\n{row[3]}", metadata)
    
    await update.effective_message.reply_text(f"📝 Updated & Synced Task {entry_id}:\n**{new_text}**")

async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry_id = None
    msg_text = update.effective_message.text
    
    if msg_text and msg_text.startswith("/confirm"):
        try:
            stripped = msg_text.replace("/confirm", "").strip()
            if stripped.isdigit(): entry_id = int(stripped)
        except ValueError: pass

    if entry_id is None and context.args:
        try: entry_id = int(context.args[0])
        except ValueError: pass
            
    if entry_id is None:
        await update.effective_message.reply_text("Usage: /confirm <ID>")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT type, domain, summary, details, tags FROM entries WHERE id = ?", (entry_id,))
    row = c.fetchone()
    
    if not row:
        await update.effective_message.reply_text(f"❌ ID {entry_id} not found.")
        conn.close()
        return
        
    c.execute("UPDATE entries SET status = 'New' WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

    metadata = {
        "type": row[0],
        "domain": row[1],
        "topics": row[4].split(",") if row[4] else [],
        "source": "telegram"
    }
    sync_to_supabase(f"{row[2]}\n{row[3]}", metadata)
    
    await update.effective_message.reply_text(f"✅ Item {entry_id} confirmed and synced to Open Brain.")

async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, type, domain, summary, target_date
        FROM entries 
        WHERE status = 'Review'
        ORDER BY id DESC LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.effective_message.reply_text("🛡️ Bouncer: No items pending review.")
        return

    msg = "🛡️ **BOUNCER REVIEW QUEUE**\n\n"
    for row in rows:
        date_str = f" 📅 {row['target_date']}" if row['target_date'] else ""
        msg += f"⚠️ **{row['domain']} {row['type']}** (ID: {row['id']})\n"
        msg += f"Summary: {row['summary']}{date_str}\n"
        msg += f"Action: /confirm{row['id']} or /edit{row['id']}\n\n"
    
    await update.effective_message.reply_text(msg, parse_mode='Markdown')

async def move_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry_id = None
    msg_text = update.effective_message.text

    if msg_text:
        if msg_text.startswith("/move_"):
            try: entry_id = int(msg_text.split("_")[1])
            except (IndexError, ValueError): pass
        
        elif msg_text.startswith("/move"):
            try:
                stripped = msg_text.replace("/move", "").strip()
                if stripped.isdigit(): entry_id = int(stripped)
            except ValueError: pass

    if entry_id is None and context.args:
        try: entry_id = int(context.args[0])
        except ValueError: pass

    if entry_id is None:
        await update.effective_message.reply_text("Usage: /move <ID>")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT domain, summary FROM entries WHERE id = ?", (entry_id,))
    row = c.fetchone()
    
    if not row:
        await update.effective_message.reply_text(f"❌ ID {entry_id} not found.")
        conn.close()
        return

    current_domain = row[0]
    new_domain = "Home" if current_domain == "Work" else "Work"
    c.execute("UPDATE entries SET domain = ? WHERE id = ?", (new_domain, entry_id))
    conn.commit()
    conn.close()

    icon = "🏡" if new_domain == "Home" else "💼"
    await update.effective_message.reply_text(f"{icon} Moved to **{new_domain}**: {row[1]}")

async def todo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
        SELECT id, type, domain, summary, target_date
        FROM entries 
        WHERE status = 'New' AND type IN ('Task', 'Project', 'Admin')
        ORDER BY 
            CASE WHEN target_date IS NULL THEN 1 ELSE 0 END, 
            target_date ASC, 
            id DESC 
        LIMIT 40
    """)
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.effective_message.reply_text("🎉 All Clear! No active tasks.")
        return

    work_items = []
    home_items = []
    
    for row in rows:
        icon = "🏗️" if row['type'] == 'Project' else "▫️"
        date_str = f" [📅 {row['target_date']}]" if row['target_date'] else ""
        
        line = f"{icon} /done{row['id']} : {row['summary']}{date_str}"
        
        if row['domain'] == 'Work':
            work_items.append(line)
        else:
            home_items.append(line)

    msg = ""
    if work_items:
        msg += "💼 **WORK**\n" + "\n".join(work_items) + "\n\n"
    if home_items:
        msg += "🏡 **HOME**\n" + "\n".join(home_items)
        
    await update.effective_message.reply_text(msg, parse_mode='Markdown')

async def work_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_tasks(update, domain="Work", title="💼 **Work Tasks**")

async def home_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_tasks(update, domain="Home", title="🏡 **Home Tasks**")

async def list_tasks(update, domain, title):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, type, summary, target_date
        FROM entries 
        WHERE status = 'New' AND domain = ? AND type IN ('Task', 'Project', 'Admin')
        ORDER BY 
            CASE WHEN target_date IS NULL THEN 1 ELSE 0 END, 
            target_date ASC, 
            id DESC 
        LIMIT 20
    """, (domain,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.effective_message.reply_text(f"{title}\nAll Clear! 🎉")
        return

    msg = f"{title}\n\n"
    for row in rows:
        icon = "🏗️" if row['type'] == 'Project' else "▫️"
        date_str = f" [📅 {row['target_date']}]" if row['target_date'] else ""
        msg += f"{icon} /done{row['id']} : {row['summary']}{date_str}\n"
    await update.effective_message.reply_text(msg, parse_mode='Markdown')

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry_id = None
    msg_text = update.effective_message.text
    if msg_text:
        if msg_text.startswith("/done_"):
            try: entry_id = int(msg_text.split("_")[1])
            except (IndexError, ValueError): pass
        elif msg_text.startswith("/done"):
            try:
                stripped = msg_text.replace("/done", "").strip()
                if stripped.isdigit(): entry_id = int(stripped)
            except ValueError: pass

    if entry_id is None and context.args:
        try: entry_id = int(context.args[0])
        except ValueError: pass
            
    if entry_id is None:
        await update.effective_message.reply_text("Usage: /done <ID>")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE entries SET status = 'Done' WHERE id = ?", (entry_id,))
    if c.rowcount > 0:
        await update.effective_message.reply_text(f"✅ Item {entry_id} marked as Done.")
    else:
        await update.effective_message.reply_text(f"❌ ID {entry_id} not found.")
    conn.commit()
    conn.close()

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    if not question:
        await update.effective_message.reply_text("Usage: /ask <question>")
        return
    await update.effective_message.reply_text("Thinking...")
    brain_dump = get_brain_context(limit=500)
    rag_prompt = f"""
    You are my Second Brain. Answer strictly based on these logs.
    {brain_dump}
    USER QUESTION: {question}
    """
    try:
        response = client.models.generate_content(
            model=model_rag, contents=rag_prompt   
        )
        await update.effective_message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Ask Error: {e}")
        await update.effective_message.reply_text("Search failed.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.text and msg.text.startswith("/"):
        await msg.reply_text("❌ Unknown command. Try /help")
        return

    logger.info(f"Processing message from {update.effective_chat.id}")
    
    active_projects = get_active_projects()
    projects_list = ", ".join(active_projects) if active_projects else "None"
    today_str = datetime.date.today().isoformat()
    
    dynamic_prompt = f"""
    You are a Second Brain assistant. Analyze the input.
    TODAY IS: {today_str}
    
    CONTEXT - USER'S ACTIVE PROJECTS:
    [{projects_list}]
    
    INSTRUCTIONS:
    1. Classify 'domain' as 'Work' ONLY IF related to: IT, Infor, WSA, WSAudiology, Magento, ERP, or Corporate SQL.
    2. Classify 'domain' as 'Home' if related to: General Programming (Python/C++), AI, Electronics, Vegan, Jeep, Cats, Personal Life, or Self-Improvement.
    3. Classify 'type' using these strict definitions:
       - 'Project': A multi-step goal requiring >1 action.
       - 'Task': A specific action step that advances an ACTIVE PROJECT listed above.
       - 'Admin': A standalone errand, maintenance chore, or "keep the lights on" task.
       - 'Idea': A thought, reference, or note with no immediate action.
       - 'person_note': Information specific to a person.
    4. EXTRACT DATES: Extract target dates in YYYY-MM-DD format. Leave null if none.
    5. EXTRACT OPEN BRAIN METADATA: 
       - 'people': array of people mentioned (empty if none)
       - 'action_items': array of implied to-dos (empty if none)
    6. Output strictly JSON. Include a "confidence" integer field (0-100) indicating certainty about the Domain.
    
    Example JSON:
    [
      {{
        "type": "Admin", 
        "domain": "Home",
        "summary": "Concise title",
        "details": "Full context",
        "target_date": "2026-02-20", 
        "tags": ["tag1", "tag2"],
        "people": ["Subbarao"],
        "action_items": ["Review PR"],
        "confidence": 85
      }}
    ]
    """
    
    response_text = ""
    try:
        if msg.voice:
            file = await context.bot.get_file(msg.voice.file_id)
            file_path = os.path.join(BASE_DIR, "voice_note.ogg") 
            await file.download_to_drive(file_path)
            
            uploaded_file = client.files.upload(file=file_path)
            
            response = client.models.generate_content(
                model=model_classification,
                contents=[uploaded_file, dynamic_prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            response_text = response.text
            
            if os.path.exists(file_path): 
                os.remove(file_path)

        elif msg.text:
            response = client.models.generate_content(
                model=model_classification,
                contents=f"{dynamic_prompt}\nInput: {msg.text}",
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            response_text = response.text

        if response_text:
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            if isinstance(data, dict): 
                entries = [data]
            elif isinstance(data, list): 
                entries = data
            else: 
                entries = []

            results = []
            for entry in entries:
                entry['summary'] = entry.get('summary') or "Untitled Note"
                entry['domain'] = entry.get('domain') or "Home"
                entry['type'] = entry.get('type') or "Idea"
                
                confidence = entry.get("confidence", 100)
                is_safe = confidence >= 60
                
                status = "New" if is_safe else "Review"
                entry_id = save_entry(entry, status=status)
                
                if is_safe:
                    metadata = {
                        "type": entry.get("type"),
                        "domain": entry.get("domain"),
                        "topics": entry.get("tags", []),
                        "people": entry.get("people", []),
                        "action_items": entry.get("action_items", []),
                        "source": "telegram"
                    }
                    sync_content = f"{entry['summary']}\n{entry.get('details', '')}".strip()
                    sync_to_supabase(sync_content, metadata)

                icon = "💼" if entry.get("domain") == "Work" else "🏡"
                date_str = f" [📅 {entry.get('target_date')}]" if entry.get('target_date') else ""
                
                if is_safe:
                    results.append(f"{icon} Saved & Synced: {entry['summary']}{date_str} (ID: {entry_id})")
                else:
                    results.append(f"🛡️ **Bouncer Alert** (Conf: {confidence}%)\n"
                                   f"I classified this as {icon} **{entry['domain']}**.\n"
                                   f"Saved to Review (ID: {entry_id}).\n"
                                   f"Type `/confirm{entry_id}` to accept and sync.")
            
            final_msg = "\n\n".join(results)
            logger.info(final_msg)
            await msg.reply_text(final_msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.reply_text("Error processing entry.")

        
if __name__ == '__main__':
    if not BOT_TOKEN or not GEMINI_KEY:
        logger.error("Set TELEGRAM_BOT_TOKEN and GEMINI_API_KEY env vars.")
        exit(1)

    init_db()
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .get_updates_read_timeout(42.0)
        .build()
    )
    
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("todo", todo_command))
    app.add_handler(CommandHandler("work", work_command))
    app.add_handler(CommandHandler("home", home_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("move", move_command))
    app.add_handler(CommandHandler("version", version_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("confirm", confirm_command))
    
    app.add_handler(MessageHandler(filters.Regex(r'^/confirm\d+'), confirm_command))
    app.add_handler(MessageHandler(filters.Regex(r'^/edit\d+'), edit_command))
    app.add_handler(MessageHandler(filters.Regex(r'^/done\d+'), done_command))
    app.add_handler(MessageHandler(filters.Regex(r'^/move\d+'), move_command)) 

    app.add_handler(MessageHandler(filters.Regex(r'^/done_\d+$'), done_command))
    app.add_handler(MessageHandler(filters.Regex(r'^/move_\d+$'), move_command))
    
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    
    logger.info(f"Bot v.{__version__} is listening [{RUN_MODE}]. Database: {DB_FILE}")
    app.run_polling()

