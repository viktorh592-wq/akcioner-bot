"""
FastAPI health check server to prevent Render.com from sleeping.

This module provides a minimal FastAPI application that runs as a background
task alongside the Telegram bot polling. The /health endpoint is periodically
called by UptimeRobot to keep the service awake.
"""

import asyncio
import logging
from fastapi import FastAPI
import uvicorn

logger = logging.getLogger(__name__)


def create_health_app() -> FastAPI:
    """
    Create and configure the FastAPI health check application.
    
    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    app = FastAPI(title="Price Tracker Health Check")
    
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint for Render.com and UptimeRobot.
        
        Returns:
            dict: Status response indicating the service is healthy.
        """
        return {"status": "ok"}
    
    return app


async def run_health_server(port: int) -> None:
    """
    Run the FastAPI health server as an asyncio background task.
    
    This function starts Uvicorn server in a separate thread to avoid
    blocking the main asyncio event loop used by aiogram.
    
    Args:
        port: Port number to bind the server to.
    """
    config = uvicorn.Config(
        "app.health_server:create_health_app",
        host="0.0.0.0",
        port=port,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(config)
    
    logger.info(f"Starting health check server on port {port}")
    
    # Run server in background using asyncio.create_task
    await server.serve()
