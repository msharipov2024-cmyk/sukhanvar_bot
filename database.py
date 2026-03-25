import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT,
            user_id       TEXT,
            username      TEXT,
            full_name     TEXT,
            question      TEXT,
            bot_answer    TEXT,
            was_blocked   INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       TEXT PRIMARY KEY,
            username      TEXT,
            full_name     TEXT,
            first_seen    TEXT,
            message_count INTEGER DEFAULT 0,
            level         TEXT DEFAULT 'Новичок'
        )
    """)
    conn.commit()
    conn.close()


def save_log(user_id, username, full_name, question, answer, blocked=False):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO logs (timestamp, user_id, username, full_name, question, bot_answer, was_blocked)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        str(user_id), username or "", full_name or "",
        question, answer, int(blocked)
    ))
    # Обновить или создать пользователя
    conn.execute("""
        INSERT INTO users (user_id, username, full_name, first_seen, message_count)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(user_id) DO UPDATE SET
            message_count = message_count + 1,
            username = excluded.username,
            full_name = excluded.full_name
    """, (str(user_id), username or "", full_name or "",
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    # Обновить уровень
    row = conn.execute("SELECT message_count FROM users WHERE user_id=?", (str(user_id),)).fetchone()
    if row:
        count = row[0]
        level = "Новичок"
        if count >= 100: level = "Легенда"
        elif count >= 50: level = "Мастер"
        elif count >= 20: level = "Оратор"
        elif count >= 5:  level = "Спикер"
        conn.execute("UPDATE users SET level=? WHERE user_id=?", (level, str(user_id)))
    conn.commit()
    conn.close()


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    total     = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    blocked   = conn.execute("SELECT COUNT(*) FROM logs WHERE was_blocked=1").fetchone()[0]
    users     = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today     = conn.execute(
        "SELECT COUNT(*) FROM logs WHERE timestamp LIKE ?",
        (datetime.now().strftime("%Y-%m-%d") + "%",)
    ).fetchone()[0]
    top5 = conn.execute("""
        SELECT full_name, username, message_count, level
        FROM users ORDER BY message_count DESC LIMIT 5
    """).fetchall()
    conn.close()
    return {"total": total, "blocked": blocked, "users": users, "today": today, "top5": top5}


def get_recent_logs(limit=10):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT timestamp, full_name, username, question, bot_answer, was_blocked
        FROM logs ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows
