"""Add product handler."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.db.models import Product, save_product
from app.parsers.base import get_parser, ParseError

logger = logging.getLogger(__name__)

router = Router()


class AddProductState(StatesGroup):
    """States for adding a product."""
    waiting_for_url = State()
    waiting_for_target_price = State()


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    """
    Handle /add command to start adding a new product.
    
    Args:
        message: Incoming message object.
        state: FSM context for conversation state.
    """
    logger.info(f"User {message.from_user.id} initiated add product")
    
    await message.answer(
        "📎 Send me the product URL you want to track.\n\n"
        "Supported marketplaces:\n"
        "• Wildberries (wb.ru)\n"
        "• Ozon (ozon.ru)\n"
        "• Yandex Market (market.yandex.ru)\n"
        "• AliExpress (aliexpress.ru/com)\n"
        "• DNS (dns-shop.ru)\n"
        "• M.Video (mvideo.ru)",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]]
        )
    )
    
    await state.set_state(AddProductState.waiting_for_url)


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Handle cancel button press.
    
    Args:
        callback: Callback query object.
        state: FSM context.
    """
    await state.clear()
    await callback.message.edit_text("❌ Operation cancelled.")
    await callback.answer()


@router.message(AddProductState.waiting_for_url)
async def process_url(message: Message, state: FSMContext) -> None:
    """
    Process the product URL sent by user.
    
    Args:
        message: Incoming message with URL.
        state: FSM context.
    """
    url = message.text.strip()
    
    # Validate URL
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "❌ Invalid URL. Please send a valid http/https URL."
        )
        return
    
    # Try to get parser for this URL
    try:
        parser = get_parser(url)
    except ParseError as e:
        await message.answer(
            f"❌ {e}\n\nPlease send a URL from one of the supported marketplaces."
        )
        return
    
    # Try to parse the page to get initial data
    await message.answer("⏳ Fetching product information...")
    
    try:
        product_data = await parser.parse(url)
    except Exception as e:
        await message.answer(f"❌ Failed to fetch product info: {e}")
        return
    
    # Store temporary data
    await state.update_data(
        url=url,
        title=product_data["title"],
        current_price=product_data["price"],
        image_url=product_data["image_url"],
        marketplace=parser.marketplace,
    )
    
    await message.answer(
        f"✅ Found product:\n\n"
        f"<b>{product_data['title']}</b>\n\n"
        f"💵 Current price: {product_data['price']:,.0f} ₽\n\n"
        f"Send your target price (in rubles). I'll notify you when it drops to or below this amount.",
        parse_mode="HTML",
    )
    
    await state.set_state(AddProductState.waiting_for_target_price)


@router.message(AddProductState.waiting_for_target_price)
async def process_target_price(message: Message, state: FSMContext) -> None:
    """
    Process the target price sent by user and save the product.
    
    Args:
        message: Incoming message with target price.
        state: FSM context.
    """
    try:
        target_price = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer(
            "❌ Invalid price. Please enter a number (e.g., 1500 or 1500.50)"
        )
        return
    
    if target_price <= 0:
        await message.answer("❌ Price must be greater than 0.")
        return
    
    # Get stored data
    data = await state.get_data()
    
    # Create and save product
    product = Product(
        user_id=message.from_user.id,
        url=data["url"],
        title=data["title"],
        target_price=target_price,
        current_price=data["current_price"],
        image_url=data.get("image_url"),
        marketplace=data["marketplace"],
    )
    
    try:
        saved_product = await save_product(product)
        
        await message.answer(
            f"✅ <b>Product added successfully!</b>\n\n"
            f"I'll check the price every 30 minutes and notify you when it drops to {target_price:,.0f} ₽ or below.\n\n"
            f"Use /list to see all your tracked products.",
            parse_mode="HTML",
        )
        
        logger.info(f"User {message.from_user.id} added product: {saved_product.id}")
        
    except Exception as e:
        await message.answer(f"❌ Failed to save product: {e}")
        logger.error(f"Failed to save product for user {message.from_user.id}: {e}")
    
    finally:
        await state.clear()
