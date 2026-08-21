"""
Database models and helper functions for the price tracker.

This module defines Pydantic models for database entities and provides
helper functions for CRUD operations with Supabase.

Schema matches existing Supabase tables:
- products: id, telegram_user_id, url, marketplace, title, image_url,
            min_price, max_price, check_interval_hours, is_active,
            last_checked_at, last_price, created_at
- price_history: id, product_id, price, checked_at
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel, Field

from app.db.supabase_client import get_supabase


class Product(BaseModel):
    """
    Product model representing a tracked item.

    Attributes:
        id: Unique product identifier (UUID).
        telegram_user_id: Telegram user ID who added this product.
        url: Product URL on the marketplace.
        marketplace: Name of the marketplace (e.g., 'wildberries', 'ozon').
        title: Product title/name.
        image_url: URL to product image.
        min_price: Minimum acceptable price (range lower bound).
        max_price: Maximum acceptable price (range upper bound for notifications).
        check_interval_hours: How often to check this product (hours).
        is_active: Whether the product is actively tracked.
        last_checked_at: Timestamp of last price check.
        last_price: Last known price.
        created_at: Timestamp when product was added.
    """
    id: Optional[str] = None
    telegram_user_id: int
    url: str
    marketplace: str
    title: str
    image_url: Optional[str] = None
    min_price: int
    max_price: int
    check_interval_hours: int = 24
    is_active: bool = True
    last_checked_at: Optional[datetime] = None
    last_price: Optional[int] = None
    created_at: Optional[datetime] = None


class PriceHistory(BaseModel):
    """
    Price history model for tracking price changes over time.

    Attributes:
        id: Unique history record identifier (UUID).
        product_id: Reference to the product.
        price: Recorded price at this point in time.
        checked_at: Timestamp when price was recorded.
    """
    id: Optional[str] = None
    product_id: str
    price: int
    checked_at: Optional[datetime] = None


async def save_product(product: Product) -> Product:
    """
    Save or update a product in the database.

    Args:
        product: Product instance to save.

    Returns:
        Product: Saved product with generated fields (id, timestamps).
    """
    supabase = get_supabase()

    data = {
        "telegram_user_id": product.telegram_user_id,
        "url": product.url,
        "marketplace": product.marketplace,
        "title": product.title,
        "image_url": product.image_url,
        "min_price": product.min_price,
        "max_price": product.max_price,
        "check_interval_hours": product.check_interval_hours,
        "is_active": product.is_active,
    }

    if product.id:
        # Update existing product
        result = supabase.table("products").update(data).eq("id", product.id).execute()
    else:
        # Insert new product
        result = supabase.table("products").insert(data).execute()

    if result.data:
        saved_data = result.data[0]
        return Product(
            id=saved_data["id"],
            telegram_user_id=saved_data["telegram_user_id"],
            url=saved_data["url"],
            marketplace=saved_data["marketplace"],
            title=saved_data["title"],
            image_url=saved_data.get("image_url"),
            min_price=saved_data["min_price"],
            max_price=saved_data["max_price"],
            check_interval_hours=saved_data["check_interval_hours"],
            is_active=saved_data["is_active"],
            last_checked_at=datetime.fromisoformat(saved_data["last_checked_at"]) if saved_data.get("last_checked_at") else None,
            last_price=saved_data.get("last_price"),
            created_at=datetime.fromisoformat(saved_data["created_at"]) if saved_data.get("created_at") else None,
        )

    raise RuntimeError("Failed to save product")


async def get_products_by_user(user_id: int, active_only: bool = True) -> list[Product]:
    """
    Get all products tracked by a specific user.

    Args:
        user_id: Telegram user ID.
        active_only: If True, only return active products.

    Returns:
        list[Product]: List of products belonging to the user.
    """
    supabase = get_supabase()

    query = supabase.table("products").select("*").eq("telegram_user_id", user_id)

    if active_only:
        query = query.eq("is_active", True)

    result = query.execute()

    products = []
    for row in result.data or []:
        products.append(Product(
            id=row["id"],
            telegram_user_id=row["telegram_user_id"],
            url=row["url"],
            marketplace=row["marketplace"],
            title=row["title"],
            image_url=row.get("image_url"),
            min_price=row["min_price"],
            max_price=row["max_price"],
            check_interval_hours=row["check_interval_hours"],
            is_active=row["is_active"],
            last_checked_at=datetime.fromisoformat(row["last_checked_at"]) if row.get("last_checked_at") else None,
            last_price=row.get("last_price"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
        ))

    return products


async def get_product_by_id(product_id: str) -> Optional[Product]:
    """
    Get a single product by its ID.

    Args:
        product_id: Product UUID.

    Returns:
        Product | None: Product if found, None otherwise.
    """
    supabase = get_supabase()

    result = supabase.table("products").select("*").eq("id", product_id).execute()

    if result.data:
        row = result.data[0]
        return Product(
            id=row["id"],
            telegram_user_id=row["telegram_user_id"],
            url=row["url"],
            marketplace=row["marketplace"],
            title=row["title"],
            image_url=row.get("image_url"),
            min_price=row["min_price"],
            max_price=row["max_price"],
            check_interval_hours=row["check_interval_hours"],
            is_active=row["is_active"],
            last_checked_at=datetime.fromisoformat(row["last_checked_at"]) if row.get("last_checked_at") else None,
            last_price=row.get("last_price"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
        )

    return None


async def get_due_products(now_utc: datetime) -> list[Product]:
    """
    Get all products that are due for price checking.

    A product is due if:
    - is_active = true
    - last_checked_at IS NULL OR last_checked_at <= now - check_interval_hours

    Args:
        now_utc: Current UTC timestamp.

    Returns:
        list[Product]: List of products due for checking.
    """
    supabase = get_supabase()

    # Query for products where last_checked_at is NULL or older than check_interval_hours
    # We need to do this in two queries or use OR with complex conditions
    # Using raw SQL via RPC would be ideal, but let's use client-side filtering
    
    # Get all active products
    result = supabase.table("products").select("*").eq("is_active", True).execute()
    
    due_products = []
    for row in result.data or []:
        last_checked = row.get("last_checked_at")
        check_interval = row.get("check_interval_hours", 24)
        
        if last_checked is None:
            # Never checked, so it's due
            due_products.append(Product(
                id=row["id"],
                telegram_user_id=row["telegram_user_id"],
                url=row["url"],
                marketplace=row["marketplace"],
                title=row["title"],
                image_url=row.get("image_url"),
                min_price=row["min_price"],
                max_price=row["max_price"],
                check_interval_hours=check_interval,
                is_active=row["is_active"],
                last_checked_at=None,
                last_price=row.get("last_price"),
                created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            ))
        else:
            last_checked_dt = datetime.fromisoformat(last_checked)
            threshold = now_utc - timedelta(hours=check_interval)
            if last_checked_dt <= threshold:
                due_products.append(Product(
                    id=row["id"],
                    telegram_user_id=row["telegram_user_id"],
                    url=row["url"],
                    marketplace=row["marketplace"],
                    title=row["title"],
                    image_url=row.get("image_url"),
                    min_price=row["min_price"],
                    max_price=row["max_price"],
                    check_interval_hours=check_interval,
                    is_active=row["is_active"],
                    last_checked_at=last_checked_dt,
                    last_price=row.get("last_price"),
                    created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
                ))
    
    return due_products


async def delete_product(product_id: str, user_id: int) -> bool:
    """
    Delete a product from the database.

    Args:
        product_id: Product UUID to delete.
        user_id: Telegram user ID (for ownership verification).

    Returns:
        bool: True if product was deleted, False otherwise.
    """
    supabase = get_supabase()

    result = (
        supabase.table("products")
        .delete()
        .eq("id", product_id)
        .eq("telegram_user_id", user_id)
        .execute()
    )

    return len(result.data or []) > 0


async def save_price(product_id: str, price: int, checked_at: Optional[datetime] = None) -> PriceHistory:
    """
    Record a price point in the price history.

    Args:
        product_id: Product UUID.
        price: Price value to record.
        checked_at: Timestamp of check (defaults to now).

    Returns:
        PriceHistory: Created price history record.
    """
    supabase = get_supabase()

    data = {
        "product_id": product_id,
        "price": price,
    }
    
    if checked_at:
        data["checked_at"] = checked_at.isoformat()

    result = supabase.table("price_history").insert(data).execute()

    if result.data:
        saved_data = result.data[0]
        return PriceHistory(
            id=saved_data["id"],
            product_id=saved_data["product_id"],
            price=saved_data["price"],
            checked_at=datetime.fromisoformat(saved_data["checked_at"]) if saved_data.get("checked_at") else None,
        )

    raise RuntimeError("Failed to save price history")


async def update_product_price(product_id: str, new_price: int, title: Optional[str] = None, image_url: Optional[str] = None) -> None:
    """
    Update a product's last_price and last_checked_at timestamp.

    Also optionally updates title and image_url if provided.

    Args:
        product_id: Product UUID.
        new_price: New current price.
        title: Optional new title.
        image_url: Optional new image URL.
    """
    supabase = get_supabase()

    now = datetime.now(timezone.utc).isoformat()
    
    data = {
        "last_price": new_price,
        "last_checked_at": now,
    }

    if title:
        data["title"] = title
    if image_url:
        data["image_url"] = image_url

    supabase.table("products").update(data).eq("id", product_id).execute()


async def toggle_product_active(product_id: str, is_active: bool) -> bool:
    """
    Toggle a product's active status.

    Args:
        product_id: Product UUID.
        is_active: New active status.

    Returns:
        bool: True if update succeeded.
    """
    supabase = get_supabase()

    result = supabase.table("products").update({"is_active": is_active}).eq("id", product_id).execute()
    
    return len(result.data or []) > 0
