"""Ozon marketplace parser."""

import logging
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)


class OzonParser(BaseParser):
    """Parser for Ozon marketplace (ozon.ru)."""
    
    marketplace = "ozon"
    url_patterns = [r"ozon\.ru"]
    
    async def parse(self, url: str) -> dict:
        """
        Parse an Ozon product page.
        
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
            title_elem = soup.find("h1", {"class": "rU6qf"})
            if not title_elem:
                title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
            
            # Extract price - Ozon has multiple price formats
            price_elem = (
                soup.find("span", class_="a3WpD")  # Main price
                or soup.find("div", class_="b8gXv")  # Alternative price container
                or soup.find("span", class_="e5y9c")  # Sale price
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
                raise ParseError("Could not extract price from Ozon page")
            
            logger.info(f"Parsed Ozon product: {title[:50]}... - {price} RUB")
            
            return {
                "title": title,
                "price": price,
                "image_url": image_url,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse Ozon URL {url}: {e}")
            raise ParseError(f"Ozon parse error: {e}")
