# Third Brain Architecture

Third Brain is a personal productivity system that uses a Telegram bot as its interface, Supabase as its database with vector search capabilities, and LLMs (via Gemini and OpenRouter) for natural language understanding.

The system has two main components that operate independently:

## Telegram Agent (`telegram_agent.py`)

This is the always-on interactive component. It listens for incoming Telegram messages (text or voice) and routes them through a two-stage pipeline. First, a lightweight classification model determines the user's *intent*: is this an **ingestion** (storing something new) or a **retrieval** (asking a question or updating a task)?

For ingestion, the agent extracts structured metadata (type, domain, topics, target date) from the raw text using an LLM, generates a vector embedding via OpenRouter's text-embedding-3-small model, and writes everything to a `thoughts` table in Supabase.

For retrieval, it spins up a Gemini-powered agentic chat session that has access to three tools — `search_thoughts` (semantic vector search), `list_thoughts` (recent items), and `update_thought` (status changes) — so the LLM can autonomously query the database and synthesize an answer.

Voice notes get transcribed by Gemini before entering this same routing flow.

## Morning Briefing (`briefing.py`)

This is a scheduled job (likely triggered by cron) that runs once, builds a daily summary, and exits. It queries Supabase directly via REST for all thoughts with status "New" and type Task/Project/Admin that are either overdue, due within the next 7 days, or have no date set. It then passes that filtered list to Gemini with a prompt that structures it into a prioritized morning briefing (flagging overdue items, picking top 3 priorities, grouping the rest). The formatted message gets sent to the user's Telegram chat.

## Data Layer

Supabase serves a dual role. It's a standard Postgres database holding the `thoughts` table (with content, metadata JSON, and timestamps), but it also stores vector embeddings alongside each record and exposes a `match_thoughts` RPC function for semantic similarity search. This means the agent can find relevant past thoughts even when the user's query doesn't use the same keywords as the stored content.

## Configuration

Both components share environment variables (API keys, Supabase credentials) loaded from a dotenv file, with the path varying based on whether the code is running in dev or prod (detected by checking if `projects/` appears in the file path). Model names are pulled from a shared `config.json`, giving you one place to swap models without touching code.

---

In short: Telegram is the UI, Gemini handles all the language reasoning, OpenRouter provides embeddings, and Supabase ties it together as both the relational store and the vector search engine.