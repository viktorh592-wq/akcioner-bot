"""Bot module initialization."""

from app.bot.handlers import (
    start_router,
    add_product_router,
    list_products_router,
    delete_product_router,
)

__all__ = [
    "start_router",
    "add_product_router",
    "list_products_router",
    "delete_product_router",
]
