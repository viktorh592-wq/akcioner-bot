"""DNS (dns-shop.ru) electronics store parser."""

import logging
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)


class DNSParser(BaseParser):
    """Parser for DNS electronics store (dns-shop.ru)."""
    
    marketplace = "dns"
    url_patterns = [r"dns-shop\.ru"]
    
    async def parse(self, url: str) -> dict:
        """
        Parse a DNS product page.
        
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
            title_elem = soup.find("h1", {"class": "product-title"})
            if not title_elem:
                title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
            
            # Extract price - DNS has specific class names
            price_elem = (
                soup.find("span", class_="product-buying-price__current-value")
                or soup.find("div", class_="regular-price")
                or soup.find("span", class_="price-format__main-value")
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
                raise ParseError("Could not extract price from DNS page")
            
            logger.info(f"Parsed DNS product: {title[:50]}... - {price} RUB")
            
            return {
                "title": title,
                "price": price,
                "image_url": image_url,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse DNS URL {url}: {e}")
            raise ParseError(f"DNS parse error: {e}")
