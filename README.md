# Third Brain Bot

> **Vibe Coded** based on the [Second Brain philosophy by Nate B. Jones](https://natebjones.substack.com/) and [Open Brain also by Nate B. Jones](https://natebjones.substack.com/).

A natural language interface for capturing, structuring, and querying task and knowledge data. This system uses Telegram as the input layer, Google Gemini for intent routing and classification, OpenRouter for vector embeddings, and Supabase (PostgreSQL + pgvector) for storage and retrieval.

## Architecture

The system operates on two primary pipelines evaluated dynamically by an LLM upon receiving a message:

1. **Ingestion Pipeline**

   * **Transcription:** Voice notes are automatically transcribed.

   * **The Bouncer:** A strict validation gate rejects vague statements, conversational filler, or typos.

   * **Classification:** Extracts metadata (Type, Domain, Target Date, Topics) based on configurable business rules. Target dates default to 7 days out if unstated.

   * **Vectorization & Storage:** Generates a 1536-dimensional embedding using OpenRouter (`openai/text-embedding-3-small`) from a composite string of the text and metadata, and inserts the record into Supabase.

2. **Retrieval Pipeline**

   * Acts as an autonomous agent.

   * Leverages tool-calling to execute vector searches (`search_thoughts`), chronological queries (`list_thoughts`), and status modifications (`update_thought`) directly against the Supabase database.

## Tech Stack & Requirements

* **Language:** Python 3.12+ (Ubuntu 12.04 compatible or standard Linux)

* **Intelligence:** Google Gemini API (Intent Routing & Classification)

* **Embeddings:** OpenRouter API (`openai/text-embedding-3-small`)

* **Storage:** Supabase (PostgreSQL Database with `pgvector` extension enabled)

## Configuration

The system relies on a dual-configuration setup: a JSON file for application logic and `.env` files for secrets.

### 1. Application Config (`config.json`)

Create this file in the directory above your source code. It defines your domains, routing keywords, and models.

```json
{
  "environment": "PROD",
  "llm_models": {
    "rag": "gemini-2.5-flash",
    "classification": "gemini-2.5-flash"
  },
  "domains": {
    "Work": ["Infor", "FP7", "10.7", "Magento", "Oracle", "SQL Server", "ERP"],
    "Home": ["ESP32", "Arduino", "Vegan", "Ubuntu", "house", "groceries"]
  }
}
```

### 2. Environment Variables

Create `.third_brain.env` (and `.third_brain_dev.env` for development) in your home directory (`~/`).

```ini
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_BOT_CHAT_ID="your_telegram_chat_id"
GEMINI_API_KEY="your_gemini_api_key"
SUPABASE_URL="your_supabase_project_url"
SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_key"
OPENROUTER_API_KEY="your_openrouter_api_key"
```

## Usage

### Running the Agent

Start the listener process to monitor the Telegram bot for incoming text or voice messages.

```bash
python telegram_agent.py
```

### Running the Briefing

The `briefing.py` script generates an LLM-summarized digest of open tasks that are overdue or due within the next 7 days. It is designed to be executed via a cron job.

```bash
# Example crontab entry to run daily at 7:00 AM
0 7 * * * /path/to/python /path/to/briefing.py >> /path/to/briefing.log 2>&1
```

## Interaction Guidelines

No slash commands are required. Interact via natural language.

**Ingestion Examples:**

* "I need to review the SQL Server logs for the FP7 migration by Friday." (Routes to Work, sets specific date).

* "Buy almond milk and tofu." (Routes to Home, sets date 7 days out).

**Retrieval & Management Examples:**

* "List my open Work tasks."

* "What did I decide about the Magento caching issue?"

* "Mark the task about the FP7 server logs as done."
