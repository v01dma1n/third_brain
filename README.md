# 🧠 Second Brain Bot

> **Vibe Coded** based on the [Second Brain philosophy by Nate B. Jones](https://natebjones.substack.com/).

A frictionless capture system that uses AI to organize your life. This Telegram bot acts as the interface to your Second Brain, separating the act of **capturing** ideas from the mental load of **organizing** them.

## 🌟 Philosophy

Traditional productivity systems fail because they ask you to categorize data *while* you are trying to capture it. This system uses **Google Gemini** to act as a "Sorter" and a "Bouncer," automatically classifying your inputs into **Work** or **Home** domains and filtering out low-confidence data.

## ✨ Features

* **⚡ Frictionless Capture:** Send text or Voice Notes. The bot transcribes and processes them instantly.
* **🤖 AI Classification:**
    * **Work:** Strictly scoped to corporate topics (Infor, WSA, Magento, ERP, SQL).
    * **Home:** Everything else (General Python/AI coding, Electronics, Personal, Cats, Jeep).
* **📅 Smart Target Dates:** Simply say "Buy milk next Friday" or "Submit report tomorrow," and the AI automatically extracts and assigns the target date.
* **🛡️ The Bouncer:**
    * **High Confidence (≥60%):** Auto-saved to your active lists.
    * **Low Confidence:** Held in a "Review Queue" for manual approval.
* **🖥️ Interactive Web Dashboard:** A local Streamlit web app allowing you to view, filter, and bulk-edit your tasks in a spreadsheet-like interface.
* **🧠 RAG Context:** Ask questions (`/ask`) about your past notes, tasks, and projects.
* **🔄 Context Switching:** Smart logic detects if it is running in **DEV** (`~/projects`) or **PROD** (`~/bin`) and loads the appropriate environment variables.
* **📂 Task Management:** Edit, Move, and Complete tasks directly from the chat interface using quick-click commands.

## 🛠️ Tech Stack

* **Language:** Python 3.12+
* **Interface:** [python-telegram-bot](https://python-telegram-bot.org/) & [Streamlit](https://streamlit.io/)
* **Intelligence:** Google Gemini API (models: `gemini-2.0-flash` & `gemini-3-flash-preview`)
* **Storage:** SQLite (`brain.db`) with Pandas for data manipulation
* **Deployment:** Systemd User Services on Linux / Cron

## 🚀 Installation

### 1. 🤖 Create your Telegram Bot
Before you install the code, you need to register a bot with Telegram.

1. Open Telegram and search for **@BotFather** (the official bot builder).
2. Send the command `/newbot`.
3. Follow the prompts:
   * **Name:** The display name (e.g., "My Second Brain").
   * **Username:** Must end in `bot` (e.g., `rybark_brain_bot`).
4. **Copy the HTTP API Token** provided by BotFather. You will need this for Step 3.

### 2. Clone & Environment
```bash
git clone [https://github.com/yourusername/second_brain.git](https://github.com/yourusername/second_brain.git)
cd second_brain
python3 -m venv ml-env
source ml-env/bin/activate
pip install -r requirements.txt

```

### 3. Configuration

The bot supports dual environments for safe development. Create these files in your **Home Directory** (`~/`):

**Production:** `~/.second_brain.env`

```ini
TELEGRAM_BOT_TOKEN="YOUR_API_TOKEN_FROM_STEP_1"
GEMINI_API_KEY="YOUR_GEMINI_KEY"
TELEGRAM_BOT_CHAT_ID="YOUR_TELEGRAM_USER_ID"

```

**Development:** `~/.second_brain_dev.env`

```ini
TELEGRAM_BOT_TOKEN="YOUR_DEV_BOT_TOKEN"
GEMINI_API_KEY="YOUR_GEMINI_KEY"
TELEGRAM_BOT_CHAT_ID="YOUR_TELEGRAM_USER_ID"

```

#### 🆔 How to find your `TELEGRAM_BOT_CHAT_ID`

The `briefing.py` script needs this ID to send **you** messages (since it runs via Cron, not as a reply to a user).

**Option A: The Hacker Way (Recommended)**

1. Run your bot manually: `python src/telegram_listener.py`
2. Send a message to the bot on Telegram (e.g., "Hello").
3. Look at your terminal output. The bot prints: `DEBUG: Chat ID: 123456789`
4. Copy that number into your `.env` files.

**Option B: The Easy Way**

1. Search for `@userinfobot` on Telegram.
2. Click Start.
3. It will reply with your ID.

### 4. Running the Bot (Listener)

**Manual:**

```bash
python src/telegram_listener.py

```

**Via Systemd:**
Ensure your service file points to the correct working directory.

```bash
systemctl --user start second_brain

```

### 5. 🖥️ Running the Interactive Dashboard

The system includes a local web interface to edit and view tasks.

```bash
# Make sure your virtual environment is active!
streamlit run src/dashboard.py

```

*(If you created the `dashboard.sh` helper script, you can simply run `./dashboard.sh`)*

### 6. 🌅 Running the Daily Briefing

The `briefing.py` script scans your "Open Loops" and sends a summarized AI digest to your Telegram every morning. It specifically targets overdue items and tasks due within the next 7 days, filtering out far-future noise.

1. Open your crontab:

```bash
crontab -e

```

2. Add the following line (adjust paths to match your system):

```bash
# Daily Briefing at 7:00 AM
0 7 * * * set -a; . $HOME/.second_brain.env; set +a; $HOME/projects/local/second_brain/ml-env/bin/python $HOME/projects/local/second_brain/src/briefing.py >> $HOME/projects/local/second_brain/log/briefing.log 2>&1

```

## 🎮 Commands

| Command | Description |
| --- | --- |
| `/todo` | View all active tasks (sorted by target date). |
| `/work` | View only Work tasks. |
| `/home` | View only Home tasks. |
| `/ask <query>` | RAG search your history. |
| `/done123` | Mark task ID 123 as complete. |
| `/edit123 <text>` | Rewrite the summary for task ID 123. |
| `/move123` | Toggle domain for task ID 123 (Work ↔ Home). |
| `/review` | See items held by **The Bouncer**. |
| `/confirm123` | Force approve review item ID 123. |
| `/version` | Check bot version and running mode. |

## 🛡️ The Bouncer Logic

To prevent "garbage in, garbage out," the bot assigns a confidence score (0-100) to every classification.

1. **Input:** "Restart the server"
2. **AI Analysis:** "Domain: Work, Confidence: 45%" (Ambiguous—could be home lab or work server).
3. **Action:** Saved with status `Review`. User must type `/confirm` or `/edit` to activate it.

---

*Generated via Vibe Coding / AI-Assisted Development.*

```

```
