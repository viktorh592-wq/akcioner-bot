"""Wildberries parser with httpx + Playwright fallback."""

import asyncio
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)

API_URL = "https://card.wb.ru/cards/v2/detail"


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

    @staticmethod
    def _extract_price(text: str) -> Optional[float]:
        digits = re.sub(r"[^\d]", "", text.replace(" ", "").replace(",", "."))
        if not digits:
            return None
        try:
            return float(digits)
        except ValueError:
            return None

    async def _try_httpx(self, article: str) -> Optional[dict]:
        """Fast JSON API path. Returns None if blocked."""
        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",
            "nm": article,
            "spp": "30",
            "ab_testing": "1",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.wildberries.ru",
            "Referer": f"https://www.wildberries.ru/catalog/{article}/detail.aspx",
            "Connection": "keep-alive",
        }

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(API_URL, params=params, headers=headers)
                if resp.status_code == 403:
                    logger.info(f"WB blocked httpx for {article}, will fallback to Playwright")
                    return None
                resp.raise_for_status()
                data = resp.json()

            products = data.get("data", {}).get("products", [])
            if not products:
                return None

            item = products[0]
            title = item.get("name") or item.get("productName") or "Товар Wildberries"

            price = None
            sizes = item.get("sizes") or []
            if sizes:
                price_obj = sizes[0].get("price", {})
                total = price_obj.get("total") or price_obj.get("product") or price_obj.get("basic")
                if total:
                    price = total / 100

            if price is None:
                sale = item.get("salePriceU") or item.get("priceU")
                if sale:
                    price = sale / 100

            if not price:
                return None

            image_url = None
            raw_img = item.get("imageUrl") or ""
            if raw_img:
                image_url = raw_img if raw_img.startswith("http") else f"https://{raw_img}"

            return {"title": title, "price": price, "image_url": image_url}

        except Exception as e:
            logger.warning(f"WB httpx failed for {article}: {e}")
            return None

    async def _try_playwright(self, article: str) -> dict:
        """Fallback: open real WB page in headless Chromium."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ParseError("Playwright не установлен — не могу обойти блокировку WB")

        product_url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="ru-RU",
                )
                
                # Mask webdriver
                page = await context.new_page()
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)

                response = await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                
                if response and response.status == 403:
                    await browser.close()
                    raise ParseError("Wildberries полностью заблокировал сервер — возможно, IP в чёрном списке")

                # Wait a bit for dynamic content
                await page.wait_for_timeout(2000)
                html = await page.content()
                await browser.close()

            soup = BeautifulSoup(html, "html.parser")

            # Title
            title_elem = soup.find("h1", {"class": re.compile(r"product-page__header")}) or soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Товар Wildberries"

            # Price — WB uses several class patterns
            price = None
            for selector in [
                "span.product-page-price__product-price",
                "span.price-block__price",
                "span.price__current-price",
                "span.product-page-card__price",
                "span.product-page-price",
            ]:
                elem = soup.select_one(selector)
                if elem:
                    price = self._extract_price(elem.get_text(strip=True))
                    if price:
                        break

            # If still no price, try meta tag
            if not price:
                meta = soup.find("meta", {"property": "product:price:amount"})
                if meta:
                    try:
                        price = float(meta.get("content"))
                    except (ValueError, TypeError):
                        pass

            if not price:
                raise ParseError("Не удалось найти цену на странице Wildberries")

            # Image
            image_url = None
            meta_img = soup.find("meta", property="og:image")
            if meta_img:
                image_url = meta_img.get("content")

            logger.info(f"WB parsed via Playwright (article {article}): {price} RUB")
            return {"title": title, "price": price, "image_url": image_url}

        except ParseError:
            raise
        except Exception as e:
            logger.error(f"WB Playwright failed for {article}: {e}")
            raise ParseError(f"Не удалось открыть страницу Wildberries: {e}")

    async def parse(self, url: str) -> dict:
        article = self._extract_article(url)
        if not article:
            raise ParseError("Не удалось найти артикул в ссылке Wildberries")

        # Try fast path first
        result = await self._try_httpx(article)
        if result:
            logger.info(f"WB parsed via httpx (article {article})")
            return result

        # Fallback to Playwright
        return await self._try_playwright(article)
