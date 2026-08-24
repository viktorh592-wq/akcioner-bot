"""Notification module for sending price alerts (Russian)."""

import logging
from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    return _bot


async def send_price_drop_notification(
    user_id: int,
    product_data: dict,
    old_price: Optional[float],
    new_price: float,
    min_price: float,
    max_price: float,
    notification_type: str,
) -> bool:
    """Send a price alert to the user in Russian."""
    try:
        bot = get_bot()
        title = product_data.get("title", "Товар")
        url = product_data.get("url", "")
        image_url = product_data.get("image_url")

        discount_line = ""
        if old_price and old_price > 0:
            percent = round(((old_price - new_price) / old_price) * 100, 1)
            discount_line = f"💸 Было: <s>{old_price:,.0f} ₽</s> (−{percent}%)\n"

        message = (
            "🔔 <b>Цена попала в твой диапазон!</b>\n\n"
            f"📦 <b>{title}</b>\n\n"
            f"💰 Цена сейчас: <b>{new_price:,.0f} ₽</b>\n"
            f"{discount_line}"
            f"🎯 Твой диапазон: {min_price:,.0f}–{max_price:,.0f} ₽\n\n"
            f"{notification_type}\n\n"
            f"🔗 <a href='{url}'>Открыть товар</a>"
        )

        if image_url:
            try:
                await bot.send_photo(chat_id=user_id, photo=image_url, caption=message)
                logger.info(f"Sent price notification (photo) to user {user_id}")
                return True
            except Exception:
                pass

        await bot.send_message(chat_id=user_id, text=message)
        logger.info(f"Sent price notification to user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {e}")
        return False


async def send_welcome_message(bot: Bot, user_id: int) -> bool:
    """Send a welcome message (kept for compatibility)."""
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "👋 <b>Привет! Я слежу за ценами на маркетплейсах.</b>\n\n"
                "Нажми /add, чтобы добавить товар."
            ),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send welcome message to user {user_id}: {e}")
        return False
