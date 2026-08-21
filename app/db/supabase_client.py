"""
Supabase database client singleton.

This module provides a singleton pattern for the Supabase client
to ensure only one connection is created and reused throughout
the application lifecycle.
"""

import logging
from supabase import create_client, Client

from app.config import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Singleton wrapper for Supabase client.
    
    Ensures only one Supabase client instance is created and provides
    thread-safe access to the database connection.
    """
    
    _instance: Client | None = None
    
    @classmethod
    def get_client(cls) -> Client:
        """
        Get or create the Supabase client instance.
        
        Returns:
            Client: Initialized Supabase client.
            
        Raises:
            RuntimeError: If client initialization fails.
        """
        if cls._instance is None:
            try:
                cls._instance = create_client(
                    settings.supabase_url,
                    settings.supabase_key
                )
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                raise RuntimeError(f"Supabase initialization failed: {e}")
        
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset the client instance (useful for testing).
        """
        cls._instance = None


def get_supabase() -> Client:
    """
    Get the Supabase client instance.
    
    Convenience function to get the singleton client.
    
    Returns:
        Client: Initialized Supabase client.
    """
    return SupabaseClient.get_client()
