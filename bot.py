import logging
import random
import anthropic

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from config import BOT_TOKEN, ADMIN_CHAT_ID, ANTHROPIC_API_KEY
from database import init_db, save_log, get_stats, get_recent_logs
from prompts import SYSTEM_PROMPT, is_blocked, get_blocked_response, LEVELS, DAILY_TASKS

# ── Логирование ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Claude клиент ────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# =============================================
# /start — приветствие
# =============================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🎙 Задать вопрос", callback_data="ask")],
        [InlineKeyboardButton("📚 Темы которые я знаю", callback_data="topics")],
        [InlineKeyboardButton("🏋 Задание дня", callback_data="daily")],
        [InlineKeyboardButton("🏆 Мой уровень", callback_data="mylevel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный тренер по *ораторскому искусству* 🎤\n\n"
        "Помогу тебе:\n"
        "• Составить и отточить речь\n"
        "• Поставить голос и дыхание\n"
        "• Победить страх сцены\n"
        "• Освоить риторику и сторителлинг\n"
        "• Подготовиться к выступлению\n\n"
        "Просто напиши свой вопрос — или выбери раздел ниже 👇",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# =============================================
# /help
# =============================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Что я умею:*\n\n"
        "Просто напиши вопрос — и получи развёрнутый ответ.\n\n"
        "*Команды:*\n"
        "/start — главное меню\n"
        "/daily — задание дня\n"
        "/level — твой уровень оратора\n"
        "/topics — темы которые я знаю\n\n"
        "*Темы:* ораторство, голос, речи, риторика, страх сцены, сторителлинг, питч, презентации.",
        parse_mode="Markdown"
    )

# =============================================
# /daily — задание дня
# =============================================
async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = random.choice(DAILY_TASKS)
    await update.message.reply_text(
        f"*🏋 Задание дня:*\n\n{task}\n\n"
        "_Выполни и расскажи как прошло — напиши мне!_",
        parse_mode="Markdown"
    )

# =============================================
# /level — уровень пользователя
# =============================================
async def cmd_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database import get_recent_logs
    import sqlite3
    from config import DB_PATH
    user_id = str(update.effective_user.id)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT message_count, level FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("Напиши хоть один вопрос — и я начну отслеживать твой прогресс! 🌱")
        return
    count, level = row
    emoji = LEVELS.get(level, {}).get("emoji", "🎤")
    # Найти следующий уровень
    levels_list = list(LEVELS.items())
    next_level = None
    for i, (name, data) in enumerate(levels_list):
        if name == level and i + 1 < len(levels_list):
            next_name, next_data = levels_list[i + 1]
            next_level = f"До уровня *{next_name}* осталось *{next_data['min'] - count}* вопросов."
            break
    text = (
        f"{emoji} *Твой уровень: {level}*\n\n"
        f"Задано вопросов: *{count}*\n"
    )
    if next_level:
        text += f"\n{next_level}"
    await update.message.reply_text(text, parse_mode="Markdown")

# =============================================
# /topics — список тем
# =============================================
async def cmd_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Темы, в которых я эксперт:*\n\n"
        "🎤 Публичные выступления\n"
        "🔊 Постановка голоса и дыхания\n"
        "📝 Написание речей и сценариев\n"
        "🧠 Риторика и убеждение\n"
        "😰 Страх сцены — как победить\n"
        "📖 Сторителлинг и истории\n"
        "🚀 Питч для инвесторов\n"
        "🎓 Защита диплома / доклад\n"
        "🥂 Тосты и поздравительные речи\n"
        "🕵 Слова-паразиты — как убрать\n"
        "👁 Язык тела и невербалика\n"
        "🏆 Разбор великих ораторов и речей\n\n"
        "_Напиши любой вопрос по этим темам!_",
        parse_mode="Markdown"
    )

# =============================================
# /admin — статистика (только для тебя)
# =============================================
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    stats = get_stats()
    top5_text = ""
    for name, username, count, level in stats["top5"]:
        uname = f"@{username}" if username else "без username"
        top5_text += f"  • {name} ({uname}) — {count} вопр., {level}\n"
    await update.message.reply_text(
        f"📊 *Статистика бота*\n\n"
        f"👥 Всего пользователей: *{stats['users']}*\n"
        f"💬 Всего вопросов: *{stats['total']}*\n"
        f"🚫 Заблокировано: *{stats['blocked']}*\n"
        f"📅 Сегодня: *{stats['today']}*\n\n"
        f"🏆 *Топ-5 активных:*\n{top5_text}",
        parse_mode="Markdown"
    )

# =============================================
# /logs — последние 10 вопросов (только для тебя)
# =============================================
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    rows = get_recent_logs(10)
    if not rows:
        await update.message.reply_text("Пока нет логов.")
        return
    for row in rows:
        ts, name, username, question, answer, blocked = row
        flag = "🚫" if blocked else "✅"
        text = (
            f"{flag} *{name}* (@{username or '—'})\n"
            f"🕐 {ts}\n"
            f"❓ {question[:200]}\n"
            f"🤖 {answer[:300]}{'...' if len(answer) > 300 else ''}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

# =============================================
# Inline кнопки
# =============================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ask":
        await query.message.reply_text("✍️ Напиши свой вопрос по ораторскому искусству!")
    elif query.data == "topics":
        await cmd_topics(query, context)
    elif query.data == "daily":
        task = random.choice(DAILY_TASKS)
        await query.message.reply_text(
            f"*🏋 Задание дня:*\n\n{task}",
            parse_mode="Markdown"
        )
    elif query.data == "mylevel":
        await cmd_level(query, context)

# =============================================
# Основной обработчик сообщений
# =============================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    question = update.message.text

    # 1. Уведомить тебя сразу о новом вопросе
    notif = (
        f"📨 *Новый вопрос*\n"
        f"👤 {user.full_name} (@{user.username or 'нет'})\n"
        f"🆔 ID: `{user.id}`\n"
        f"❓ {question}"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=notif, parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить админа: {e}")

    # 2. Проверка фильтра
    if is_blocked(question):
        blocked_msg = get_blocked_response(question)
        await update.message.reply_text(blocked_msg)
        save_log(user.id, user.username, user.full_name, question, blocked_msg, blocked=True)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🚫 *Заблокировано* — тема вне ораторства",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    # 3. Индикатор печатания
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # 4. Запрос к Claude
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

    # 5. Отправить ответ пользователю
    await update.message.reply_text(answer)

    # 6. Сохранить в базу
    save_log(user.id, user.username, user.full_name, question, answer)

    # 7. Уведомить тебя об ответе
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"🤖 *Ответ бота:*\n"
                f"{answer[:600]}{'...' if len(answer) > 600 else ''}"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить ответ админу: {e}")


# =============================================
# ЗАПУСК
# =============================================
def main():
    init_db()
    logger.info("✅ База данных инициализирована")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("daily",  cmd_daily))
    app.add_handler(CommandHandler("level",  cmd_level))
    app.add_handler(CommandHandler("topics", cmd_topics))
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(CommandHandler("logs",   cmd_logs))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
