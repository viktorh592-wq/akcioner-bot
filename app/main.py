"""Application entry point.

Runs three components in a single asyncio event loop:
1. FastAPI health check server (keeps Render awake via UptimeRobot pings)
2. APScheduler price checker
3. aiogram Telegram bot (long polling)
"""

import asyncio
import logging
import sys

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI

from app.bot.handlers import (
    add_product_router,
    delete_product_router,
    list_products_router,
    start_router,
)
from app.bot.middlewares import AdminOnlyMiddleware, LoggingMiddleware
from app.config import settings
from app.db.supabase_client import get_supabase
from app.scheduler.price_checker import get_scheduler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Health check server (FastAPI)
# ---------------------------------------------------------------------------
health_app = FastAPI(title="Price Tracker Health")


@health_app.get("/health")
async def health() -> dict:
    """Health endpoint for UptimeRobot keep-alive pings."""
    return {"status": "ok"}


async def run_health_server() -> None:
    """Run the FastAPI health server inside the current event loop."""
    config = uvicorn.Config(
        health_app,
        host="0.0.0.0",
        port=settings.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    # Disable uvicorn's own signal handlers - we manage shutdown ourselves
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    await server.serve()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
async def main() -> None:
    """Start all application components and run the bot."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    logger.info("Starting Price Tracker Bot...")

    # Fail fast on bad Supabase credentials
    get_supabase()

    # Bot & dispatcher
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Middlewares (order matters: logging first, then access control)
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(AdminOnlyMiddleware())

    # Routers
    dp.include_routers(
        start_router,
        add_product_router,
        list_products_router,
        delete_product_router,
    )

    # 1) Health server as background task (Render sees HTTP traffic -> no sleep)
    health_task = asyncio.create_task(run_health_server())

    # 2) Price checker scheduler (every 10 minutes, per-product intervals respected)
    scheduler = get_scheduler(check_interval_minutes=10)
    scheduler.start()

    logger.info("All components started. Launching Telegram polling...")

    try:
        # 3) Telegram bot polling (blocks until stopped)
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        scheduler.stop()
        health_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
