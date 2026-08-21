"""Notification module for sending price drop alerts."""

import logging
from typing import Optional

from aiogram import Bot

from app.db.models import Product

logger = logging.getLogger(__name__)


async def send_price_drop_notification(
    bot: Bot,
    user_id: int,
    product: Product,
    old_price: Optional[float],
    new_price: float,
    target_price: float,
) -> bool:
    """
    Send a notification to a user when a product price drops below target.
    
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID to notify.
        product: Product that had a price drop.
        old_price: Previous price (can be None if first check).
        new_price: Current price.
        target_price: User's target price threshold.
        
    Returns:
        bool: True if notification was sent successfully.
    """
    try:
        # Calculate discount percentage
        discount_percent = 0
        if old_price and old_price > 0:
            discount_percent = round(((old_price - new_price) / old_price) * 100, 1)
        
        # Build notification message
        message = (
            f"🔥 <b>Price Drop Alert!</b>\n\n"
            f"<b>{product.title}</b>\n\n"
            f"💰 New Price: <b>{new_price:,.0f} ₽</b>\n"
        )
        
        if old_price:
            message += f"~~{old_price:,.0f} ₽~~ (-{discount_percent}%)\n"
        
        message += (
            f"🎯 Your Target: {target_price:,.0f} ₽\n\n"
            f"✅ Price is now BELOW your target!\n\n"
            f"🔗 <a href='{product.url}'>View Product</a>"
        )
        
        # Send photo if available
        if product.image_url:
            await bot.send_photo(
                chat_id=user_id,
                photo=product.image_url,
                caption=message,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML",
            )
        
        logger.info(f"Sent price drop notification to user {user_id} for product {product.id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {e}")
        return False


async def send_welcome_message(bot: Bot, user_id: int) -> bool:
    """
    Send a welcome message to a new user.
    
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID.
        
    Returns:
        bool: True if message was sent successfully.
    """
    try:
        message = (
            "👋 <b>Welcome to Price Tracker Bot!</b>\n\n"
            "I'll help you track prices on Russian marketplaces:\n"
            "• Wildberries\n"
            "• Ozon\n"
            "• Yandex Market\n"
            "• AliExpress\n"
            "• DNS\n"
            "• M.Video\n\n"
            "<b>How to use:</b>\n"
            "1. Send me a product URL\n"
            "2. Set your target price\n"
            "3. I'll notify you when the price drops!\n\n"
            "Use /help for more commands."
        )
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
        )
        
        logger.info(f"Sent welcome message to user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send welcome message to user {user_id}: {e}")
        return False


async def send_help_message(bot: Bot, user_id: int) -> bool:
    """
    Send a help message with command descriptions.
    
    Args:
        bot: Aiogram Bot instance.
        user_id: Telegram user ID.
        
    Returns:
        bool: True if message was sent successfully.
    """
    try:
        message = (
            "📚 <b>Bot Commands:</b>\n\n"
            "/start - Start the bot and see welcome message\n"
            "/add - Add a new product to track\n"
            "/list - View all your tracked products\n"
            "/delete - Remove a product from tracking\n"
            "/help - Show this help message\n\n"
            "<b>Tips:</b>\n"
            "• You can send product URLs directly\n"
            "• Price checks run automatically every 30 minutes\n"
            "• You'll only be notified when price ≤ your target"
        )
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send help message to user {user_id}: {e}")
        return False
