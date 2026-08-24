"""Add product handler (Russian)."""

import asyncio
import html
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

# Total budget for fetching product info. The WB antibot challenge can take
# up to ~75s, so the outer timeout must be larger than the parser's own budget
# (tier1 ~12s + tier2 ~10s + tier3 ~75s ≈ 97s worst case).
PARSE_TIMEOUT_SECONDS = 100
# Show a "still working" update if fetching takes longer than this
PARSE_PROGRESS_AFTER = 25


class AddProductState(StatesGroup):
    waiting_for_url = State()
    waiting_for_range = State()
    waiting_for_interval = State()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )


async def _safe_cancel(task: "asyncio.Task") -> None:
    """Cancel a parse task in the background without blocking the handler.

    If the task is stuck inside Playwright cleanup, cancellation itself can
    hang — that must never block the reply to the user, so we give the
    cancellation its own short timeout and then simply abandon the task.
    """
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=15)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass


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

    # Run the parse as an independent task. We deliberately do NOT use a bare
    # `asyncio.wait_for(parser.parse(url))`: if the coroutine hangs inside
    # Playwright cleanup, wait_for would wait for the cancellation to finish
    # and the user would never get a reply (the "bot froze" bug). With the
    # shield + task pattern we always answer on time and cancel in background.
    parse_task = asyncio.create_task(parser.parse(url))

    async def _show_progress() -> None:
        await _edit_safely(
            wait_msg,
            "⏳ Маркетплейс проверяет запрос (антибот-защита)...\n"
            "Это может занять до полутора минут — не спеши отправлять новые команды.",
        )

    loop = asyncio.get_running_loop()
    progress_task = loop.call_later(PARSE_PROGRESS_AFTER, lambda: loop.create_task(_show_progress()))

    timed_out = False
    try:
        product_data = await asyncio.wait_for(
            asyncio.shield(parse_task), timeout=PARSE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        timed_out = True
        product_data = None
    except ParseError as e:
        progress_task.cancel()
        await _edit_safely(wait_msg, f"❌ {e}")
        await state.clear()
        return
    except Exception as e:
        logger.exception(f"Unexpected parse error for {url}")
        progress_task.cancel()
        await _edit_safely(
            wait_msg, f"❌ Не удалось получить товар: {e}\n\nПопробуй ещё раз."
        )
        await state.clear()
        return

    progress_task.cancel()

    if timed_out:
        # Reply IMMEDIATELY; finish the stuck parse in the background.
        asyncio.get_running_loop().create_task(_safe_cancel(parse_task))
        await _edit_safely(
            wait_msg,
            "❌ Маркетплейс не ответил вовремя (защита от ботов).\n"
            "Попробуй ещё раз через пару минут — команда /add.",
        )
        await state.clear()
        return

    if product_data is None:  # task was cancelled unexpectedly
        await _edit_safely(wait_msg, "❌ Не удалось получить товар. Попробуй ещё раз.")
        await state.clear()
        return

    await state.update_data(
        url=url,
        title=product_data["title"],
        current_price=product_data["price"],
        image_url=product_data.get("image_url"),
        marketplace=parser.marketplace,
    )

    title = product_data["title"]
    if len(title) > 200:
        title = title[:200] + "…"
    safe_title = html.escape(title)

    await _edit_safely(
        wait_msg,
        f"✅ Товар найден:\n\n<b>{safe_title}</b>\n\n"
        f"💵 Текущая цена: <b>{product_data['price']:,.0f} ₽</b>\n\n"
        "📉 Укажи диапазон цены, при которой я пришлю уведомление.\n"
        "Например: <b>1000-1500</b>\n\n"
        "(Если напишешь одно число — буду считать его максимальной ценой.)",
        parse_mode="HTML",
        keyboard=cancel_keyboard(),
    )
    await state.set_state(AddProductState.waiting_for_range)


async def _edit_safely(msg: Message, text: str, parse_mode: str = None, keyboard=None) -> None:
    """Edit the status message, ignoring Telegram API errors (e.g. duplicate text)."""
    try:
        await msg.edit_text(
            text,
            parse_mode=parse_mode,
            reply_markup=keyboard,
        )
    except Exception:
        pass


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
        f"📦 {html.escape(str(data['title'])[:200])}\n"
        f"🎯 Диапазон: {data['min_price']}–{data['max_price']} ₽\n"
        f"⏰ Проверка: {interval_text}\n\n"
        "Я напишу тебе, когда цена попадёт в диапазон или упадёт ниже 📉\n\n"
        "/list — посмотреть все товары",
        parse_mode="HTML",
    )
    await state.clear()
    await callback.answer()
