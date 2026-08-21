"""Delete product handler."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from app.db.models import delete_product, get_products_by_user

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    """
    Handle /delete command to remove a product.
    
    Args:
        message: Incoming message object.
    """
    logger.info(f"User {message.from_user.id} initiated delete product")
    
    try:
        products = await get_products_by_user(message.from_user.id, active_only=True)
        
        if not products:
            await message.answer(
                "📭 You don't have any tracked products to delete.\n\n"
                "Use /add to add products first."
            )
            return
        
        # Build list with numbers for selection
        response = "🗑️ <b>Select a product to delete:</b>\n\n"
        
        for i, product in enumerate(products, 1):
            price_info = f"{product.current_price:,.0f} ₽" if product.current_price else "Unknown"
            
            response += (
                f"{i}. <b>{product.title[:40]}...</b>\n"
                f"   💵 {price_info} | 🎯 {product.target_price:,.0f} ₽\n"
                f"   ID: <code>{product.id}</code>\n\n"
            )
        
        response += (
            "Send the number of the product you want to delete,\n"
            "or send the product ID directly."
        )
        
        await message.answer(response, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Failed to show delete menu for user {message.from_user.id}: {e}")
        await message.answer("❌ Failed to retrieve your products. Please try again later.")


@router.message(cmd_delete)
async def process_delete_selection(message: Message) -> None:
    """
    Process product deletion based on user input.
    
    Args:
        message: Incoming message with product number or ID.
    """
    try:
        products = await get_products_by_user(message.from_user.id, active_only=True)
        
        if not products:
            return
        
        user_input = message.text.strip()
        
        # Try to parse as number first
        try:
            selection = int(user_input)
            
            if 1 <= selection <= len(products):
                product_to_delete = products[selection - 1]
            else:
                await message.answer(
                    f"❌ Invalid number. Please enter a number between 1 and {len(products)}."
                )
                return
                
        except ValueError:
            # Try to find by ID
            product_to_delete = None
            for product in products:
                if product.id == user_input:
                    product_to_delete = product
                    break
            
            if not product_to_delete:
                await message.answer(
                    "❌ Product not found. Please send a valid product number or ID."
                )
                return
        
        # Delete the product
        success = await delete_product(product_to_delete.id, message.from_user.id)  # type: ignore
        
        if success:
            await message.answer(
                f"✅ Product deleted successfully:\n{product_to_delete.title}"
            )
            logger.info(
                f"User {message.from_user.id} deleted product {product_to_delete.id}"
            )
        else:
            await message.answer("❌ Failed to delete product. Please try again.")
            
    except Exception as e:
        logger.error(f"Failed to delete product for user {message.from_user.id}: {e}")
        await message.answer("❌ An error occurred. Please try again later.")
