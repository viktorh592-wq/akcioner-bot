"""List products handler (Russian)."""

import asyncio
import html
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.models import get_products_by_user
from app.db.supabase_client import get_supabase
from app.parsers.base import get_parser, ParseError

logger = logging.getLogger(__name__)

router = Router()

MARKETPLACE_EMOJI = {
    "wildberries": "🟣",
    "ozon": "🔵",
    "yandex": "🟡",
    "aliexpress": "🟠",
    "dns": "🟢",
    "mvideo": "🔴",
}

# Budget for a manual "check price" request. WB's antibot may take ~75s,
# so this must be larger than the parser's internal budget.
CHECK_TIMEOUT_SECONDS = 100


async def _safe_cancel(task: "asyncio.Task") -> None:
    """Cancel a stuck parse task in the background without blocking replies."""
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=15)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass


def product_keyboard(product_id: str, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "▶️ Возобновить" if not is_active else "⏸ Приостановить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить", callback_data=f"check:{product_id}"),
                InlineKeyboardButton(text=toggle_text, callback_data=f"toggle:{product_id}"),
            ],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ldel:{product_id}")],
        ]
    )


def product_card_text(p) -> str:
    emoji = MARKETPLACE_EMOJI.get(p.marketplace, "🛒")
    status = "✅ активен" if p.is_active else "⏸ на паузе"
    last = f"{p.last_price:,.0f} ₽" if p.last_price else "ещё не проверялась"
    title = html.escape(str(p.title)[:200])
    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"💵 Текущая цена: {last}\n"
        f"🎯 Диапазон: {p.min_price}–{p.max_price} ₽\n"
        f"⏰ Проверка: каждые {p.check_interval_hours} ч\n"
        f"📌 Статус: {status}\n\n"
        f"🔗 {p.url}"
    )


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    products = await get_products_by_user(message.from_user.id, active_only=False)

    if not products:
        await message.answer(
            "📭 Пока нет отслеживаемых товаров.\n\nНажми /add, чтобы добавить первый!"
        )
        return

    await message.answer(f"📋 <b>Твои товары ({len(products)}):</b>", parse_mode="HTML")
    for p in products:
        await message.answer(
            product_card_text(p),
            reply_markup=product_keyboard(p.id, p.is_active),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("ldel:"))
async def cb_delete(callback: CallbackQuery) -> None:
    pid = callback.data[5:]
    supabase = get_supabase()
    await asyncio.to_thread(
        lambda: supabase.table("products").delete().eq("id", pid).execute()
    )
    try:
        await callback.message.edit_text("🗑 Товар удалён из отслеживания.")
    except Exception:
        await callback.message.answer("🗑 Товар удалён из отслеживания.")
    await callback.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(callback: CallbackQuery) -> None:
    pid = callback.data[7:]
    supabase = get_supabase()
    row = await asyncio.to_thread(
        lambda: supabase.table("products").select("is_active").eq("id", pid).execute()
    )

    if not row.data:
        await callback.answer("Товар не найден", show_alert=True)
        return

    new_state = not row.data[0]["is_active"]
    await asyncio.to_thread(
        lambda: supabase.table("products")
        .update({"is_active": new_state})
        .eq("id", pid)
        .execute()
    )

    await callback.answer(
        "▶️ Отслеживание возобновлено" if new_state else "⏸ Отслеживание на паузе"
    )
    try:
        await callback.message.edit_reply_markup(
            reply_markup=product_keyboard(pid, new_state)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("check:"))
async def cb_check(callback: CallbackQuery) -> None:
    pid = callback.data[6:]
    supabase = get_supabase()
    row = await asyncio.to_thread(
        lambda: supabase.table("products").select("*").eq("id", pid).execute()
    )

    if not row.data:
        await callback.answer("Товар не найден", show_alert=True)
        return

    data = row.data[0]
    await callback.answer("⏳ Проверяю цену...")

    status_msg = await callback.message.answer(
        f"⏳ Проверяю цену...\n📦 {html.escape(str(data['title'])[:80])}"
    )

    # shield + task pattern (see add_product.py): guarantees a reply even if
    # the parser gets stuck inside Playwright cleanup.
    parse_task = asyncio.create_task(get_parser(data["url"]).parse(data["url"]))
    timed_out = False
    try:
        result = await asyncio.wait_for(
            asyncio.shield(parse_task), timeout=CHECK_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        timed_out = True
    except ParseError as e:
        await status_msg.edit_text(f"❌ {e}")
        return
    except Exception as e:
        logger.exception(f"Manual price check failed for product {pid}")
        await status_msg.edit_text(f"❌ Не удалось проверить цену: {e}")
        return

    if timed_out:
        asyncio.get_running_loop().create_task(_safe_cancel(parse_task))
        await status_msg.edit_text(
            "❌ Маркетплейс не ответил вовремя (защита от ботов).\n"
            "Попробуй ещё раз через пару минут."
        )
        return

    price = result["price"]

    await asyncio.to_thread(
        lambda: supabase.table("products")
        .update({"last_price": int(price)})
        .eq("id", pid)
        .execute()
    )

    if price < data["min_price"]:
        verdict = "🔥 НИЖЕ диапазона — отличная сделка!"
    elif price <= data["max_price"]:
        verdict = "✅ Цена в твоём диапазоне!"
    else:
        verdict = "😔 Пока выше диапазона — ждём снижения."

    try:
        await status_msg.edit_text(
            f"🔄 <b>Проверка цены</b>\n\n"
            f"📦 {html.escape(str(data['title'])[:200])}\n\n"
            f"💵 Цена сейчас: <b>{price:,.0f} ₽</b>\n"
            f"🎯 Твой диапазон: {data['min_price']}–{data['max_price']} ₽\n\n"
            f"{verdict}",
            parse_mode="HTML",
        )
    except Exception:
        pass
