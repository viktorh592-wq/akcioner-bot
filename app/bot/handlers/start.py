"""Start command handler."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CommandStart

from app.notifications.notifier import send_welcome_message

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
    
    await send_welcome_message(message.bot, message.from_user.id)
