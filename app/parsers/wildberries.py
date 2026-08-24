"""Wildberries parser with multi-tier fallback.

Tier 1: card.wb.ru JSON API via curl_cffi (Chrome TLS impersonation) — fast path.
Tier 2: basket CDN card.json — metadata (title/brand/image) that always works.
Tier 3: Playwright headless browser — handles the wbaas antibot challenge.

Every tier has a hard timeout, so parse() can never hang forever.
"""

import asyncio
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)

API_URL = "https://card.wb.ru/cards/v2/detail"

# How long each tier is allowed to take (seconds)
TIER_API_TIMEOUT = 12
TIER_BASKET_TIMEOUT = 10
TIER_PLAYWRIGHT_BUDGET = 75


class WildberriesParser(BaseParser):
    """Parser for Wildberries marketplace (wildberries.ru / wb.ru)."""

    marketplace = "wildberries"
    url_patterns = [r"wildberries\.ru", r"wb\.ru"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _basket_paths(article: str) -> tuple[int, int]:
        """Return (vol, part) for the basket CDN URL scheme."""
        nm = int(article)
        return nm // 100000, nm // 1000

    # ------------------------------------------------------------------
    # Tier 1: card.wb.ru via curl_cffi (Chrome TLS impersonation)
    # ------------------------------------------------------------------

    async def _try_card_api(self, article: str) -> Optional[dict]:
        """Query the public card API impersonating Chrome's TLS fingerprint.

        Plain httpx gets 403 here because WB's WAF fingerprints the
        TLS handshake; curl_cffi repeats the exact Chrome handshake.
        """
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            logger.warning("curl_cffi is not installed, skipping API tier")
            return None

        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",
            "nm": article,
            "spp": "30",
            "ab_testing": "1",
        }
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.wildberries.ru",
            "Referer": f"https://www.wildberries.ru/catalog/{article}/detail.aspx",
        }

        try:
            async with AsyncSession() as s:
                resp = await asyncio.wait_for(
                    s.get(
                        API_URL,
                        params=params,
                        headers=headers,
                        impersonate="chrome",
                        timeout=TIER_API_TIMEOUT,
                    ),
                    timeout=TIER_API_TIMEOUT + 3,
                )
                if resp.status_code != 200:
                    logger.info(
                        f"WB card API returned {resp.status_code} for {article}, "
                        f"falling through to next tier"
                    )
                    return None
                data = resp.json()
        except asyncio.TimeoutError:
            logger.info(f"WB card API timed out for {article}")
            return None
        except Exception as e:
            logger.warning(f"WB card API failed for {article}: {e}")
            return None

        try:
            products = (data.get("data") or {}).get("products") or []
            if not products:
                logger.info(f"WB card API: no products for {article}")
                return None
            item = products[0]
        except Exception:
            return None

        title = item.get("name") or item.get("productName") or "Товар Wildberries"
        price = self._price_from_item(item)

        if not price:
            return None

        logger.info(f"WB parsed via card API (article {article}): {price} RUB")
        return {"title": title, "price": price, "image_url": None}

    @staticmethod
    def _price_from_item(item: dict) -> Optional[float]:
        """Extract price (in rubles) from a card API product item."""
        price = None
        sizes = item.get("sizes") or []
        for size in sizes:
            price_obj = size.get("price") or {}
            total = (
                price_obj.get("total")
                or price_obj.get("product")
                or price_obj.get("basic")
            )
            if total:
                price = total / 100
                break
        if price is None:
            sale = item.get("salePriceU") or item.get("priceU")
            if sale:
                price = sale / 100
        return price

    # ------------------------------------------------------------------
    # Tier 2: basket CDN card.json (metadata only, no price)
    # ------------------------------------------------------------------

    async def _try_basket_card(self, article: str) -> Optional[dict]:
        """Fetch product metadata from the basket CDN.

        The CDN is not behind the antibot, so this works even from
        datacenter IPs. It has the title/brand/image but no price.
        """
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            return None

        vol, part = self._basket_paths(article)

        async def fetch_from_basket(basket: int) -> Optional[dict]:
            url = (
                f"https://basket-{basket:02d}.wbbasket.ru"
                f"/vol{vol}/part{part}/{article}/info/ru/card.json"
            )
            try:
                async with AsyncSession() as s:
                    resp = await asyncio.wait_for(
                        s.get(
                            url,
                            headers={"User-Agent": self.user_agent, "Accept": "*/*"},
                            impersonate="chrome",
                            timeout=6,
                        ),
                        timeout=8,
                    )
                if resp.status_code != 200:
                    return None
                card = resp.json()
            except Exception:
                return None
            if not card or not card.get("imt_name"):
                return None
            image_url = (
                f"https://basket-{basket:02d}.wbbasket.ru"
                f"/vol{vol}/part{part}/{article}/images/c246x328/1.webp"
            )
            brand = (card.get("selling") or {}).get("brand_name") or ""
            title = card.get("imt_name")
            if brand and brand.lower() not in title.lower():
                title = f"{title} ({brand})"
            return {"title": title, "image_url": image_url}

        # Probe likely baskets in parallel. The vol->basket mapping changed
        # over time, so we try a spread of buckets instead of hardcoding.
        candidates = [1, 2, 3, 4, 5, 8, 10, 12, 14, 16, 18, 20, 25, 30, 33, 40, 50, 60]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(fetch_from_basket(b) for b in candidates),
                    return_exceptions=True,
                ),
                timeout=TIER_BASKET_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.info(f"WB basket CDN timed out for {article}")
            return None

        for res in results:
            if isinstance(res, dict):
                logger.info(f"WB basket card found for {article}: {res['title'][:50]}")
                return res
        return None

    # ------------------------------------------------------------------
    # Tier 3: Playwright with antibot-challenge wait
    # ------------------------------------------------------------------

    async def _try_playwright(self, article: str) -> dict:
        """Open the real WB page in headless Chromium.

        WB serves an antibot challenge page first; a real browser solves
        it after ~60s and the page reloads with the actual content. We
        monitor for the real page within a bounded time budget.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ParseError("Playwright не установлен — не могу обойти блокировку WB")

        product_url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        browser = None
        deadline = asyncio.get_event_loop().time() + TIER_PLAYWRIGHT_BUDGET

        try:
            async with async_playwright() as p:
                browser = await asyncio.wait_for(
                    p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-extensions",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-background-networking",
                            "--disable-renderer-backgrounding",
                            "--mute-audio",
                        ],
                    ),
                    timeout=25,
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    locale="ru-RU",
                )
                page = await context.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{get: () => undefined});"
                )

                try:
                    await asyncio.wait_for(
                        page.goto(product_url, wait_until="domcontentloaded", timeout=30000),
                        timeout=35,
                    )
                except asyncio.TimeoutError:
                    raise ParseError(
                        "Wildberries слишком долго отвечал. Попробуй ещё раз через минуту."
                    )

                # Poll for the real product page: the antibot challenge
                # ("Что-то не так... Подозрительная активность") reloads the
                # page automatically after ~60s; keep checking until budget.
                html = ""
                while asyncio.get_event_loop().time() < deadline:
                    await page.wait_for_timeout(3000)
                    try:
                        html = await page.content()
                    except Exception:
                        break

                    price = self._find_price_in_html(html)
                    if price:
                        title = self._find_title_in_html(html) or "Товар Wildberries"
                        image_url = None
                        m = re.search(
                            r'property="og:image"\s+content="([^"]+)"', html
                        ) or re.search(r'content="([^"]+)"\s+property="og:image"', html)
                        if m:
                            image_url = m.group(1)
                        logger.info(
                            f"WB parsed via Playwright (article {article}): {price} RUB"
                        )
                        return {"title": title, "price": price, "image_url": image_url}

                raise ParseError(
                    "Wildberries не отдал страницу товара (антибот-защита). "
                    "Попробуй ещё раз через несколько минут."
                )

        except ParseError:
            raise
        except asyncio.TimeoutError:
            raise ParseError("Не удалось запустить браузер для обхода защиты WB")
        except Exception as e:
            logger.error(f"WB Playwright failed for {article}: {e}")
            raise ParseError(f"Не удалось открыть страницу Wildberries: {e}")
        finally:
            if browser is not None:
                close_exc: BaseException | None = None
                try:
                    await asyncio.wait_for(browser.close(), timeout=10)
                except BaseException as e:  # incl. CancelledError — cleanup is bulletproof
                    close_exc = e
                if close_exc is not None:
                    try:
                        browser.process.kill()  # type: ignore[attr-defined]
                    except Exception:
                        pass

    def _find_price_in_html(self, html: str) -> Optional[float]:
        """Extract the current price from WB page HTML."""
        soup = BeautifulSoup(html, "html.parser")

        # JSON state embedded in the page
        m = re.search(r'"salePriceU":\s*(\d+)', html) or re.search(
            r'"priceU":\s*(\d+)', html
        )
        if m:
            return int(m.group(1)) / 100

        m = re.search(r'itemprop="price"\s+content="([\d.]+)"', html)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

        for selector in [
            "span.product-page-price__product-price",
            "span.price-block__price",
            "ins.price-block__final-price",
            "span.price__current-price",
            "span.product-page-card__price",
            "span.product-page-price",
        ]:
            elem = soup.select_one(selector)
            if elem:
                price = self._extract_price(elem.get_text(strip=True))
                if price:
                    return price
        return None

    @staticmethod
    def _find_title_in_html(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        elem = soup.find("h1")
        if elem:
            text = elem.get_text(strip=True)
            if text:
                return text
        m = re.search(r"<title>([^<]{5,300})</title>", html)
        if m and m.group(1).strip() not in ("...", ""):
            return m.group(1).strip()
        return None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def parse(self, url: str) -> dict:
        article = self._extract_article(url)
        if not article:
            raise ParseError("Не удалось найти артикул в ссылке Wildberries")

        # Tier 1: fast JSON API with Chrome TLS impersonation
        result = await self._try_card_api(article)
        if result:
            # The card API has no image — enrich it from the basket CDN.
            meta = await self._try_basket_card(article)
            if meta:
                result["image_url"] = meta.get("image_url")
            return result

        # Tier 2: basket CDN gives us reliable metadata (title/image)
        basket_meta = await self._try_basket_card(article)

        # Tier 3: browser with antibot wait — the only way to get the price
        # when the API is blocked.
        try:
            result = await self._try_playwright(article)
        except ParseError as e:
            if basket_meta:
                raise ParseError(
                    f"WB заблокировал запрос цены ({e}). Товар найден: "
                    f"«{basket_meta['title'][:80]}». Попробуй ещё раз через пару минут."
                )
            raise

        # Enrich playwright result with basket metadata if something is missing
        if basket_meta:
            if not result.get("image_url"):
                result["image_url"] = basket_meta.get("image_url")
            if not result.get("title") or result["title"] == "Товар Wildberries":
                result["title"] = basket_meta["title"]
        return result
