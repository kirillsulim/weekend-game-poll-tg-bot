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

WEEKDAYS_RU = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}

SCHEDULE_TEST_MODE = os.environ.get("SCHEDULE_TEST_MODE")

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
def get_upcoming_weekend_dates() -> list[date]:
    today = date.today()
    days_until_saturday = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_until_saturday)
    return [saturday, saturday + timedelta(days=1)]

def get_date_options(args: list[str]) -> list[str]:
    if not args:
        today = date.today()
        dates = [today + timedelta(days=i) for i in range(3)]
    else:
        try:
            dates = [date.fromisoformat(arg) for arg in args]
        except ValueError:
            return args

    # Russian day name + ISO date
    return [f"{WEEKDAYS_RU[d.weekday()]}, {d.isoformat()}" for d in dates]

def build_poll_options(dates: list[date]) -> list[str]:
    """Return nicely formatted poll options: weekday name + date, plus 'Пас'."""
    options = [f"{WEEKDAYS_RU[d.weekday()]}, {d.isoformat()}" for d in dates]
    options.append("Пас")
    return options

# --------------------------------------------
# Job callback – send the weekend poll
# --------------------------------------------
async def send_weekly_poll(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    saturday, sunday = get_upcoming_weekend_dates()
    options = build_poll_options([saturday, sunday])
    question = "Играем на этой неделе?"
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
            await update.message.reply_text("Еженедельный опрос уже включен для этого чата.")
            return

    if not SCHEDULE_TEST_MODE:
    # Schedule the job (Monday 12:00 UTC)
        context.job_queue.run_daily(
            callback=send_weekly_poll,
            time=get_poll_time(),
            days=(0,),
            chat_id=chat_id,
            name=f"weekly_poll_{chat_id}",
        )
    else:
        # Schedule the job (every 60 seconds for testing)
        context.job_queue.run_repeating(
            callback=send_weekly_poll,
            interval=60,  # seconds
            first=1,  # wait 1 sec before first run
            chat_id=chat_id,
            name=f"weekly_poll_{chat_id}",
        )

    # Persist to database
    save_weekly_chat(chat_id)
    await update.message.reply_text(
        "✅ Расписашка включена! Каждый понедельник в 12:00 бот будет создавать опрос на выходные."
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
    await update.message.reply_text("❌ Еженедельный опрос отключен.")


async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    # ---- Determine the dates ----
    if not args:
        today = date.today()
        dates = [today + timedelta(days=i) for i in range(3)]
    else:
        try:
            dates = [date.fromisoformat(arg) for arg in args]
        except ValueError:
            await update.message.reply_text(
                "⚠️ Неверный формат даты. Используйте ГГГГ-ММ-ДД (например, 2026-07-04)."
            )
            return

    # ---- Build poll options (same format as weekly poll) ----
    options = build_poll_options(dates)
    question = "Играем?"
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
        if not SCHEDULE_TEST_MODE:
            # Avoid duplicates if a job was already added (shouldn’t happen)
            application.job_queue.run_daily(
                callback=send_weekly_poll,
                time=get_poll_time(),
                days=(0,),
                chat_id=chat_id,
                name=f"weekly_poll_{chat_id}",
            )
        else:
            application.job_queue.run_repeating(
                callback=send_weekly_poll,
                interval=60,
                first=1,
                chat_id=chat_id,
                name=f"weekly_poll_{chat_id}",
            )
    if chat_ids:
        print(f"Restored weekly polls for {len(chat_ids)} chat(s).")

def get_poll_time() -> time:
    return time(hour=12, minute=0, tzinfo=timezone(timedelta(hours=5)))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для организации настольных игр.\n\n"
        "Я помогаю группе выбрать удобную дату с помощью голосования.\n\n"
        "Доступные команды:\n"
        "/poll – создать опрос (3 ближайших дня или свои даты)\n"
        "/enable_weekly – включить еженедельный опрос (Пн, 12:00 UTC+5)\n"
        "/disable_weekly – выключить еженедельный опрос\n"
        "/help – показать это сообщение\n\n"
        "Добавьте меня в группу и используйте команды!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Как использовать бота*\n\n"
        "/poll – опрос на три ближайших дня\n"
        "/poll 2026-07-04 2026-07-11 – опрос с конкретными датами\n"
        "/enable_weekly – автоматический опрос каждый понедельник\n"
        "/disable_weekly – отключить автоматический опрос\n\n"
        "Опросы не анонимные, можно выбрать несколько вариантов.",
    )

# --------------------------------------------
# Main
# --------------------------------------------
def main():
    init_db()  # create table if not exists

    app = Application.builder().token(TOKEN).post_init(restore_weekly_jobs).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("poll", poll_command))
    app.add_handler(CommandHandler("enable_weekly", enable_weekly))
    app.add_handler(CommandHandler("disable_weekly", disable_weekly))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
