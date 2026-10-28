"""Модуль работы с базой данных SQLite.

Поддерживает:
1. Асинхронные методы через aiosqlite (для Telegram-бота и фонового планировщика).
2. Синхронные методы через sqlite3 (для десктопного GUI на Tkinter).
3. Режим WAL (Write-Ahead Logging) для безопасного одновременного доступа.
"""

import aiosqlite
import sqlite3
import datetime
from typing import List, Dict, Any, Optional

INIT_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    join_code TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    notifications_enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT NOT NULL,
    created_by_id INTEGER,
    created_by_name TEXT,
    reminded_24h INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_completions (
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    deadline_id INTEGER NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, deadline_id)
);
"""


class AsyncDatabase:
    """Асинхронный клиент БД для бота и фонового планировщика."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(INIT_SQL)
            await db.commit()

    # --- ГРУППЫ ---
    async def create_group(self, name: str, join_code: str) -> Optional[int]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "INSERT INTO groups (name, join_code) VALUES (?, ?)",
                    (name.strip(), join_code.strip().upper()),
                )
                await db.commit()
                return cursor.lastrowid
        except Exception:
            return None

    async def get_group_by_code(self, join_code: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM groups WHERE join_code = ?", (join_code.strip().upper(),)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_group_by_id(self, group_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_groups(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT g.*, COUNT(u.telegram_id) as member_count 
                   FROM groups g 
                   LEFT JOIN users u ON u.group_id = g.id 
                   GROUP BY g.id ORDER BY g.name"""
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # --- ПОЛЬЗОВАТЕЛИ ---
    async def get_or_create_user(
        self, telegram_id: int, username: str = "", full_name: str = ""
    ) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    "UPDATE users SET username = ?, full_name = ? WHERE telegram_id = ?",
                    (username, full_name, telegram_id),
                )
                await db.commit()
                return dict(row)

            await db.execute(
                "INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
                (telegram_id, username, full_name),
            )
            await db.commit()
            return {
                "telegram_id": telegram_id,
                "username": username,
                "full_name": full_name,
                "group_id": None,
                "notifications_enabled": 1,
            }

    async def set_user_group(self, telegram_id: int, group_id: Optional[int]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET group_id = ? WHERE telegram_id = ?",
                (group_id, telegram_id),
            )
            await db.commit()

    async def get_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE group_id = ? AND notifications_enabled = 1",
                (group_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # --- ДЕДЛАЙНЫ ---
    async def add_deadline(
        self,
        group_id: int,
        subject: str,
        title: str,
        description: str,
        due_date: str,
        created_by_id: int,
        created_by_name: str,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO deadlines 
                   (group_id, subject, title, description, due_date, created_by_id, created_by_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    group_id,
                    subject.strip(),
                    title.strip(),
                    description.strip() if description else "",
                    due_date.strip(),
                    created_by_id,
                    created_by_name,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_group_deadlines(
        self, group_id: int, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Возвращает дедлайны группы с отметкой, сдал ли конкретный студент."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = """
                SELECT d.*, 
                       CASE WHEN uc.user_id IS NOT NULL THEN 1 ELSE 0 END AS is_completed
                FROM deadlines d
                LEFT JOIN user_completions uc 
                       ON uc.deadline_id = d.id AND uc.user_id = ?
                WHERE d.group_id = ?
                ORDER BY d.due_date ASC
            """
            cursor = await db.execute(sql, (user_id, group_id))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_deadline_by_id(self, deadline_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM deadlines WHERE id = ?", (deadline_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_deadline(self, deadline_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
            await db.commit()
            return True

    # --- ОТМЕТКА О СДАЧЕ («Я сдал») ---
    async def toggle_completion(self, user_id: int, deadline_id: int) -> bool:
        """Переключает статус: сдал / не сдал. Возвращает True, если теперь сдан."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM user_completions WHERE user_id = ? AND deadline_id = ?",
                (user_id, deadline_id),
            )
            exists = await cursor.fetchone()
            if exists:
                await db.execute(
                    "DELETE FROM user_completions WHERE user_id = ? AND deadline_id = ?",
                    (user_id, deadline_id),
                )
                await db.commit()
                return False
            else:
                await db.execute(
                    "INSERT INTO user_completions (user_id, deadline_id) VALUES (?, ?)",
                    (user_id, deadline_id),
                )
                await db.commit()
                return True

    async def is_completed(self, user_id: int, deadline_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM user_completions WHERE user_id = ? AND deadline_id = ?",
                (user_id, deadline_id),
            )
            return (await cursor.fetchone()) is not None

    # --- ПЛАНИРОВЩИК / НАПОМИНАНИЯ (ЗА 24 ЧАСА) ---
    async def get_deadlines_for_24h_reminder(self):
        """Находит дедлайны, у которых срок наступает менее чем через 24 часа."""
        import datetime
        now = datetime.datetime.now()
        in_24h = now + datetime.timedelta(hours=24)

        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        in_24h_str = in_24h.strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT d.*, g.name as group_name 
                   FROM deadlines d JOIN groups g ON g.id = d.group_id
                   WHERE d.reminded_24h = 0 AND d.due_date > ? AND d.due_date <= ?""",
                (now_str, in_24h_str),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def mark_reminder_sent(self, deadline_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE deadlines SET reminded_24h = 1 WHERE id = ?", (deadline_id,))
            await db.commit()

class SyncDatabase:
    """Синхронный клиент БД для десктопного GUI на CustomTkinter."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_init()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _ensure_init(self):
        with self._get_connection() as conn:
            conn.executescript(INIT_SQL)
            conn.commit()
            # Создаем начальную демо-группу и дедлайн, если база пустая
            cnt = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
            if cnt == 0:
                conn.execute(
                    "INSERT INTO groups (name, join_code) VALUES (?, ?)",
                    ("ИВТ-21 (Демо)", "IVT21")
                )
                conn.commit()
                group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                due_demo = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d 18:00:00")
                conn.execute(
                    """INSERT INTO deadlines (group_id, subject, title, description, due_date, created_by_id, created_by_name)
                       VALUES (?, ?, ?, ?, ?, 0, ?)""",
                    (group_id, "Математический анализ", "Лабораторная работа №1", "Вариант 3, сдать в ауд. 402", due_demo, "Староста (Демо)")
                )
                conn.commit()

    def get_all_groups(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT g.*, COUNT(u.telegram_id) as member_count 
                   FROM groups g 
                   LEFT JOIN users u ON u.group_id = g.id 
                   GROUP BY g.id ORDER BY g.name"""
            )
            return [dict(r) for r in cursor.fetchall()]

    def create_group(self, name: str, join_code: str) -> Optional[int]:
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "INSERT INTO groups (name, join_code) VALUES (?, ?)",
                    (name.strip(), join_code.strip().upper()),
                )
                conn.commit()
                return cur.lastrowid
        except Exception:
            return None

    def get_all_deadlines(self, group_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if group_id:
                sql = """SELECT d.*, g.name as group_name 
                         FROM deadlines d 
                         JOIN groups g ON g.id = d.group_id 
                         WHERE d.group_id = ?
                         ORDER BY d.due_date ASC"""
                cur = conn.execute(sql, (group_id,))
            else:
                sql = """SELECT d.*, g.name as group_name 
                         FROM deadlines d 
                         JOIN groups g ON g.id = d.group_id 
                         ORDER BY d.due_date ASC"""
                cur = conn.execute(sql)
            return [dict(r) for r in cur.fetchall()]

    def add_deadline(
        self,
        group_id: int,
        subject: str,
        title: str,
        description: str,
        due_date: str,
        author: str = "Панель администратора (GUI)",
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO deadlines 
                   (group_id, subject, title, description, due_date, created_by_id, created_by_name)
                   VALUES (?, ?, ?, ?, ?, 0, ?)""",
                (
                    group_id,
                    subject.strip(),
                    title.strip(),
                    description.strip() if description else "",
                    due_date.strip(),
                    author,
                ),
            )
            conn.commit()
            return cur.lastrowid

    def delete_deadline(self, deadline_id: int):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        with self._get_connection() as conn:
            groups_cnt = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
            users_cnt = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            deadlines_cnt = conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            active_cnt = conn.execute(
                "SELECT COUNT(*) FROM deadlines WHERE due_date >= ?", (now_str,)
            ).fetchone()[0]
            return {
                "groups": groups_cnt,
                "users": users_cnt,
                "deadlines": deadlines_cnt,
                "active_deadlines": active_cnt,
            }