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

# Hard cap for a single Playwright page load. Marketplace pages (Ozon, WB…)
# keep long-polling analytics connections open and never reach "networkidle",
# so we use "domcontentloaded" plus a fixed settle delay instead.
PAGE_LOAD_TIMEOUT = 45
BROWSER_CLOSE_TIMEOUT = 10


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
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text

    async def _fetch_with_playwright(self, url: str) -> str:
        """
        Fetch URL using Playwright (for JavaScript-rendered pages).

        Uses "domcontentloaded" plus a short settle delay: marketplace pages
        never reach "networkidle" and would always time out. The browser is
        closed in a finally block with its own timeout so a stuck browser
        can never hang the whole parse.

        Args:
            url: URL to fetch.

        Returns:
            str: HTML content after JavaScript execution.
        """
        browser: Optional[Browser] = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-blink-features=AutomationControlled",
                    ]
                )

                page: Page = await browser.new_page(
                    user_agent=self.user_agent,
                    viewport={"width": 1920, "height": 1080}
                )
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{get: () => undefined});"
                )

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_LOAD_TIMEOUT * 1000,
                )

                # Give dynamic content a moment to render, then grab the HTML.
                await asyncio.sleep(3)

                return await page.content()

        finally:
            if browser is not None:
                close_exc: Optional[BaseException] = None
                try:
                    await asyncio.wait_for(browser.close(), timeout=BROWSER_CLOSE_TIMEOUT)
                except BaseException as e:  # incl. CancelledError — cleanup is bulletproof
                    close_exc = e
                if close_exc is not None:
                    try:
                        browser.process.kill()  # type: ignore[attr-defined]
                    except Exception:
                        pass

    def _extract_price(self, text: str) -> Optional[float]:
        """
        Extract numeric price from text string.

        Handles various formats:
        - "1 234 ₽"
        - "1,234.56" (US: comma thousands, dot decimal)
        - "1.234,56" (EU: dot thousands, comma decimal)
        - "1234,56 руб." (RU: comma decimal)
        - "1000"

        Args:
            text: Text containing price information.

        Returns:
            float | None: Extracted price or None if not found.
        """
        # Remove currency symbols and extra spaces (incl. non-breaking ones)
        cleaned = re.sub(r"[^\d,.]", "", text.replace(" ", "").replace("\xa0", ""))
        # Strip separators at the edges — e.g. the trailing dot in "руб."
        cleaned = cleaned.strip(".,")
        if not cleaned:
            return None

        if "," in cleaned and "." in cleaned:
            # Both separators present: the rightmost one is the decimal point.
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Single separator type: comma is decimal (Russian convention).
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
