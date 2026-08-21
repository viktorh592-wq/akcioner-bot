"""Price checker scheduler using APScheduler."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.models import (
    Product,
    get_products_by_user,
    update_product_price,
    save_price,
)
from app.notifications.notifier import send_price_drop_notification
from app.parsers.base import get_parser, ParseError

logger = logging.getLogger(__name__)


class PriceCheckerScheduler:
    """
    Scheduler for periodic price checking.
    
    Uses APScheduler to run price checks at regular intervals
    for all active products in the database.
    """
    
    def __init__(self, check_interval_minutes: int = 30):
        """
        Initialize the price checker scheduler.
        
        Args:
            check_interval_minutes: How often to check prices (in minutes).
        """
        self.scheduler = AsyncIOScheduler()
        self.check_interval = check_interval_minutes
        self._is_running = False
    
    def start(self) -> None:
        """
        Start the scheduler.
        
        Schedules the price check job to run at the configured interval.
        """
        self.scheduler.add_job(
            self._check_all_prices,
            trigger=IntervalTrigger(minutes=self.check_interval),
            id="price_check",
            name="Check all product prices",
            replace_existing=True,
        )
        
        self.scheduler.start()
        self._is_running = True
        
        logger.info(f"Price checker scheduler started (interval: {self.check_interval} minutes)")
    
    def stop(self) -> None:
        """
        Stop the scheduler gracefully.
        """
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Price checker scheduler stopped")
    
    async def _check_all_prices(self) -> None:
        """
        Check prices for all active products.
        
        This method is called by the scheduler at regular intervals.
        It fetches all active products, parses their current prices,
        and sends notifications if prices have dropped below target.
        """
        logger.info("Starting scheduled price check...")
        
        try:
            # Get all active products from all users
            # Note: In a real multi-user scenario, you'd iterate through users
            # For now, we'll need to get products differently
            # This will be refined when we implement user management
            
            # We need to get products for each user - this requires knowing user IDs
            # For the initial implementation, we'll handle this in main.py
            # where we have access to user data
            
            logger.info("Scheduled price check completed")
            
        except Exception as e:
            logger.error(f"Error during scheduled price check: {e}")
    
    async def check_product_price(self, product: Product) -> Optional[dict]:
        """
        Check the price of a single product.
        
        Args:
            product: Product to check.
            
        Returns:
            dict | None: Price change information if price dropped, None otherwise.
        """
        try:
            parser = get_parser(product.url)
            result = await parser.parse(product.url)
            
            new_price = result["price"]
            old_price = product.current_price
            
            # Update product with new price
            await update_product_price(
                product.id,  # type: ignore
                new_price,
                title=result.get("title"),
                image_url=result.get("image_url")
            )
            
            # Save price history
            await save_price(product.id, new_price)  # type: ignore
            
            # Check if price dropped below target
            if new_price <= product.target_price:
                logger.info(
                    f"Price drop detected for {product.title}: "
                    f"{old_price} -> {new_price} (target: {product.target_price})"
                )
                
                return {
                    "product": product,
                    "old_price": old_price,
                    "new_price": new_price,
                    "target_price": product.target_price,
                }
            
            return None
            
        except ParseError as e:
            logger.warning(f"Failed to parse product {product.url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error checking price for product {product.id}: {e}")
            return None


# Global scheduler instance
_scheduler: Optional[PriceCheckerScheduler] = None


def get_scheduler(check_interval_minutes: int = 30) -> PriceCheckerScheduler:
    """
    Get or create the global scheduler instance.
    
    Args:
        check_interval_minutes: Check interval in minutes.
        
    Returns:
        PriceCheckerScheduler: Scheduler instance.
    """
    global _scheduler
    
    if _scheduler is None:
        _scheduler = PriceCheckerScheduler(check_interval_minutes)
    
    return _scheduler


async def run_price_check_for_user(user_id: int) -> None:
    """
    Run price checks for all products belonging to a user.
    
    This is a convenience function that can be called periodically
    to check prices for a specific user's products.
    
    Args:
        user_id: Telegram user ID.
    """
    try:
        products = await get_products_by_user(user_id, active_only=True)
        
        if not products:
            return
        
        logger.info(f"Checking prices for {len(products)} products (user {user_id})")
        
        for product in products:
            scheduler = get_scheduler()
            result = await scheduler.check_product_price(product)
            
            if result:
                # Send notification about price drop
                await send_price_drop_notification(
                    user_id=user_id,
                    product=result["product"],
                    old_price=result["old_price"],
                    new_price=result["new_price"],
                    target_price=result["target_price"],
                )
        
        logger.info(f"Completed price check for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error running price check for user {user_id}: {e}")
