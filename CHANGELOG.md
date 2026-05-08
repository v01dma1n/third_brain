# Changelog

## [1.7.0] - 2026-05-08

### Added
- Human-friendly `seq_id` (BIGSERIAL) column on `thoughts` table — tasks now referenced as `#7`, `#12`, etc.
- `update_thought` now resolves `seq_id` to UUID internally; agent always works with `#seq_id`, never raw UUIDs
- `search_thoughts` and `list_thoughts` return `seq_id` in all results
- Dashboard shows `#` as first read-only column

## [1.6.0] - 2026-05-08

### Added
- Per-session conversation history for the retrieval agent (last 10 turns, 1-hour idle TTL)
- Multi-turn references now work: "mark the second one as done", "change that task's date"
- Agent system instruction rebuilt per-request with today's date for accurate natural language date resolution

### Fixed
- `chat.get_history()` used instead of non-existent `.history` attribute (SDK compatibility)

## [1.5.1] - 2026-05-08

### Fixed
- `update_thought` now accepts `new_target_date` (YYYY-MM-DD) in addition to `new_status`
- Agent system instruction updated to instruct date resolution before calling `update_thought`

## [1.5.0] - 2026-05-08

### Added
- Confidence-based bouncer: items with confidence < 60 land as `Review` status instead of outright rejection
- `Admin` type restored alongside Task, Project, Idea
- `list_thoughts` default limit raised from 5 to 12
- Improved intent router: update/change/reschedule commands reliably classified as `RETRIEVAL`

### Changed
- `ingest_thought` accepts a `status` parameter so the bouncer can route to `Review` or `New`

## [1.4.3] - 2026-05-08

### Fixed
- Bot token conflict resolved — third_brain now uses its own dedicated Telegram bot token
- `TELEGRAM_BOT_CHAT_ID` corrected to user's personal chat ID

## [1.1.0] - 2026-05-08 (briefing.py)

### Added
- Domain-split email briefings via Gmail SMTP (`smtplib`, no new dependencies)
- Work domain items → work email; Home domain items → home email
- Telegram combined briefing unchanged
- Sender alias set to `ThirdBrain <sender@gmail.com>`
- Skips email send if no items exist for that domain
- New env vars: `GMAIL_SENDER`, `GMAIL_APP_PASSWORD`, `WORK_EMAIL`, `HOME_EMAIL`

## [1.0.0] - 2026-03-10

### Added
- Streamlit dashboard backed by Supabase with sidebar filters (Status / Domain / Type)
- Editable table with inline save via REST PATCH
- Metrics bar: Shown / Work / Home / Review counts
- Deployed as persistent systemd service on port 8502

## [Unreleased → 1.0.0-alpha]

### Added
- Telegram agent with voice transcription via Gemini
- LLM-based intent routing (INGESTION vs RETRIEVAL)
- Strict bouncer validation gate (ACCEPT / REJECT)
- Metadata extraction: type, domain, topics, target date (7-day default for Tasks)
- Vectorization via OpenRouter (`openai/text-embedding-3-small`, 1536-dim)
- Supabase / pgvector storage and semantic search
- Autonomous retrieval agent with tool-calling (`search_thoughts`, `list_thoughts`, `update_thought`)
- Daily morning briefing via Gemini with Telegram delivery
- Dev / Prod environment detection via `config.json`
- `.gitignore`, systemd service files, cron setup
