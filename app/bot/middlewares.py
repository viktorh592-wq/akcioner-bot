"""Bot middleware module."""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging all incoming messages.
    
    Useful for debugging and monitoring bot activity.
    """
    
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        """
        Process incoming message and log it.
        
        Args:
            handler: Next handler in chain.
            event: Incoming message.
            data: Handler data.
            
        Returns:
            Handler result.
        """
        logger.info(f"Received message from user {event.from_user.id}: {event.text}")
        return await handler(event, data)
