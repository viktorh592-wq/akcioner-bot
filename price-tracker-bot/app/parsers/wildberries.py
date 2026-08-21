"""Wildberries marketplace parser."""

import logging
from typing import Optional
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)


class WildberriesParser(BaseParser):
    """Parser for Wildberries marketplace (wb.ru)."""
    
    marketplace = "wildberries"
    url_patterns = [r"wildberries\.ru", r"wb\.ru"]
    
    async def parse(self, url: str) -> dict:
        """
        Parse a Wildberries product page.
        
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
            title_elem = soup.find("h1", {"class": "product-page-name__header"})
            if not title_elem:
                title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
            
            # Extract price - Wildberries uses dynamic pricing
            price_elem = (
                soup.find("span", {"class": "price__current-price"})
                or soup.find("span", class_="price-block__price")
                or soup.find("span", class_="product-page-card__price")
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
                raise ParseError("Could not extract price from Wildberries page")
            
            logger.info(f"Parsed Wildberries product: {title[:50]}... - {price} RUB")
            
            return {
                "title": title,
                "price": price,
                "image_url": image_url,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse Wildberries URL {url}: {e}")
            raise ParseError(f"Wildberries parse error: {e}")
