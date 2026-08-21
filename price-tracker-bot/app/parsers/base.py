"""
Base parser module for marketplace price extraction.

This module provides an abstract base class for all marketplace parsers
with common functionality like HTTP requests, User-Agent rotation,
and retry logic with exponential backoff.
"""

import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)


# User-Agent strings for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Request timeout in seconds
REQUEST_TIMEOUT = 30


class ParseError(Exception):
    """Exception raised when parsing fails."""
    pass


class BaseParser(ABC):
    """
    Abstract base class for marketplace parsers.
    
    All marketplace-specific parsers must inherit from this class
    and implement the required methods.
    """
    
    # Marketplace name (e.g., 'wildberries', 'ozon')
    marketplace: str = ""
    
    # URL patterns that this parser can handle
    url_patterns: list[str] = []
    
    def __init__(self) -> None:
        """Initialize the parser with a random User-Agent."""
        self.user_agent = random.choice(USER_AGENTS)
    
    @abstractmethod
    async def parse(self, url: str) -> dict:
        """
        Parse a product page and extract price information.
        
        Args:
            url: Product page URL.
            
        Returns:
            dict: Dictionary containing 'title', 'price', and 'image_url'.
            
        Raises:
            ParseError: If parsing fails.
        """
        pass
    
    def can_parse(self, url: str) -> bool:
        """
        Check if this parser can handle the given URL.
        
        Args:
            url: URL to check.
            
        Returns:
            bool: True if this parser can handle the URL.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        for pattern in self.url_patterns:
            if re.search(pattern, domain, re.IGNORECASE):
                return True
        
        return False
    
    async def _fetch_with_retry(
        self,
        url: str,
        max_retries: int = 3,
        use_playwright: bool = False
    ) -> str:
        """
        Fetch URL content with retry logic and exponential backoff.
        
        Args:
            url: URL to fetch.
            max_retries: Maximum number of retry attempts.
            use_playwright: If True, use Playwright instead of httpx.
            
        Returns:
            str: HTML content of the page.
            
        Raises:
            ParseError: If all retries fail.
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(max_retries):
            try:
                if use_playwright:
                    return await self._fetch_with_playwright(url)
                else:
                    return await self._fetch_with_httpx(url)
                    
            except Exception as e:
                last_error = e
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time:.2f}s"
                )
                await asyncio.sleep(wait_time)
        
        raise ParseError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")
    
    async def _fetch_with_httpx(self, url: str) -> str:
        """
        Fetch URL using httpx with rotating User-Agent.
        
        Args:
            url: URL to fetch.
            
        Returns:
            str: HTML content.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text
    
    async def _fetch_with_playwright(self, url: str) -> str:
        """
        Fetch URL using Playwright (for JavaScript-rendered pages).
        
        Args:
            url: URL to fetch.
            
        Returns:
            str: HTML content after JavaScript execution.
        """
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            
            try:
                page: Page = await browser.new_page(
                    user_agent=self.user_agent,
                    viewport={"width": 1920, "height": 1080}
                )
                
                await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
                
                # Wait a bit for dynamic content to load
                await asyncio.sleep(2)
                
                content = await page.content()
                return content
                
            finally:
                await browser.close()
    
    def _extract_price(self, text: str) -> Optional[float]:
        """
        Extract numeric price from text string.
        
        Handles various formats:
        - "1 234 ₽"
        - "1,234.56"
        - "1234 руб."
        
        Args:
            text: Text containing price information.
            
        Returns:
            float | None: Extracted price or None if not found.
        """
        # Remove currency symbols and extra spaces
        cleaned = re.sub(r"[^\d,.]", "", text.replace(" ", ""))
        
        # Handle comma as decimal separator (Russian format)
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None


def get_parser(url: str) -> BaseParser:
    """
    Factory function to get the appropriate parser for a URL.
    
    Args:
        url: Product URL to parse.
        
    Returns:
        BaseParser: Parser instance capable of handling the URL.
        
    Raises:
        ParseError: If no suitable parser is found.
    """
    # Import all parsers here to avoid circular imports
    from app.parsers.wildberries import WildberriesParser
    from app.parsers.ozon import OzonParser
    from app.parsers.yandex import YandexMarketParser
    from app.parsers.aliexpress import AliExpressParser
    from app.parsers.dns import DNSParser
    from app.parsers.mvideo import MVideoParser
    
    parsers = [
        WildberriesParser(),
        OzonParser(),
        YandexMarketParser(),
        AliExpressParser(),
        DNSParser(),
        MVideoParser(),
    ]
    
    for parser in parsers:
        if parser.can_parse(url):
            logger.info(f"Selected parser: {parser.marketplace}")
            return parser
    
    raise ParseError(f"No parser found for URL: {url}")
