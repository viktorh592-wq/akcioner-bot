"""Price checker scheduler using APScheduler."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.models import (
    Product,
    get_products_by_user,
    update_product_price,
    save_price,
)
from app.db.supabase_client import get_supabase
from app.notifications.notifier import send_price_drop_notification
from app.parsers.base import get_parser, ParseError

logger = logging.getLogger(__name__)


class PriceCheckerScheduler:
    """
    Scheduler for periodic price checking.

    Uses APScheduler to run price checks at regular intervals
    for all active products in the database.
    """

    def __init__(self, check_interval_minutes: int = 10):
        """
        Initialize the price checker scheduler.

        Args:
            check_interval_minutes: How often to run the checker (in minutes).
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
        """Stop the scheduler gracefully."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Price checker scheduler stopped")

    async def _check_all_prices(self) -> None:
        """
        Check prices for all active products.

        This method is called by the scheduler at regular intervals.
        It fetches all active products that are due for checking,
        parses their current prices, and sends notifications if prices
        have entered the user's target range.
        """
        logger.info("Starting scheduled price check...")

        try:
            # Get Supabase client
               supabase = get_supabase()

            # Get all active products that need checking
            # (last_checked_at is null OR older than check_interval_hours)
            now = datetime.utcnow()
            response = (
                supabase.table("products")
                .select("*")
                .eq("is_active", True)
                .execute()
            )

            if not response.data:
                logger.info("No active products to check")
                return

            products_data = response.data
            logger.info(f"Found {len(products_data)} active products")

            checked_count = 0
            notified_count = 0

            for product_data in products_data:
                # Check if product is due for checking
                last_checked = product_data.get("last_checked_at")
                check_interval_hours = product_data.get("check_interval_hours", 24)

                if last_checked:
                    last_checked_dt = datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
                    time_since_check = now - last_checked_dt.replace(tzinfo=None)
                    
                    if time_since_check < timedelta(hours=check_interval_hours):
                        # Not due yet
                        continue

                # Product is due for checking
                try:
                    result = await self.check_product_price(product_data)
                    checked_count += 1

                    if result:
                        notified_count += 1

                    # Small delay between requests to avoid rate limiting
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error checking product {product_data.get('id')}: {e}")
                    continue

            logger.info(
                f"Price check completed: checked {checked_count} products, "
                f"sent {notified_count} notifications"
            )

        except Exception as e:
            logger.error(f"Error during scheduled price check: {e}")

    async def check_product_price(self, product_data: dict) -> Optional[dict]:
        """
        Check the price of a single product.

        Args:
            product_data: Product data from database.

        Returns:
            dict | None: Price change information if notification sent, None otherwise.
        """
        product_id = product_data["id"]
        url = product_data["url"]
        telegram_user_id = product_data["telegram_user_id"]
        min_price = product_data.get("min_price")
        max_price = product_data.get("max_price")
        last_price = product_data.get("last_price")
        title = product_data.get("title", "Unknown Product")

        try:
            # Parse current price
            parser = get_parser(url)
            result = await parser.parse(url)
            new_price = result["price"]

            # Update product with new price
            await update_product_price(
                product_id,
                new_price,
                title=result.get("title"),
                image_url=result.get("image_url"),
            )

            # Save price history
            await save_price(product_id, new_price)

            logger.info(
                f"Checked {title[:50]}... - new price: {new_price} RUB "
                f"(last: {last_price}, range: {min_price}-{max_price})"
            )

            # Check if price entered the target range
            # Notify if: new_price <= max_price AND (last_price was > max_price OR last_price is null)
            should_notify = False
            notification_type = ""

            if new_price <= max_price:
                if last_price is None or last_price > max_price:
                    should_notify = True
                    
                    if new_price < min_price:
                        notification_type = "🔥 BELOW your range — great deal!"
                    else:
                        notification_type = "✅ IN your range"

            if should_notify:
                logger.info(
                    f"Price drop detected for {title}: "
                    f"{last_price} -> {new_price} (range: {min_price}-{max_price})"
                )

                # Send notification
                await send_price_drop_notification(
                    user_id=telegram_user_id,
                    product_data={
                        "id": product_id,
                        "title": title,
                        "url": url,
                        "marketplace": product_data.get("marketplace"),
                        "image_url": result.get("image_url"),
                    },
                    old_price=last_price,
                    new_price=new_price,
                    min_price=min_price,
                    max_price=max_price,
                    notification_type=notification_type,
                )

                return {
                    "product_id": product_id,
                    "title": title,
                    "old_price": last_price,
                    "new_price": new_price,
                    "min_price": min_price,
                    "max_price": max_price,
                }

            return None

        except ParseError as e:
            logger.warning(f"Failed to parse product {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error checking price for product {product_id}: {e}")
            return None


# Global scheduler instance
_scheduler: Optional[PriceCheckerScheduler] = None


def get_scheduler(check_interval_minutes: int = 10) -> PriceCheckerScheduler:
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
            # Convert Product model to dict for check_product_price
            product_data = {
                "id": product.id,
                "telegram_user_id": product.telegram_user_id,
                "url": product.url,
                "marketplace": product.marketplace,
                "title": product.title,
                "image_url": product.image_url,
                "min_price": product.min_price,
                "max_price": product.max_price,
                "last_price": product.last_price,
                "check_interval_hours": product.check_interval_hours,
            }
            await scheduler.check_product_price(product_data)

        logger.info(f"Completed price check for user {user_id}")

    except Exception as e:
        logger.error(f"Error running price check for user {user_id}: {e}")
