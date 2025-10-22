import aiosqlite
from typing import Dict, Optional


class Database:
    def __init__(self, path: str) -> None:
        self._path = path

    async def init_models(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    income REAL DEFAULT 0,
                    name TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT DEFAULT CURRENT_TIMESTAMP,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    old_category TEXT,
                    new_category TEXT,
                    date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            await db.commit()

    async def get_or_create_user(self, telegram_id: int, name: str) -> Dict[str, object]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, telegram_id, income, name FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row:
                return dict(row)
            cursor = await db.execute(
                "INSERT INTO users (telegram_id, name) VALUES (?, ?)",
                (telegram_id, name),
            )
            await db.commit()
            user_id = cursor.lastrowid
            return {"id": user_id, "telegram_id": telegram_id, "income": 0.0, "name": name}

    async def update_income(self, telegram_id: int, amount: float) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE users SET income = ? WHERE telegram_id = ?",
                (amount, telegram_id),
            )
            await db.commit()

    async def add_expense(self, telegram_id: int, name: str, amount: float, category: str) -> int:
        user_id = await self._get_user_id(telegram_id)
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "INSERT INTO expenses (user_id, name, amount, category) VALUES (?, ?, ?, ?)",
                (user_id, name, amount, category),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_expense_category(self, expense_id: int, category: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE expenses SET category = ? WHERE id = ?",
                (category, expense_id),
            )
            await db.commit()

    async def save_feedback(
        self,
        telegram_id: int,
        item_name: str,
        old_category: Optional[str],
        new_category: Optional[str],
    ) -> None:
        user_id = await self._get_user_id(telegram_id)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO feedback (user_id, item_name, old_category, new_category) VALUES (?, ?, ?, ?)",
                (user_id, item_name, old_category, new_category),
            )
            await db.commit()

    async def get_expense_summary(self, telegram_id: int) -> Dict[str, float]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT category, SUM(amount) as total
                FROM expenses
                JOIN users ON users.id = expenses.user_id
                WHERE users.telegram_id = ?
                GROUP BY category
                """,
                (telegram_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return {row["category"]: row["total"] for row in rows}

    async def _get_user_id(self, telegram_id: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if not row:
            raise ValueError("User not found")
        return int(row["id"])
