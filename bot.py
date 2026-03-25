import logging
import random
import asyncio
import anthropic

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import BOT_TOKEN, ADMIN_CHAT_ID, ANTHROPIC_API_KEY
from database import init_db, save_log, get_stats, get_recent_logs
from prompts import SYSTEM_PROMPT, is_blocked, get_blocked_response, LEVELS, DAILY_TASKS

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Задать вопрос", callback_data="ask")],
        [InlineKeyboardButton("Темы", callback_data="topics")],
        [InlineKeyboardButton("Задание дня", callback_data="daily")],
        [InlineKeyboardButton("Мой уровень", callback_data="mylevel")],
    ]
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n\nЯ тренер по ораторскому искусству.\nНапиши вопрос или выбери раздел:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши вопрос по ораторству и получи ответ.\n\n/daily — задание дня\n/level — твой уровень\n/topics — мои темы")


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Задание дня:\n\n{random.choice(DAILY_TASKS)}")


async def cmd_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import sqlite3
    from config import DB_PATH
    user_id = str(update.effective_user.id)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT message_count, level FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("Напиши первый вопрос!")
        return
    count, level = row
    await update.message.reply_text(f"Уровень: {level}\nВопросов: {count}")


async def cmd_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Мои темы:\n- Публичные выступления\n- Постановка голоса\n- Написание речей\n- Риторика\n- Страх сцены\n- Сторителлинг\n- Питч\n- Язык тела")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("Нет доступа.")
        return
    stats = get_stats()
    await update.message.reply_text(f"Статистика:\nПользователей: {stats['users']}\nВопросов: {stats['total']}\nЗаблокировано: {stats['blocked']}\nСегодня: {stats['today']}")


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("Нет доступа.")
        return
    rows = get_recent_logs(5)
    if not rows:
        await update.message.reply_text("Пока нет логов.")
        return
    for ts, name, username, question, answer, blocked in rows:
        await update.message.reply_text(f"{'БЛОК' if blocked else 'OK'} {name}\n{ts}\n{question[:100]}\n{answer[:200]}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ask":
        await query.message.reply_text("Напиши вопрос по ораторскому искусству!")
    elif query.data == "topics":
        await query.message.reply_text("Темы: выступления, голос, речи, риторика, страх сцены, сторителлинг, питч, язык тела")
    elif query.data == "daily":
        await query.message.reply_text(f"Задание дня:\n\n{random.choice(DAILY_TASKS)}")
    elif query.data == "mylevel":
        import sqlite3
        from config import DB_PATH
        user_id = str(query.from_user.id)
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT message_count, level FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        if not row:
            await query.message.reply_text("Напиши первый вопрос!")
        else:
            count, level = row
            await query.message.reply_text(f"Уровень: {level}, вопросов: {count}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    question = update.message.text

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Вопрос от {user.full_name} (@{user.username or 'нет'}) ID:{user.id}\n{question}")
    except Exception as e:
        logger.warning(f"Ошибка уведомления: {e}")

    if is_blocked(question):
        blocked_msg = get_blocked_response(question)
        await update.message.reply_text(blocked_msg)
        save_log(user.id, user.username, user.full_name, question, blocked_msg, blocked=True)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: claude.messages.create(
            model="claude-opus-4-6", max_tokens=1500, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}]
        ))
        answer = response.content[0].text
    except Exception as e:
        logger.error(f"Ошибка Claude: {e}")
        answer = "Техническая ошибка. Попробуй позже."

    await update.message.reply_text(answer)
    save_log(user.id, user.username, user.full_name, question, answer)

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Ответ бота:\n{answer[:600]}")
    except Exception as e:
        logger.warning(f"Ошибка отправки ответа: {e}")


def main():
    init_db()
    logger.info("База данных инициализирована")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("level", cmd_level))
    app.add_handler(CommandHandler("topics", cmd_topics))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
