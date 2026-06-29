import os
import sqlite3
from datetime import date, time, timedelta, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import calendar
from typing import Optional

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

SHORT_WEEKDAYS_RU = {
    "пн": 0,
    "вт": 1,
    "ср": 2,
    "чт": 3,
    "пт": 4,
    "сб": 5,
    "вс": 6,
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


def parse_smart_date(text: str) -> Optional[date]:
    """
    Parse a single argument into a date using these rules (in order):
    1. YYYY-MM-DD → exact date
    2. Short Russian weekday (ПН, ВТ, ...) → next occurrence (today included)
    3. Number (day of month) → nearest future date with that day
    4. Month-day (MM-DD) → nearest future date with that month and day
    Returns None if unparseable.
    """
    today = date.today()
    text = text.strip().lower()

    # 1. Try YYYY-MM-DD
    try:
        return date.fromisoformat(text)
    except (ValueError, TypeError):
        pass

    # 2. Short weekday
    if text in SHORT_WEEKDAYS_RU:
        target_weekday = SHORT_WEEKDAYS_RU[text]
        days_ahead = (target_weekday - today.weekday()) % 7
        return today + timedelta(days=days_ahead)

    # 3. Day of month number
    if text.isdigit():
        day = int(text)
        if 1 <= day <= 31:
            year, month = today.year, today.month
            # Try this month
            _, max_day = calendar.monthrange(year, month)
            if day <= max_day:
                candidate = date(year, month, day)
                if candidate >= today:
                    return candidate
            # Move to next month(s)
            for _ in range(12):  # max 12 months to try
                if month == 12:
                    month = 1
                    year += 1
                else:
                    month += 1
                _, max_day = calendar.monthrange(year, month)
                # Use min(day, max_day) to handle months with fewer days
                actual_day = min(day, max_day)
                candidate = date(year, month, actual_day)
                if candidate >= today:
                    return candidate
            return None  # Should never happen

    # 4. Month-day (MM-DD)
    if "-" in text:
        parts = text.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            month_num = int(parts[0])
            day_num = int(parts[1])
            if 1 <= month_num <= 12 and 1 <= day_num <= 31:
                # Try current year first
                try:
                    candidate = date(today.year, month_num, day_num)
                    if candidate >= today:
                        return candidate
                except ValueError:
                    pass
                # Try next year
                try:
                    return date(today.year + 1, month_num, day_num)
                except ValueError:
                    pass

    return None

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

    if not args:
        # Default: next three days
        today = date.today()
        dates = [today + timedelta(days=i) for i in range(3)]
    else:
        dates = []
        for arg in args:
            parsed = parse_smart_date(arg)
            if parsed:
                dates.append(parsed)
            else:
                await update.message.reply_text(
                    f"⚠️ Не удалось распознать дату: «{arg}». "
                    "Используйте ГГГГ-ММ-ДД, день недели (ПН, ВТ, СР, ЧТ, ПТ, СБ, ВС), число (день месяца) или ММ-ДД."
                )
                return  # Stop to avoid a poll with missing dates

    # Sort and remove duplicates (keep unique dates, ascending)
    dates = sorted(set(dates))

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
        "📋 *Команды:*\n"
        "`/poll` – опрос на три ближайших дня\n"
        "`/poll <даты>` – опрос с конкретными датами\n"
        "`/enable_weekly` – включить еженедельный опрос (пн, 12:00 UTC+5) на выходные\n"
        "`/disable_weekly` – выключить еженедельный опрос\n"
        "`/help` – показать подсказку\n\n"
        "📅 *Форматы дат для /poll:*\n"
        "• День недели: `ПН`, `ВТ`, `СР`, `ЧТ`, `ПТ`, `СБ`, `ВС`\n"
        "• Число месяца: `5`, `15`, `28`\n"
        "• Месяц‑день: `7-14` (14 июля), `12-31` (31 декабря)\n"
        "• Год‑месяц‑день: `2026-07-04`\n\n"
        "Примеры:\n"
        "`/poll ПТ СБ ВС` – ближайшие пятница, суббота, воскресенье\n"
        "`/poll 15 20` – ближайшие 15‑е и 20‑е число\n"
        "`/poll 7-14 12-31` – 14 июля и 31 декабря\n"
        "`/poll` (без аргументов) – сегодня, завтра, послезавтра\n\n"
        "Все опросы содержат вариант «Пас», если кто-то не может прийти.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Справка по командам*\n\n"
        "`/poll` – опрос на три ближайших дня\n"
        "`/poll <даты>` – опрос с конкретными датами\n\n"
        "Форматы дат:\n"
        "• Краткий день недели: `ПН`, `ВТ`, `СР`, `ЧТ`, `ПТ`, `СБ`, `ВС`\n"
        "• Число: `5`, `15` (день месяца)\n"
        "• Месяц‑день: `7-14` (14 июля)\n"
        "• Год‑месяц‑день: `2026-07-04`\n\n"
        "Несколько дат можно указывать через пробел.\n\n"
        "`/enable_weekly` – автоопрос каждую неделю (пн, 12:00 UTC+5) на выходные\n"
        "`/disable_weekly` – отключить автоопрос\n\n"
        "Во всех опросах есть опция «Пас» – можно указать, что вы не придёте.",
        parse_mode="Markdown"
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
