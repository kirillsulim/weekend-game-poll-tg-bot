# Boardgame Poll Bot 🤖🎲

A Telegram bot that helps groups decide when to meet for board games.  
It creates polls with date options and can be set to automatically create a poll every Monday asking about the upcoming weekend.

## Features

- **`/poll`** – create a one‑off poll with the next three days (or custom dates)
- **`/enable_weekly`** – schedule a recurring poll every **Monday at 12:00 UTC** (Saturday & Sunday options)
- **`/disable_weekly`** – stop the recurring poll for the chat
- **SQLite persistence** – weekly settings survive bot restarts
- **Docker support** – easy deployment with persistent data volume

## Commands

| Command | Example | Description |
|---------|---------|-------------|
| `/poll` | `/poll` | Poll with the next three days (today, tomorrow, day after tomorrow) |
| `/poll 2026-07-04 2026-07-11` | `/poll 2026-07-04 2026-07-11` | Poll with custom ISO dates |
| `/enable_weekly` | `/enable_weekly` | Start automatic weekly poll (Monday 12:00 UTC) |
| `/disable_weekly` | `/disable_weekly` | Stop automatic weekly poll |

Weekly polls contain the actual upcoming Saturday and Sunday dates (e.g. `Saturday, 2026-07-04` and `Sunday, 2026-07-05`).  
All polls allow **multiple answers** and are **not anonymous**, so you can see who voted for each day.

## Local Setup

### 1. Clone / download the project
```bash
git clone <your-repo-url>
cd boardgame-bot
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set your bot token
Get a token from [@BotFather](https://t.me/BotFather) on Telegram, then export it:
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghikl"
# Windows (cmd):
set TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghikl
```

### 5. Run the bot
```bash
python boardgame_poll_bot.py
```

The SQLite database file (`bot_data.sqlite`) will be created in the same folder.  
**Do not delete it** – it stores which groups have enabled the weekly poll.

## Docker Setup

### Build and run
```bash
docker build -t boardgame-bot .
docker run -d \
  --name boardgame-bot \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -v boardgame-data:/data \
  boardgame-bot
```

Using `docker compose`:
```yaml
# docker-compose.yml
version: "3.8"
services:
  bot:
    build: .
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
    volumes:
      - bot_data:/data
    restart: unless-stopped

volumes:
  bot_data:
```
```bash
TELEGRAM_BOT_TOKEN="your_token" docker compose up -d
```

The volume `boardgame-data` (or `bot_data`) persists the SQLite database, so weekly poll settings are kept even if you recreate the container.

## Customisation

### Change poll schedule
Edit `boardgame_poll_bot.py` and locate the `run_daily` call inside `enable_weekly` and `restore_weekly_jobs`.  
For testing, you can temporarily switch to `run_repeating`:
```python
context.job_queue.run_repeating(
    callback=send_weekly_poll,
    interval=60,      # every 60 seconds
    first=1,
    chat_id=chat_id,
    name=f"weekly_poll_{chat_id}",
)
```

### Change timezone
The default time is **12:00 UTC**. To use a different timezone, change the `tzinfo` parameter inside `run_daily`:
```python
from datetime import timezone, timedelta

# Example: Moscow (UTC+3)
time(hour=12, minute=0, tzinfo=timezone(timedelta(hours=3)))
```

## Requirements

- Python ≥ 3.8
- `python-telegram-bot[job-queue]` (includes `APScheduler`)

See `requirements.txt` for the exact dependency.

## File overview

| File | Purpose |
|------|---------|
| `boardgame_poll_bot.py` | Main bot application |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container definition |
| `.dockerignore` | Excludes unnecessary files from the Docker build |
| `bot_data.sqlite` | SQLite database (auto‑generated) |
| `docker-compose.yml` | (optional) Example compose file |

## License

Feel free to use and modify this project for your own game nights. 🎉
