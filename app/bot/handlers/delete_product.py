"""Delete product handler (Russian)."""

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.models import get_products_by_user
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    products = await get_products_by_user(message.from_user.id, active_only=False)

    if not products:
        await message.answer("📭 Список пуст — удалять нечего.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"🗑 {p.title[:40]}", callback_data=f"del:{p.id}")]
        for p in products
    ]

    await message.answer(
        "🗑 <b>Какой товар удалить?</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery) -> None:
    pid = callback.data[4:]
    supabase = get_supabase()
    supabase.table("products").delete().eq("id", pid).execute()
    try:
        await callback.message.edit_text("🗑 Товар удалён из отслеживания.")
    except Exception:
        await callback.message.answer("🗑 Товар удалён из отслеживания.")
    await callback.answer()
