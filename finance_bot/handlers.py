import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from budget import BudgetAdvisor
from categorize import ExpenseCategorizer
from db import Database
from ocr import OCRService


class RateLimiterProtocol(Protocol):
    def check(self, user_id: int, timestamp: float) -> bool:
        ...


@dataclass
class PendingExpense:
    expense_id: int
    name: str
    amount: float
    category: str


DEFAULT_CATEGORIES = ["еда", "транспорт", "покупки", "прочее", "здоровье", "развлечения"]


def register_handlers(
    dp: Dispatcher,
    bot: Bot,
    database: Database,
    ocr_service: OCRService,
    categorizer: ExpenseCategorizer,
    budget_advisor: BudgetAdvisor,
    rate_limiter: RateLimiterProtocol,
) -> None:
    router = Router()

    pending_expenses: Dict[int, Dict[int, PendingExpense]] = {}

    async def ensure_user(message: Message) -> Optional[int]:
        if not message.from_user:
            await message.answer("Не удалось определить пользователя.")
            return None
        tg_id = message.from_user.id
        full_name = message.from_user.full_name
        try:
            user = await database.get_or_create_user(tg_id, full_name)
        except Exception:
            logging.exception("Failed to get or create user")
            await message.answer("Произошла ошибка при обращении к базе данных.")
            return None
        return user["id"]

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        user_id = await ensure_user(message)
        if user_id is None:
            return
        await message.answer(
            "👋 Привет! Я ваш финансовый помощник.\n"
            "Отправьте /income <сумма>, чтобы сохранить доход, или пришлите фото чека — я распознаю траты."
        )

    @router.message(Command("income"))
    async def handle_income(message: Message, command: CommandObject) -> None:
        user_id = await ensure_user(message)
        if user_id is None or not message.from_user:
            return

        args = command.args or ""
        args = args.replace(",", ".").strip()
        try:
            amount = float(args)
        except ValueError:
            await message.answer("Пожалуйста, укажите сумму после команды, например: /income 85000")
            return

        try:
            await database.update_income(message.from_user.id, amount)
        except Exception:
            logging.exception("Failed to update income")
            await message.answer("Не удалось сохранить доход. Попробуйте позже.")
            return

        summary = await database.get_expense_summary(message.from_user.id)
        budget_text = await budget_advisor.generate_budget(amount, summary)

        await message.answer(
            "Доход сохранён!\n"
            f"Текущий доход: <b>{amount:.2f}</b> ₽\n\n"
            f"Рекомендации по бюджету:\n{budget_text}"
        )

    @router.message(F.photo)
    async def handle_receipt(message: Message) -> None:
        if not message.from_user:
            return

        now = time.time()
        if not rate_limiter.check(message.from_user.id, now):
            await message.answer("Пожалуйста, не отправляйте сообщения слишком часто.")
            return

        user_id = await ensure_user(message)
        if user_id is None:
            return

        await message.answer("⏳ Обрабатываю чек, пожалуйста подождите...")
        try:
            items = await ocr_service.process_receipt(message)
        except Exception:
            logging.exception("OCR failed")
            await message.answer("Не удалось распознать чек. Попробуйте фото лучшего качества.")
            return

        if not items:
            await message.answer("Не удалось найти покупки на чеке. Попробуйте ещё раз.")
            return

        try:
            categorized_items = await categorizer.classify_items(items)
        except Exception:
            logging.exception("Categorization failed")
            await message.answer("Ошибка при классификации расходов. Попробуйте позже.")
            return

        user_pending: Dict[int, PendingExpense] = {}
        summary_lines: List[str] = []
        total = 0.0
        for item in categorized_items:
            try:
                expense_id = await database.add_expense(
                    telegram_id=message.from_user.id,
                    name=item.name,
                    amount=item.amount,
                    category=item.category,
                )
            except Exception:
                logging.exception("Failed to save expense")
                await message.answer("Ошибка при сохранении данных. Попробуйте позже.")
                return
            user_pending[expense_id] = PendingExpense(expense_id, item.name, item.amount, item.category)
            summary_lines.append(f"• {item.name} — {item.amount:.2f} ₽ ({item.category})")
            total += item.amount

        pending_expenses[message.from_user.id] = user_pending

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="edit_yes"),
                    InlineKeyboardButton(text="Нет", callback_data="edit_no"),
                ]
            ]
        )

        await message.answer(
            "✅ Расходы сохранены:\n" + "\n".join(summary_lines) + f"\n\nВсего: <b>{total:.2f}</b> ₽\n"
            "Хотите изменить категории?",
            reply_markup=keyboard,
        )

    @router.callback_query(F.data == "edit_no")
    async def handle_edit_no(callback: CallbackQuery) -> None:
        await callback.answer("Отлично! Категории оставлены без изменений.", show_alert=False)
        await callback.message.edit_reply_markup(reply_markup=None)

    @router.callback_query(F.data == "edit_yes")
    async def handle_edit_yes(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return

        user_items = pending_expenses.get(callback.from_user.id)
        if not user_items:
            await callback.answer("Нет элементов для редактирования.", show_alert=True)
            return

        builder = InlineKeyboardBuilder()
        for expense in user_items.values():
            builder.button(
                text=f"{expense.name} ({expense.category})",
                callback_data=f"edit_item:{expense.expense_id}",
            )
        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(text="Готово", callback_data="edit_done")
        )

        try:
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        except TelegramBadRequest:
            logging.warning("Failed to edit reply markup, sending new message")
            await callback.message.answer("Выберите товар для изменения категории:", reply_markup=builder.as_markup())
        await callback.answer()

    @router.callback_query(F.data == "edit_done")
    async def handle_edit_done(callback: CallbackQuery) -> None:
        await callback.answer("Категории обновлены.")
        await callback.message.edit_reply_markup(reply_markup=None)

    @router.callback_query(F.data.startswith("edit_item:"))
    async def handle_edit_item(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return

        try:
            expense_id = int(callback.data.split(":", 1)[1])
        except (ValueError, AttributeError):
            await callback.answer("Некорректный запрос.", show_alert=True)
            return

        user_items = pending_expenses.get(callback.from_user.id)
        if not user_items or expense_id not in user_items:
            await callback.answer("Расход не найден.", show_alert=True)
            return

        builder = InlineKeyboardBuilder()
        for category in DEFAULT_CATEGORIES:
            builder.button(
                text=category.capitalize(),
                callback_data=f"setcat:{expense_id}:{category}",
            )
        builder.adjust(2)
        await callback.message.answer(
            f"Выберите категорию для <b>{user_items[expense_id].name}</b>:",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("setcat:"))
    async def handle_set_category(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        try:
            _, expense_id_str, category = callback.data.split(":", 2)
            expense_id = int(expense_id_str)
        except (ValueError, AttributeError):
            await callback.answer("Некорректная категория.", show_alert=True)
            return

        user_items = pending_expenses.get(callback.from_user.id)
        if not user_items or expense_id not in user_items:
            await callback.answer("Расход не найден.", show_alert=True)
            return

        expense = user_items[expense_id]
        old_category = expense.category
        if old_category == category:
            await callback.answer("Категория уже установлена.")
            return

        try:
            await database.update_expense_category(expense_id, category)
            await database.save_feedback(
                telegram_id=callback.from_user.id,
                item_name=expense.name,
                old_category=old_category,
                new_category=category,
            )
        except Exception:
            logging.exception("Failed to update category")
            await callback.answer("Не удалось обновить категорию.", show_alert=True)
            return

        expense.category = category
        await callback.answer("Категория обновлена.")

    dp.include_router(router)
