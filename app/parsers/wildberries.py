"""Wildberries parser via public JSON API (fast, no browser needed)."""

import logging
import re
from typing import Optional

import httpx

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)

API_URL = "https://card.wb.ru/cards/detail"


class WildberriesParser(BaseParser):
    """Parser for Wildberries marketplace (wb.ru)."""

    marketplace = "wildberries"
    url_patterns = [r"wildberries\.ru", r"wb\.ru"]

    @staticmethod
    def _extract_article(url: str) -> Optional[str]:
        m = re.search(r"/catalog/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"nm=(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"(\d{6,})", url)
        return m.group(1) if m else None

    async def parse(self, url: str) -> dict:
        article = self._extract_article(url)
        if not article:
            raise ParseError("Не удалось найти артикул в ссылке Wildberries")

        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",
            "nm": article,
            "spp": "30",
        }
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(API_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            products = data.get("data", {}).get("products", [])
            if not products:
                raise ParseError("Товар не найден на Wildberries — проверь ссылку")

            item = products[0]
            title = item.get("name") or item.get("productName") or "Товар Wildberries"

            price = None
            sizes = item.get("sizes") or []
            if sizes:
                price_obj = sizes[0].get("price", {})
                total = (
                    price_obj.get("total")
                    or price_obj.get("product")
                    or price_obj.get("basic")
                )
                if total:
                    price = total / 100

            if price is None:
                sale = item.get("salePriceU") or item.get("priceU")
                if sale:
                    price = sale / 100

            if not price:
                raise ParseError("Не удалось получить цену товара Wildberries")

            image_url = None
            raw_img = item.get("imageUrl") or ""
            if raw_img:
                image_url = raw_img if raw_img.startswith("http") else f"https://{raw_img}"

            logger.info(f"Parsed WB product {article}: {price} RUB")
            return {"title": title, "price": price, "image_url": image_url}

        except ParseError:
            raise
        except Exception as e:
            logger.error(f"Failed to parse WB {url}: {e}")
            raise ParseError(f"Ошибка парсинга Wildberries: {e}")
