"""Help command handler."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """
    Handle /help command.

    Sends a detailed help message with all available commands.

    Args:
        message: Incoming message object.
    """
    logger.info(f"User {message.from_user.id} requested help")
    
    help_text = (
        "📚 <b>Справка по командам</b>\n\n"
        "/start - Запустить бота и увидеть приветствие\n"
        "/add - Добавить новый товар для отслеживания\n"
        "/list - Посмотреть все отслеживаемые товары\n"
        "/help - Показать эту справку\n\n"
        "<b>Как добавить товар:</b>\n"
        "1. Нажми /add\n"
        "2. Отправь ссылку на товар с маркетплейса\n"
        "3. Укажи желаемый диапазон цен (например: 1000-1500)\n"
        "4. Бот будет проверять цену и уведомит тебя, когда она попадёт в диапазон\n\n"
        "<b>Поддерживаемые маркетплейсы:</b>\n"
        "• Wildberries (wildberries.ru, wb.ru)\n"
        "• Ozon (ozon.ru)\n"
        "• Яндекс.Маркет (market.yandex.ru)\n"
        "• AliExpress (aliexpress.ru)\n"
        "• DNS (dns-shop.ru)\n"
        "• М.Видео (mvideo.ru)\n\n"
        "💡 Бот проверяет цены автоматически каждые 10 минут"
    )
    
    await message.answer(help_text, parse_mode="HTML")
