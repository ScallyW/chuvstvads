import aiosqlite
import os
from datetime import datetime

DB_PATH = "bot_data.db"


class Database:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        """Инициализация всех таблиц базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица заказов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    description TEXT NOT NULL,
                    budget TEXT,
                    deadline TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_id INTEGER,
                    channel_id INTEGER,
                    assigned_to INTEGER,
                    reject_reason TEXT
                )
            """)
            
            # Таблица отзывов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_id INTEGER
                )
            """)
            
            # Таблица настроек приветствий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    role_id INTEGER,
                    message_template TEXT,
                    is_enabled BOOLEAN DEFAULT 1
                )
            """)
            
            await db.commit()

    # === ORDERS ===
    async def create_order(self, user_id: int, username: str, description: str, 
                          budget: str = None, deadline: str = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO orders (user_id, username, description, budget, deadline)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, description, budget, deadline)
            )
            await db.commit()
            return cursor.lastrowid

    async def update_order_message_id(self, order_id: int, message_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE orders SET message_id = ? WHERE id = ?",
                (message_id, order_id)
            )
            await db.commit()

    async def update_order_ticket(self, order_id: int, channel_id: int = None, 
                                   status: str = None, assigned_to: int = None,
                                   reject_reason: str = None):
        """Обновление данных тикета заказа"""
        async with aiosqlite.connect(self.db_path) as db:
            if channel_id:
                await db.execute(
                    "UPDATE orders SET channel_id = ? WHERE id = ?",
                    (channel_id, order_id)
                )
            if status:
                await db.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (status, order_id)
                )
            if assigned_to:
                await db.execute(
                    "UPDATE orders SET assigned_to = ? WHERE id = ?",
                    (assigned_to, order_id)
                )
            if reject_reason:
                await db.execute(
                    "UPDATE orders SET reject_reason = ? WHERE id = ?",
                    (reject_reason, order_id)
                )
            await db.commit()

    async def get_order_by_channel(self, channel_id: int):
        """Получить заказ по ID канала тикета"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM orders WHERE channel_id = ?", (channel_id,)
            )
            return await cursor.fetchone()

    async def get_order(self, order_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            )
            return await cursor.fetchone()

    # === REVIEWS ===
    async def create_review(self, user_id: int, username: str, rating: int, text: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO reviews (user_id, username, rating, text)
                   VALUES (?, ?, ?, ?)""",
                (user_id, username, rating, text)
            )
            await db.commit()
            return cursor.lastrowid

    async def update_review_message_id(self, review_id: int, message_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE reviews SET message_id = ? WHERE id = ?",
                (message_id, review_id)
            )
            await db.commit()

    async def get_user_reviews(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM reviews WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return await cursor.fetchall()

    # === WELCOME SETTINGS ===
    async def set_welcome_settings(self, guild_id: int, channel_id: int = None,
                                   role_id: int = None, message_template: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO welcome_settings 
                   (guild_id, channel_id, role_id, message_template)
                   VALUES (?, ?, ?, ?)""",
                (guild_id, channel_id, role_id, message_template)
            )
            await db.commit()

    async def get_welcome_settings(self, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM welcome_settings WHERE guild_id = ?",
                (guild_id,)
            )
            return await cursor.fetchone()


# Глобальный экземпляр базы данных
db = Database()
