"""Telegram bot keyboard utilities."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def create_product_keyboard(product_id: str) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for a product item.
    
    Args:
        product_id: Product UUID.
        
    Returns:
        InlineKeyboardMarkup: Keyboard with delete button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_{product_id}")]
        ]
    )


def create_cancel_keyboard() -> InlineKeyboardMarkup:
    """
    Create inline keyboard with cancel button.
    
    Returns:
        InlineKeyboardMarkup: Keyboard with cancel button.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
        ]
    )
