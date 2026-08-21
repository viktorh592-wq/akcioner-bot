"""Yandex Market parser."""

import logging
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)


class YandexMarketParser(BaseParser):
    """Parser for Yandex Market (market.yandex.ru)."""
    
    marketplace = "yandex"
    url_patterns = [r"market\.yandex\.ru", r"yandex\.ru.*market"]
    
    async def parse(self, url: str) -> dict:
        """
        Parse a Yandex Market product page.
        
        Args:
            url: Product page URL.
            
        Returns:
            dict: Dictionary with 'title', 'price', and 'image_url'.
            
        Raises:
            ParseError: If parsing fails.
        """
        try:
            html = await self._fetch_with_retry(url, use_playwright=True)
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract title
            title_elem = soup.find("h1", {"data-autotest": "productName"})
            if not title_elem:
                title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
            
            # Extract price - Yandex Market has complex pricing
            price_elem = (
                soup.find("span", class_="ZNfI8")  # Main price
                or soup.find("div", class_="_2QpCa")  # Alternative
                or soup.find("span", data_autotest="offer-price")
            )
            
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price = self._extract_price(price_text)
            else:
                price = None
            
            # Extract image
            image_elem = soup.find("meta", property="og:image")
            image_url = image_elem.get("content") if image_elem else None
            
            if not price:
                raise ParseError("Could not extract price from Yandex Market page")
            
            logger.info(f"Parsed Yandex Market product: {title[:50]}... - {price} RUB")
            
            return {
                "title": title,
                "price": price,
                "image_url": image_url,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse Yandex Market URL {url}: {e}")
            raise ParseError(f"Yandex Market parse error: {e}")
