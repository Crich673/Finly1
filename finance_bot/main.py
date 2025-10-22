import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from db import Database
from handlers import register_handlers
from ocr import OCRService
from categorize import ExpenseCategorizer
from budget import BudgetAdvisor


class RateLimiter:
    """Very simple in-memory rate limiter."""

    def __init__(self, cooldown_seconds: float = 1.0) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._timestamps: dict[int, float] = {}

    def check(self, user_id: int, timestamp: float) -> bool:
        """Returns True if the user is allowed to proceed."""
        last_time = self._timestamps.get(user_id)
        if last_time is not None and timestamp - last_time < self.cooldown_seconds:
            return False
        self._timestamps[user_id] = timestamp
        return True


async def on_startup(dispatcher: Dispatcher, database: Database) -> None:
    await database.init_models()
    logging.info("Database initialized")


async def main() -> None:
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set in environment")

    db_path = os.getenv("DB_PATH", "finance_bot.db")
    openai_key: Optional[str] = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        logging.warning("OPENAI_API_KEY is not configured; GPT features will fail")

    storage = MemoryStorage()
    bot = Bot(token=bot_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=storage)

    database = Database(db_path)
    ocr_service = OCRService()
    categorizer = ExpenseCategorizer(openai_api_key=openai_key)
    budget_advisor = BudgetAdvisor(openai_api_key=openai_key)
    rate_limiter = RateLimiter()

    register_handlers(
        dp=dp,
        bot=bot,
        database=database,
        ocr_service=ocr_service,
        categorizer=categorizer,
        budget_advisor=budget_advisor,
        rate_limiter=rate_limiter,
    )

    await on_startup(dp, database)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
