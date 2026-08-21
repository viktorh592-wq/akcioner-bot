"""Database module initialization."""

from app.db.supabase_client import get_supabase, SupabaseClient
from app.db.models import (
    Product,
    PriceHistory,
    save_product,
    get_products_by_user,
    delete_product,
    save_price,
    update_product_price,
    get_product_by_id,
)

__all__ = [
    "get_supabase",
    "SupabaseClient",
    "Product",
    "PriceHistory",
    "save_product",
    "get_products_by_user",
    "delete_product",
    "save_price",
    "update_product_price",
    "get_product_by_id",
]
