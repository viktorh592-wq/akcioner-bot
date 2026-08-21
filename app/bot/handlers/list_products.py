"""List products handler."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from app.db.models import get_products_by_user
from app.bot.keyboards import create_product_keyboard

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    """
    Handle /list command to show all tracked products.
    
    Args:
        message: Incoming message object.
    """
    logger.info(f"User {message.from_user.id} requested product list")
    
    try:
        products = await get_products_by_user(message.from_user.id, active_only=True)
        
        if not products:
            await message.answer(
                "📭 You don't have any tracked products yet.\n\n"
                "Use /add to add your first product!"
            )
            return
        
        # Build product list message
        response = f"📦 <b>Your Tracked Products ({len(products)})</b>\n\n"
        
        for i, product in enumerate(products, 1):
            status = "✅" if product.current_price and product.current_price <= product.target_price else "⏳"
            
            price_info = f"{product.current_price:,.0f} ₽" if product.current_price else "Unknown"
            
            response += (
                f"{i}. {status} <b>{product.title[:50]}...</b>\n"
                f"   💵 Current: {price_info}\n"
                f"   🎯 Target: {product.target_price:,.0f} ₽\n"
                f"   🏪 {product.marketplace.capitalize()}\n\n"
            )
        
        # Truncate if too long
        if len(response) > 4096:
            response = response[:4093] + "..."
        
        await message.answer(response, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Failed to list products for user {message.from_user.id}: {e}")
        await message.answer("❌ Failed to retrieve your products. Please try again later.")
