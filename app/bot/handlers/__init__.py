"""Bot handlers module."""

from app.bot.handlers.start import router as start_router
from app.bot.handlers.add_product import router as add_product_router
from app.bot.handlers.list_products import router as list_products_router
from app.bot.handlers.delete_product import router as delete_product_router
from app.bot.handlers.help import router as help_router

__all__ = [
    "start_router",
    "add_product_router",
    "list_products_router",
    "delete_product_router",
    "help_router",
]
