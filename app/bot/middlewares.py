"""Bot middlewares for request processing and access control."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from app.config import settings

logger = logging.getLogger(__name__)


class AdminOnlyMiddleware(BaseMiddleware):
    """
    Middleware that restricts bot access to admin only.
    
    Checks if the user ID matches the configured TELEGRAM_ADMIN_ID.
    If not, sends an access denied message and blocks the request.
    """

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """
        Check user access before processing the update.

        Args:
            handler: Next handler in the chain.
            event: Telegram update object.
            data: Additional data.

        Returns:
            Result of the next handler if access granted, None otherwise.
        """
        # Get user from message or callback query
        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user

        # If no user found, allow (system messages)
        if not user:
            return await handler(event, data)

        # Check if user is admin
        if user.id != settings.telegram_admin_id:
            logger.warning(
                f"Access denied for user {user.id} (username: {user.username}). "
                f"Expected admin ID: {settings.telegram_admin_id}"
            )

            # Send access denied message
            if event.message:
                await event.message.answer(
                    "❌ <b>Доступ запрещён</b>\n\n"
                    "Этот бот предназначен только для личного использования владельцем.\n\n"
                    "Если вы считаете, что это ошибка, свяжитесь с администратором бота.",
                    parse_mode="HTML",
                )
            elif event.callback_query:
                await event.callback_query.answer(
                    "❌ Доступ запрещён. Этот бот только для владельца.",
                    show_alert=True,
                )

            # Block the request
            return None

        # User is admin, continue processing
        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging all incoming updates.
    Useful for debugging and monitoring.
    """

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """
        Log update details before processing.

        Args:
            handler: Next handler in the chain.
            event: Telegram update object.
            data: Additional data.

        Returns:
            Result of the next handler.
        """
        user = None
        update_type = "unknown"

        if event.message:
            user = event.message.from_user
            update_type = "message"
            logger.info(
                f"Received {update_type} from user {user.id} "
                f"(username: {user.username}): {event.message.text}"
            )
        elif event.callback_query:
            user = event.callback_query.from_user
            update_type = "callback_query"
            logger.info(
                f"Received {update_type} from user {user.id} "
                f"(username: {user.username}): {event.callback_query.data}"
            )

        return await handler(event, data)
