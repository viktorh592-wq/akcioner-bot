"""Start command handler."""

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """
    Handle /start command.

    Sends a welcome message to the user with instructions on how to use the bot.

    Args:
        message: Incoming message object.
    """
    logger.info(f"User {message.from_user.id} started the bot")
    
    welcome_text = (
        "👋 <b>Привет! Я бот для отслеживания цен</b>\n\n"
        "Я помогу тебе следить за ценами на российских маркетплейсах:\n"
        "• Wildberries\n"
        "• Ozon\n"
        "• Яндекс.Маркет\n"
        "• AliExpress\n"
        "• DNS\n"
        "• М.Видео\n\n"
        "<b>Как пользоваться:</b>\n"
        "1️⃣ /add - добавить товар для отслеживания\n"
        "2️⃣ /list - посмотреть все твои товары\n"
        "3️⃣ /help - подробная помощь\n\n"
        "Нажми /add чтобы начать! 🚀"
    )
    
    await message.answer(welcome_text, parse_mode="HTML")
    logger.info(f"Welcome message sent to user {message.from_user.id}")
