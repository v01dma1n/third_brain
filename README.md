# Third Brain

> **Vibe Coded** based on the [Second Brain philosophy by Nate B. Jones](https://natebjones.substack.com/) and [Open Brain also by Nate B. Jones](https://natebjones.substack.com/).

A natural language interface for capturing, structuring, and querying personal tasks and knowledge. Telegram is the input layer; Google Gemini handles intent routing, classification, and retrieval; OpenRouter generates vector embeddings; Supabase (PostgreSQL + pgvector) provides storage and semantic search.

## Features

- **Voice and text capture** via Telegram — no slash commands required
- **Confidence-based bouncer** — high-confidence items land in `New`, low-confidence items go to `Review` for manual approval
- **Semantic search** via pgvector — retrieval understands meaning, not just keywords
- **Autonomous retrieval agent** — tool-calling LLM answers questions and updates tasks in natural language
- **Human-friendly task IDs** — every thought gets a `#seq_id` (e.g. `#7`) for easy reference
- **Per-session conversation memory** — agent remembers the last 10 exchanges for multi-turn interactions
- **Morning briefing** — daily digest sent to Telegram (combined) and email (Work and Home separately)
- **Streamlit dashboard** — browser UI for bulk review, filtering, and inline editing
- **Personal fact injection** — stable personal context (base facts + weekly auto-inferred facts) prepended to every Gemini prompt

## Architecture

Each incoming Telegram message is routed by an LLM to one of two pipelines:

### Ingestion Pipeline

1. **Transcription** — voice notes are transcribed automatically via Gemini
2. **Intent routing** — LLM classifies the message as `INGESTION` or `RETRIEVAL`
3. **The Bouncer** — evaluates whether the input is concrete and actionable; returns a confidence score (0–100)
   - Score ≥ 60 → saved as `New`
   - Score < 60 → saved as `Review` (visible in dashboard for approval)
   - Clear filler/typo → rejected with a reason
4. **Metadata extraction** — extracts `type` (Task / Project / Admin / Idea), `domain` (Work / Home), `topics`, and `target_date` (defaults to 7 days out for Tasks)
5. **Vectorization** — 1536-dimensional embedding generated via OpenRouter (`openai/text-embedding-3-small`)
6. **Storage** — record inserted into Supabase `thoughts` table

### Retrieval Pipeline

An autonomous LLM agent with access to three tools:

| Tool | Description |
|---|---|
| `search_thoughts(query)` | Semantic vector search via Supabase `pgvector` |
| `list_thoughts(limit, status)` | Chronological listing with optional status filter |
| `update_thought(seq_id, new_status, new_target_date)` | Update status and/or target date by `#seq_id` |

Per-session conversation history (last 10 turns, 1-hour TTL) is passed on each request so multi-turn references like "mark the second one as done" work correctly.

### Morning Briefing

Runs daily via cron. Queries Supabase for all `New` Tasks, Projects, and Admin items that are overdue, due within 7 days, or undated. Generates three separate Gemini-summarized digests:

- **Telegram** — combined (Work + Home)
- **Work email** — Work domain items only
- **Home email** — Home domain items only

### Personal Fact Injection

Two fact files are prepended to every Gemini system prompt:

| File | Owner | Purpose |
|---|---|---|
| `facts/base_facts.md` | User (manual) | Stable personal context — identity, work domain, interests, skills |
| `facts/inferred_facts.md` | Automation (weekly) | Facts extracted from the last 90 days of captured thoughts |

`src/facts.py` loads and concatenates both files. Base facts always load first.

`src/infer_facts.py` runs weekly via cron, queries Supabase for non-cancelled/non-done thoughts from the last 90 days, extracts stable generalizations via Gemini, and appends new facts (confidence ≥ 0.7) without removing existing ones.

```bash
# Runs weekly on Sunday at 5:50 AM (before the 6:00 AM briefing)
50 5 * * 0 set -a; . $HOME/.third_brain.env; set +a; $HOME/.pyenv/versions/ml-env/bin/python $HOME/bin/third_brain/src/infer_facts.py >> $HOME/bin/third_brain/log/infer_facts.log 2>&1
```

Both fact files are excluded from redeploy overwrites — `deploy.sh` copies them only on first deploy.

### Dashboard

A Streamlit web UI served as a persistent systemd service. Provides:

- Sidebar filters by status, domain, and type
- Editable table with dropdowns for status / domain / type, date picker for target date
- `#seq_id` column as the human-friendly reference
- Metrics bar (shown / Work / Home / Review counts)
- Auto-saves changed rows to Supabase on edit

## Tech Stack

| Layer | Technology |
|---|---|
| Interface | Telegram Bot (`python-telegram-bot`) |
| LLM | Google Gemini (`gemini-2.5-flash`) |
| Embeddings | OpenRouter (`openai/text-embedding-3-small`, 1536-dim) |
| Storage | Supabase — PostgreSQL + `pgvector` |
| Dashboard | Streamlit |
| Email | Gmail SMTP (`smtplib`) |
| Runtime | Python 3.12+, systemd user services |

## Supabase Schema

```sql
CREATE TABLE thoughts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq_id BIGSERIAL,
    content TEXT,
    metadata JSONB,   -- {type, domain, topics, status, target_date}
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Vector similarity search function
CREATE OR REPLACE FUNCTION query_thoughts(query_embedding VECTOR(1536), match_count INT)
RETURNS TABLE(id UUID, content TEXT, metadata JSONB, similarity FLOAT)
LANGUAGE sql AS $$
    SELECT id, content, metadata, 1 - (embedding <=> query_embedding) AS similarity
    FROM thoughts
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
```

## Configuration

### `config.json`

Place in the project root. Controls environment, models, and domain routing keywords.

```json
{
  "environment": "PROD",
  "llm_models": {
    "rag": "gemini-2.5-flash",
    "classification": "gemini-2.5-flash"
  },
  "domains": {
    "Work": ["keyword1", "keyword2"],
    "Home": ["keyword3", "keyword4"]
  }
}
```

### `.third_brain.env`

Place in `~/`. Use `.third_brain_dev.env` for a development environment (set `"environment": "DEV"` in `config.json`).

```ini
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_BOT_CHAT_ID="your_telegram_chat_id"
GEMINI_API_KEY="your_gemini_api_key"
SUPABASE_URL="your_supabase_project_url"
SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"
OPENROUTER_API_KEY="your_openrouter_api_key"
GMAIL_SENDER="your_gmail_address"
GMAIL_APP_PASSWORD="your_gmail_app_password"
WORK_EMAIL="your_work_email"
HOME_EMAIL="your_home_email"
```

> Gmail app passwords require 2FA. Generate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

## Deployment

### Telegram Agent (systemd)

```ini
# ~/.config/systemd/user/third_brain.service
[Unit]
Description=Third Brain Telegram Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/bin/third_brain
ExecStart=%h/.pyenv/versions/ml-env/bin/python %h/bin/third_brain/src/telegram_agent.py
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=default.target
```

### Dashboard (systemd)

```ini
# ~/.config/systemd/user/third_brain_dashboard.service
[Unit]
Description=Third Brain Streamlit Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/bin/third_brain
ExecStart=%h/.pyenv/versions/ml-env/bin/streamlit run src/dashboard.py --server.headless true --server.port 8502
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=default.target
```

Enable both services:

```bash
loginctl enable-linger $USER
systemctl --user daemon-reload
systemctl --user enable third_brain third_brain_dashboard
systemctl --user start third_brain third_brain_dashboard
```

### Cron Jobs

```bash
# Morning briefing — daily at 6:00 AM
0 6 * * * set -a; . $HOME/.third_brain.env; set +a; $HOME/.pyenv/versions/ml-env/bin/python $HOME/bin/third_brain/src/briefing.py >> $HOME/bin/third_brain/log/briefing.log 2>&1

# Fact inference — weekly on Sunday at 5:50 AM (before briefing)
50 5 * * 0 set -a; . $HOME/.third_brain.env; set +a; $HOME/.pyenv/versions/ml-env/bin/python $HOME/bin/third_brain/src/infer_facts.py >> $HOME/bin/third_brain/log/infer_facts.log 2>&1
```

## Usage Examples

### Ingestion

```
"Review SQL Server logs for the FP7 migration by Friday"
→ Work / Task / target_date set to next Friday

"Buy almond milk and tofu"
→ Home / Task / target_date set 7 days out

"Idea: use pgvector for the new search feature"
→ Home / Idea / no target date
```

### Retrieval & Updates

```
"List my open Work tasks"
"What did I decide about the Magento caching issue?"
"Change the date on task #7 to next Monday"
"Mark #12 as done"
"Show me items in Review"
```

### Dashboard

Access at `http://localhost:8502` (or your Tailscale IP on port 8502 for remote access). Use the Review status filter to approve low-confidence bouncer items.
