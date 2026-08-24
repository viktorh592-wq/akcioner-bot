"""Add product handler (Russian)."""

import asyncio
import logging
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.models import Product, save_product
from app.parsers.base import get_parser, ParseError

logger = logging.getLogger(__name__)

router = Router()

PARSE_TIMEOUT_SECONDS = 30


class AddProductState(StatesGroup):
    waiting_for_url = State()
    waiting_for_range = State()
    waiting_for_interval = State()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    logger.info(f"User {message.from_user.id} initiated add product")
    await message.answer(
        "📎 Отправь ссылку на товар, который хочешь отслеживать.\n\n"
        "Поддерживаемые маркетплейсы:\n"
        "• Wildberries (wb.ru)\n"
        "• Ozon (ozon.ru)\n"
        "• Яндекс.Маркет (market.yandex.ru)\n"
        "• AliExpress (aliexpress.ru/com)\n"
        "• DNS (dns-shop.ru)\n"
        "• М.Видео (mvideo.ru)",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(AddProductState.waiting_for_url)


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("❌ Операция отменена.")
    except Exception:
        pass
    await callback.answer()


@router.message(AddProductState.waiting_for_url)
async def process_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        await message.answer(
            "❌ Это не похоже на ссылку. Отправь ссылку, начинающуюся с http:// или https://"
        )
        return

    try:
        parser = get_parser(url)
    except ParseError:
        await message.answer(
            "❌ Этот маркетплейс не поддерживается.\n\n"
            "Поддерживаются: Wildberries, Ozon, Яндекс.Маркет, AliExpress, DNS, М.Видео."
        )
        return

    wait_msg = await message.answer("⏳ Получаю информацию о товаре...")

    try:
        product_data = await asyncio.wait_for(parser.parse(url), timeout=PARSE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await wait_msg.edit_text(
            "❌ Маркетплейс не ответил вовремя. Попробуй ещё раз через пару минут."
        )
        await state.clear()
        return
    except ParseError as e:
        await wait_msg.edit_text(f"❌ {e}")
        await state.clear()
        return
    except Exception as e:
        await wait_msg.edit_text(f"❌ Не удалось получить товар: {e}\n\nПопробуй ещё раз.")
        await state.clear()
        return

    await state.update_data(
        url=url,
        title=product_data["title"],
        current_price=product_data["price"],
        image_url=product_data.get("image_url"),
        marketplace=parser.marketplace,
    )

    await wait_msg.edit_text(
        f"✅ Товар найден:\n\n<b>{product_data['title']}</b>\n\n"
        f"💵 Текущая цена: <b>{product_data['price']:,.0f} ₽</b>\n\n"
        "📉 Укажи диапазон цены, при которой я пришлю уведомление.\n"
        "Например: <b>1000-1500</b>\n\n"
        "(Если напишешь одно число — буду считать его максимальной ценой.)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(AddProductState.waiting_for_range)


def parse_range(text: str):
    parts = re.split(r"[-–—\s]+", text.replace("₽", "").replace("руб", "").strip())
    nums = []
    for part in parts:
        part = part.replace(" ", "").replace(",", ".").strip()
        if not part:
            continue
        try:
            nums.append(float(part))
        except ValueError:
            return None
    if len(nums) == 1:
        return 0, int(nums[0])
    if len(nums) == 2:
        lo, hi = sorted(nums)
        return int(lo), int(hi)
    return None


@router.message(AddProductState.waiting_for_range)
async def process_range(message: Message, state: FSMContext) -> None:
    parsed = parse_range(message.text or "")
    if parsed is None or parsed[1] <= 0:
        await message.answer(
            "❌ Не понял. Укажи диапазон в формате: <b>1000-1500</b> "
            "(или одно число — максимальная цена).",
            parse_mode="HTML",
        )
        return

    min_price, max_price = parsed
    await state.update_data(min_price=min_price, max_price=max_price)

    await message.answer(
        "⏰ Как часто проверять цену этого товара?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚡ Каждый час", callback_data="interval:1"),
                    InlineKeyboardButton(text="🕕 Каждые 6 часов", callback_data="interval:6"),
                ],
                [InlineKeyboardButton(text="📅 Раз в сутки", callback_data="interval:24")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
            ]
        ),
    )
    await state.set_state(AddProductState.waiting_for_interval)


@router.callback_query(AddProductState.waiting_for_interval, F.data.startswith("interval:"))
async def process_interval(callback: CallbackQuery, state: FSMContext) -> None:
    hours = int(callback.data.split(":")[1])
    data = await state.get_data()

    product = Product(
        telegram_user_id=callback.from_user.id,
        url=data["url"],
        marketplace=data["marketplace"],
        title=data["title"],
        image_url=data.get("image_url"),
        min_price=data["min_price"],
        max_price=data["max_price"],
        check_interval_hours=hours,
        last_price=int(data.get("current_price") or 0) or None,
    )

    try:
        await save_product(product)
    except Exception as e:
        await callback.message.answer(f"❌ Не удалось сохранить товар: {e}")
        await state.clear()
        return

    interval_text = {1: "каждый час", 6: "каждые 6 часов", 24: "раз в сутки"}[hours]

    await callback.message.answer(
        "✅ <b>Товар добавлен!</b>\n\n"
        f"📦 {data['title']}\n"
        f"🎯 Диапазон: {data['min_price']}–{data['max_price']} ₽\n"
        f"⏰ Проверка: {interval_text}\n\n"
        "Я напишу тебе, когда цена попадёт в диапазон или упадёт ниже 📉\n\n"
        "/list — посмотреть все товары",
        parse_mode="HTML",
    )
    await state.clear()
    await callback.answer()
