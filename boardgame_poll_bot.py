import os
import sqlite3
from datetime import date, time, timedelta, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --------------------------------------------
# Configuration
# --------------------------------------------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")

DB_PATH = os.environ.get("DB_PATH", "bot_data.sqlite")

# --------------------------------------------
# SQLite helper functions
# --------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_polls (
            chat_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def save_weekly_chat(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO weekly_polls (chat_id) VALUES (?)", (chat_id,))
    conn.commit()
    conn.close()

def remove_weekly_chat(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM weekly_polls WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def get_all_weekly_chats() -> list[int]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT chat_id FROM weekly_polls").fetchall()
    conn.close()
    return [row[0] for row in rows]

# --------------------------------------------
# Helper: upcoming Saturday & Sunday
# --------------------------------------------
def get_upcoming_weekend_dates():
    today = date.today()
    days_until_saturday = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_until_saturday)
    return saturday, saturday + timedelta(days=1)

# --------------------------------------------
# Job callback – send the weekend poll
# --------------------------------------------
async def send_weekly_poll(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    saturday, sunday = get_upcoming_weekend_dates()
    options = [
        f"Saturday, {saturday.isoformat()}",
        f"Sunday, {sunday.isoformat()}",
    ]
    question = "Board games this weekend? Which day(s) can you make it?"
    await context.bot.send_poll(
        chat_id=chat_id,
        question=question,
        options=options,
        is_anonymous=False,
        allows_multiple_answers=True,
    )

# --------------------------------------------
# /enable_weekly command
# --------------------------------------------
async def enable_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Check if a job is already running in memory
    current_jobs = context.job_queue.jobs()
    for job in current_jobs:
        if job.name == f"weekly_poll_{chat_id}":
            await update.message.reply_text("Weekly poll is already enabled for this chat.")
            return

    # Schedule the job (Monday 12:00 UTC)
    context.job_queue.run_daily(
        callback=send_weekly_poll,
        time=time(hour=12, minute=0, tzinfo=timezone.utc),
        days=(0,),
        chat_id=chat_id,
        name=f"weekly_poll_{chat_id}",
    )

    # Persist to database
    save_weekly_chat(chat_id)
    await update.message.reply_text(
        "✅ Weekly poll enabled! Every Monday at 12:00 UTC a poll will be created for the upcoming weekend."
    )

# --------------------------------------------
# /disable_weekly command
# --------------------------------------------
async def disable_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Remove the running job (if any)
    for job in context.job_queue.jobs():
        if job.name == f"weekly_poll_{chat_id}":
            job.schedule_removal()

    # Remove from database
    remove_weekly_chat(chat_id)
    await update.message.reply_text("❌ Weekly poll disabled.")

# --------------------------------------------
# /poll command (unchanged)
# --------------------------------------------
def get_date_options(args: list[str]) -> list[str]:
    if not args:
        today = date.today()
        return [(today + timedelta(days=i)).isoformat() for i in range(3)]
    return args

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    options = get_date_options(context.args)
    question = "On which date(s) can you meet for board games?"
    await context.bot.send_poll(
        chat_id=chat_id,
        question=question,
        options=options,
        is_anonymous=False,
        allows_multiple_answers=True,
    )

# --------------------------------------------
# Restore persisted jobs on startup
# --------------------------------------------
async def restore_weekly_jobs(application: Application):
    """Called after the application is built, before polling starts."""
    chat_ids = get_all_weekly_chats()
    for chat_id in chat_ids:
        # Avoid duplicates if a job was already added (shouldn’t happen)
        application.job_queue.run_daily(
            callback=send_weekly_poll,
            time=time(hour=12, minute=0, tzinfo=timezone.utc),
            days=(0,),
            chat_id=chat_id,
            name=f"weekly_poll_{chat_id}",
        )
    if chat_ids:
        print(f"Restored weekly polls for {len(chat_ids)} chat(s).")

# --------------------------------------------
# Main
# --------------------------------------------
def main():
    init_db()  # create table if not exists

    app = Application.builder().token(TOKEN).post_init(restore_weekly_jobs).build()

    app.add_handler(CommandHandler("poll", poll_command))
    app.add_handler(CommandHandler("enable_weekly", enable_weekly))
    app.add_handler(CommandHandler("disable_weekly", disable_weekly))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
