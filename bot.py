import logging
import random
import anthropic

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    CallbackQueryHandler, Filters, CallbackContext
)

from config import BOT_TOKEN, ADMIN_CHAT_ID, ANTHROPIC_API_KEY
from database import init_db, save_log, get_stats, get_recent_logs
from prompts import SYSTEM_PROMPT, is_blocked, get_blocked_response, LEVELS, DAILY_TASKS

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def cmd_start(update: Update, context: CallbackContext):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🎙 Задать вопрос", callback_data="ask")],
        [InlineKeyboardButton("📚 Темы которые я знаю", callback_data="topics")],
        [InlineKeyboardButton("🏋 Задание дня", callback_data="daily")],
        [InlineKeyboardButton("🏆 Мой уровень", callback_data="mylevel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный тренер по ораторскому искусству 🎤\n\n"
        "Помогу тебе:\n"
        "• Составить и отточить речь\n"
        "• Поставить голос и дыхание\n"
        "• Победить страх сцены\n"
        "• Освоить риторику и сторителлинг\n"
        "• Подготовиться к выступлению\n\n"
        "Просто напиши свой вопрос — или выбери раздел ниже 👇",
        reply_markup=reply_markup
    )


def cmd_help(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📖 Что я умею:\n\n"
        "Просто напиши вопрос — и получи развёрнутый ответ.\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/daily — задание дня\n"
        "/level — твой уровень оратора\n"
        "/topics — темы которые я знаю\n\n"
        "Темы: ораторство, голос, речи, риторика, страх сцены, сторителлинг, питч, презентации."
    )


def cmd_daily(update: Update, context: CallbackContext):
    task = random.choice(DAILY_TASKS)
    update.message.reply_text(f"🏋 Задание дня:\n\n{task}\n\nВыполни и расскажи как прошло!")


def cmd_level(update: Update, context: CallbackContext):
    import sqlite3
    from config import DB_PATH
    user_id = str(update.effective_user.id)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT message_count, level FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        update.message.reply_text("Напиши хоть один вопрос — и я начну отслеживать твой прогресс! 🌱")
        return
    count, level = row
    emoji = LEVELS.get(level, {}).get("emoji", "🎤")
    levels_list = list(LEVELS.items())
    next_level = ""
    for i, (name, data) in enumerate(levels_list):
        if name == level and i + 1 < len(levels_list):
            next_name, next_data = levels_list[i + 1]
            next_level = f"\nДо уровня {next_name} осталось {next_data['min'] - count} вопросов."
            break
    update.message.reply_text(
        f"{emoji} Твой уровень: {level}\n\nЗадано вопросов: {count}{next_level}"
    )


def cmd_topics(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📚 Темы, в которых я эксперт:\n\n"
        "🎤 Публичные выступления\n"
        "🔊 Постановка голоса и дыхания\n"
        "📝 Написание речей и сценариев\n"
        "🧠 Риторика и убеждение\n"
        "😰 Страх сцены — как победить\n"
        "📖 Сторителлинг и истории\n"
        "🚀 Питч для инвесторов\n"
        "🎓 Защита диплома / доклад\n"
        "🥂 Тосты и поздравительные речи\n"
        "👁 Язык тела и невербалика\n"
        "🏆 Разбор великих ораторов и речей\n\n"
        "Напиши любой вопрос по этим темам!"
    )


def cmd_admin(update: Update, context: CallbackContext):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        update.message.reply_text("⛔ Нет доступа.")
        return
    stats = get_stats()
    top5_text = ""
    for name, username, count, level in stats["top5"]:
        uname = f"@{username}" if username else "без username"
        top5_text += f"  • {name} ({uname}) — {count} вопр., {level}\n"
    update.message.reply_text(
        f"📊 Статистика бота\n\n"
        f"👥 Всего пользователей: {stats['users']}\n"
        f"💬 Всего вопросов: {stats['total']}\n"
        f"🚫 Заблокировано: {stats['blocked']}\n"
        f"📅 Сегодня: {stats['today']}\n\n"
        f"🏆 Топ-5 активных:\n{top5_text}"
    )


def cmd_logs(update: Update, context: CallbackContext):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        update.message.reply_text("⛔ Нет доступа.")
        return
    rows = get_recent_logs(10)
    if not rows:
        update.message.reply_text("Пока нет логов.")
        return
    for row in rows:
        ts, name, username, question, answer, blocked = row
        flag = "🚫" if blocked else "✅"
        text = (
            f"{flag} {name} (@{username or '—'})\n"
            f"🕐 {ts}\n"
            f"❓ {question[:200]}\n"
            f"🤖 {answer[:300]}{'...' if len(answer) > 300 else ''}"
        )
        update.message.reply_text(text)


def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if query.data == "ask":
        query.message.reply_text("✍️ Напиши свой вопрос по ораторскому искусству!")
    elif query.data == "topics":
        query.message.reply_text(
            "📚 Темы, в которых я эксперт:\n\n"
            "🎤 Публичные выступления\n"
            "🔊 Постановка голоса и дыхания\n"
            "📝 Написание речей и сценариев\n"
            "🧠 Риторика и убеждение\n"
            "😰 Страх сцены — как победить\n"
            "📖 Сторителлинг и истории\n"
            "🚀 Питч для инвесторов\n"
            "Напиши любой вопрос!"
        )
    elif query.data == "daily":
        task = random.choice(DAILY_TASKS)
        query.message.reply_text(f"🏋 Задание дня:\n\n{task}")
    elif query.data == "mylevel":
        import sqlite3
        from config import DB_PATH
        user_id = str(query.from_user.id)
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT message_count, level FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()
        if not row:
            query.message.reply_text("Напиши хоть один вопрос — и я начну отслеживать прогресс! 🌱")
        else:
            count, level = row
            emoji = LEVELS.get(level, {}).get("emoji", "🎤")
            query.message.reply_text(f"{emoji} Твой уровень: {level}\nВопросов задано: {count}")


def handle_message(update: Update, context: CallbackContext):
    user = update.effective_user
    question = update.message.text

    try:
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📨 Новый вопрос\n👤 {user.full_name} (@{user.username or 'нет'})\n🆔 {user.id}\n❓ {question}"
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить админа: {e}")

    if is_blocked(question):
        blocked_msg = get_blocked_response(question)
        update.message.reply_text(blocked_msg)
        save_log(user.id, user.username, user.full_name, question, blocked_msg, blocked=True)
        try:
            context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="🚫 Заблокировано — тема вне ораторства")
        except Exception:
            pass
        return

    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = claude.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}]
        )
        answer = response.content[0].text
    except Exception as e:
        logger.error(f"Ошибка Claude API: {e}")
        answer = "⚠️ Произошла техническая ошибка. Попробуйте чуть позже."

    update.message.reply_text(answer)
    save_log(user.id, user.username, user.full_name, question, answer)

    try:
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🤖 Ответ бота:\n{answer[:600]}{'...' if len(answer) > 600 else ''}"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить ответ админу: {e}")


def main():
    init_db()
    logger.info("✅ База данных инициализирована")

    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start",  cmd_start))
    dp.add_handler(CommandHandler("help",   cmd_help))
    dp.add_handler(CommandHandler("daily",  cmd_daily))
    dp.add_handler(CommandHandler("level",  cmd_level))
    dp.add_handler(CommandHandler("topics", cmd_topics))
    dp.add_handler(CommandHandler("admin",  cmd_admin))
    dp.add_handler(CommandHandler("logs",   cmd_logs))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    logger.info("🚀 Бот запущен!")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
