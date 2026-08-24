"""Start and help command handlers (Russian)."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer(
        "👋 <b>Привет! Я слежу за ценами на маркетплейсах</b>\n\n"
        "Поддерживаю: Wildberries, Ozon, Яндекс.Маркет, AliExpress, DNS, М.Видео\n\n"
        "<b>Как пользоваться:</b>\n"
        "1️⃣ /add — добавь товар и укажи диапазон цены\n"
        "2️⃣ /list — список твоих товаров\n"
        "3️⃣ /help — подробная справка\n\n"
        "Когда цена попадёт в твой диапазон — я пришлю уведомление! 📉",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    logger.info(f"User {message.from_user.id} requested help")
    await message.answer(
        "📚 <b>Команды:</b>\n\n"
        "/start — запуск и приветствие\n"
        "/add — добавить товар\n"
        "/list — мои товары (проверка, пауза, удаление)\n"
        "/delete — удалить товар\n"
        "/help — эта справка\n\n"
        "<b>Пример:</b> отправь ссылку на товар и укажи диапазон, например <b>1000-1500</b>.\n"
        "Я напишу, когда цена станет ≤ 1500 ₽, а если упадёт ниже 1000 ₽ — отмечу это как супер-цену! 🔥",
        parse_mode="HTML",
    )
