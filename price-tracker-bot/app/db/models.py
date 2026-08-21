"""
Database models and helper functions for the price tracker.

This module defines Pydantic models for database entities and provides
helper functions for CRUD operations with Supabase.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.db.supabase_client import get_supabase


class Product(BaseModel):
    """
    Product model representing a tracked item.
    
    Attributes:
        id: Unique product identifier (UUID).
        user_id: Telegram user ID who added this product.
        url: Product URL on the marketplace.
        title: Product title/name.
        target_price: Target price threshold for notifications.
        current_price: Current known price.
        image_url: URL to product image.
        marketplace: Name of the marketplace (e.g., 'wildberries', 'ozon').
        created_at: Timestamp when product was added.
        updated_at: Timestamp of last update.
        is_active: Whether the product is actively tracked.
    """
    id: Optional[str] = None
    user_id: int
    url: str
    title: str
    target_price: float
    current_price: Optional[float] = None
    image_url: Optional[str] = None
    marketplace: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True


class PriceHistory(BaseModel):
    """
    Price history model for tracking price changes over time.
    
    Attributes:
        id: Unique history record identifier (UUID).
        product_id: Reference to the product.
        price: Recorded price at this point in time.
        recorded_at: Timestamp when price was recorded.
    """
    id: Optional[str] = None
    product_id: str
    price: float
    recorded_at: Optional[datetime] = None


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
        "user_id": product.user_id,
        "url": product.url,
        "title": product.title,
        "target_price": product.target_price,
        "current_price": product.current_price,
        "image_url": product.image_url,
        "marketplace": product.marketplace,
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
            user_id=saved_data["user_id"],
            url=saved_data["url"],
            title=saved_data["title"],
            target_price=saved_data["target_price"],
            current_price=saved_data.get("current_price"),
            image_url=saved_data.get("image_url"),
            marketplace=saved_data["marketplace"],
            created_at=datetime.fromisoformat(saved_data["created_at"]) if saved_data.get("created_at") else None,
            updated_at=datetime.fromisoformat(saved_data["updated_at"]) if saved_data.get("updated_at") else None,
            is_active=saved_data["is_active"],
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
    
    query = supabase.table("products").select("*").eq("user_id", user_id)
    
    if active_only:
        query = query.eq("is_active", True)
    
    result = query.execute()
    
    products = []
    for row in result.data or []:
        products.append(Product(
            id=row["id"],
            user_id=row["user_id"],
            url=row["url"],
            title=row["title"],
            target_price=row["target_price"],
            current_price=row.get("current_price"),
            image_url=row.get("image_url"),
            marketplace=row["marketplace"],
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
            is_active=row["is_active"],
        ))
    
    return products


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
        .eq("user_id", user_id)
        .execute()
    )
    
    return len(result.data or []) > 0


async def save_price(product_id: str, price: float) -> PriceHistory:
    """
    Record a price point in the price history.
    
    Args:
        product_id: Product UUID.
        price: Price value to record.
        
    Returns:
        PriceHistory: Created price history record.
    """
    supabase = get_supabase()
    
    data = {
        "product_id": product_id,
        "price": price,
    }
    
    result = supabase.table("price_history").insert(data).execute()
    
    if result.data:
        saved_data = result.data[0]
        return PriceHistory(
            id=saved_data["id"],
            product_id=saved_data["product_id"],
            price=saved_data["price"],
            recorded_at=datetime.fromisoformat(saved_data["recorded_at"]) if saved_data.get("recorded_at") else None,
        )
    
    raise RuntimeError("Failed to save price history")


async def update_product_price(product_id: str, price: float, title: Optional[str] = None, image_url: Optional[str] = None) -> None:
    """
    Update a product's current price and optionally title/image.
    
    Args:
        product_id: Product UUID.
        price: New current price.
        title: Optional new title.
        image_url: Optional new image URL.
    """
    supabase = get_supabase()
    
    data = {
        "current_price": price,
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    if title:
        data["title"] = title
    if image_url:
        data["image_url"] = image_url
    
    supabase.table("products").update(data).eq("id", product_id).execute()


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
            user_id=row["user_id"],
            url=row["url"],
            title=row["title"],
            target_price=row["target_price"],
            current_price=row.get("current_price"),
            image_url=row.get("image_url"),
            marketplace=row["marketplace"],
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
            is_active=row["is_active"],
        )
    
    return None
