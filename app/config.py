"""
Application configuration using pydantic-settings.

This module provides a Settings class that loads and validates
all environment variables required by the application.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings are validated at startup to ensure the application
    fails fast if configuration is incorrect.
    """

    # Telegram Bot Configuration
    telegram_bot_token: str
    telegram_admin_id: int

    # Supabase Database Configuration
    supabase_url: str
    supabase_key: str

    # Server Configuration
    port: int = 8000

    # Logging Configuration
    log_level: str = "INFO"

    # Price Check Interval (minutes)
    check_interval_minutes: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def log_level_int(self) -> int:
        """Convert log level string to logging constant."""
        import logging
        return getattr(logging, self.log_level.upper(), logging.INFO)


# Global settings instance
settings = Settings()
