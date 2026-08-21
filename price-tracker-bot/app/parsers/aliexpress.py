"""AliExpress parser."""

import logging
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)


class AliExpressParser(BaseParser):
    """Parser for AliExpress (aliexpress.ru, aliexpress.com)."""
    
    marketplace = "aliexpress"
    url_patterns = [r"aliexpress\.ru", r"aliexpress\.com"]
    
    async def parse(self, url: str) -> dict:
        """
        Parse an AliExpress product page.
        
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
            title_elem = soup.find("h1", {"data-testid": "product-title"})
            if not title_elem:
                title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
            
            # Extract price - AliExpress has multiple price formats
            price_elem = (
                soup.find("span", class_="_1e35y8t")  # Main price
                or soup.find("span", class_="product-price-current")
                or soup.find("div", class_="product-price-value")
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
                raise ParseError("Could not extract price from AliExpress page")
            
            logger.info(f"Parsed AliExpress product: {title[:50]}... - {price}")
            
            return {
                "title": title,
                "price": price,
                "image_url": image_url,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse AliExpress URL {url}: {e}")
            raise ParseError(f"AliExpress parse error: {e}")
