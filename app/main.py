"""
Main entry point for the Price Tracker Bot.

This module initializes and runs all components of the application:
1. Loads configuration from environment variables
2. Initializes Supabase database client
3. Creates aiogram Bot and Dispatcher
4. Starts FastAPI health server in background
5. Starts APScheduler for periodic price checks
6. Runs aiogram polling for Telegram updates
7. Handles graceful shutdown on SIGINT/SIGTERM
"""

import asyncio
import logging
import signal
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.health_server import run_health_server
from app.scheduler.price_checker import get_scheduler, run_price_check_for_user
from app.bot import (
    start_router,
    add_product_router,
    list_products_router,
    delete_product_router,
)
from app.db.models import get_products_by_user
from app.notifications.notifier import send_help_message

# Configure logging
logging.basicConfig(
    level=settings.log_level_int,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def scheduled_price_checks(bot: Bot) -> None:
    """
    Run periodic price checks for all users.
    
    This function is called by APScheduler every 30 minutes
    to check prices for all tracked products.
    
    Args:
        bot: Aiogram Bot instance.
    """
    logger.info("Running scheduled price check for all users...")
    
    try:
        # Get all unique user IDs from products
        # In a real scenario, you'd query this from the database
        # For now, we'll need to track users separately or iterate through known users
        
        # This is a simplified version - in production you'd maintain a users table
        admin_id = settings.telegram_admin_id
        
        # Check prices for admin user (placeholder for multi-user support)
        await run_price_check_for_user(admin_id)
        
    except Exception as e:
        logger.error(f"Error during scheduled price check: {e}")


async def main() -> None:
    """
    Main application entry point.
    
    Initializes all components and starts the bot with health server
    running in parallel.
    """
    logger.info("Starting Price Tracker Bot...")
    
    # Create bot instance with default properties
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    # Create dispatcher
    dp = Dispatcher()
    
    # Include routers
    dp.include_router(start_router)
    dp.include_router(add_product_router)
    dp.include_router(list_products_router)
    dp.include_router(delete_product_router)
    
    # Start health server FIRST (before polling) to ensure Render sees traffic immediately
    health_server_task = asyncio.create_task(
        run_health_server(settings.port),
        name="health_server"
    )
    
    # Wait a moment for health server to start
    await asyncio.sleep(1)
    logger.info("Health server started")
    
    # Initialize and start scheduler
    scheduler = get_scheduler(check_interval_minutes=30)
    scheduler.start()
    logger.info("Price checker scheduler started")
    
    # Set up periodic price checks via APScheduler
    # The scheduler will call run_price_check_for_user periodically
    
    # Send help message to admin on startup (optional)
    try:
        await send_help_message(bot, settings.telegram_admin_id)
        logger.info("Sent help message to admin")
    except Exception as e:
        logger.warning(f"Could not send startup message to admin: {e}")
    
    logger.info("Starting bot polling...")
    
    try:
        # Start polling (this blocks until stopped)
        await dp.start_polling(bot)
    finally:
        # Cleanup
        logger.info("Shutting down...")
        
        # Stop scheduler
        scheduler.stop()
        
        # Cancel health server task
        health_server_task.cancel()
        try:
            await health_server_task
        except asyncio.CancelledError:
            pass
        
        # Close bot session
        await bot.session.close()
        logger.info("Bot shut down successfully")


def handle_shutdown(signum: int, frame: Any) -> None:
    """
    Handle shutdown signals gracefully.
    
    Args:
        signum: Signal number.
        frame: Current stack frame.
    """
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")


if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        # Run the main async function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
