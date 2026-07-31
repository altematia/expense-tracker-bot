"""A tiny personal expense tracker Telegram bot.

Run with: python bot.py
"""

import asyncio
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "expenses.sqlite3"

# Ten deliberately broad categories: they work without any configuration.
CATEGORIES = [
    ("food", "🍔 Еда"),
    ("coffee", "☕ Кофе"),
    ("taxi", "🚕 Такси"),
    ("transport", "🚌 Транспорт"),
    ("shopping", "🛍 Покупки"),
    ("home", "🏠 Дом"),
    ("health", "💊 Здоровье"),
    ("entertainment", "🎬 Развлечения"),
    ("subscriptions", "📱 Подписки"),
    ("other", "📦 Другое"),
]
CATEGORY_LABELS = dict(CATEGORIES)


@dataclass
class DraftExpense:
    description: str
    amount: int


# A small in-memory draft is enough for a bot used by a few people.
drafts: dict[int, DraftExpense] = {}
dp = Dispatcher()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK(amount > 0),
                category_key TEXT NOT NULL,
                category_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def parse_expense(text: str) -> DraftExpense | None:
    """Parse `coffee 300`: the final integer is the amount."""
    match = re.fullmatch(r"\s*(.+?\S)\s+([0-9][0-9 ]*)\s*", text)
    if not match:
        return None
    description = match.group(1).strip()
    amount = int(match.group(2).replace(" ", ""))
    if amount <= 0:
        return None
    return DraftExpense(description=description, amount=amount)


def categories_keyboard():
    builder = InlineKeyboardBuilder()
    for key, label in CATEGORIES:
        builder.button(text=label, callback_data=f"category:{key}")
    builder.adjust(2)
    return builder.as_markup()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Привет! Просто отправь расход в формате:\n"
        "<code>кофе 300</code>\n\n"
        "Последнее число — сумма в рублях. Затем выбери категорию."
    )


@dp.message(Command("cancel"))
async def cancel(message: Message) -> None:
    drafts.pop(message.from_user.id, None)
    await message.answer("Текущий расход отменён.")


@dp.message(F.text)
async def receive_expense(message: Message) -> None:
    draft = parse_expense(message.text)
    if draft is None:
        await message.answer("Напиши расход так: <code>кофе 300</code>")
        return

    drafts[message.from_user.id] = draft
    await message.answer(
        f"<b>{draft.description}</b> — {draft.amount:,} ₽\nВыбери категорию:".replace(",", " "),
        reply_markup=categories_keyboard(),
    )


@dp.callback_query(F.data.startswith("category:"))
async def save_expense(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    draft = drafts.pop(user_id, None)
    if draft is None:
        await callback.answer("Расход устарел. Отправь его ещё раз.", show_alert=True)
        return

    category_key = callback.data.split(":", maxsplit=1)[1]
    category_name = CATEGORY_LABELS.get(category_key)
    if category_name is None:
        await callback.answer("Неизвестная категория.", show_alert=True)
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO expenses
              (telegram_user_id, description, amount, category_key, category_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, draft.description, draft.amount, category_key, category_name),
        )

    await callback.message.edit_text(
        f"Сохранено: {category_name}\n{draft.description} — {draft.amount:,} ₽".replace(",", " ")
    )
    await callback.answer()


async def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    token = os.getenv("BOT_TOKEN")
    if not token or token == "put_your_telegram_bot_token_here":
        raise RuntimeError("Set BOT_TOKEN in the .env file. See .env.example.")
    init_db()
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
