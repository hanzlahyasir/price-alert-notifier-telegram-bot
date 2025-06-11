import asyncio
import re
import time
from functools import wraps
from urllib.parse import urljoin

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError
)
from bs4 import BeautifulSoup

browser_args = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--single-process',
    '--disable-gpu'
]

BASE_URL = "https://www.mobilezone.com.py/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

MAX_CONCURRENT = 5

def async_with_retries(max_retries=4, backoff_factor=1):
    def decorator(fn):
        @wraps(fn)
        async def wrapped(*args, **kwargs):
            delay = backoff_factor
            for attempt in range(1, max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except PlaywrightError as e:
                    if attempt == max_retries:
                        print(f"{fn.__name__} failed after {attempt} attempts: {e!r}")
                        raise
                    print(f"  → {fn.__name__} crashed (attempt {attempt}/{max_retries}): {e!r}")
                    print(f"    retrying in {delay}s…")
                    await asyncio.sleep(delay)
                    delay *= 2
        return wrapped
    return decorator

@async_with_retries()
async def get_category_urls(playwright):
    browser = await playwright.chromium.launch(headless=True, args=browser_args)
    ctx     = await browser.new_context(user_agent=USER_AGENT)
    page    = await ctx.new_page()
    await page.goto(BASE_URL, timeout=120_000)
    await page.wait_for_load_state("domcontentloaded")
    # your existing selector logic…
    link_sel = "div.MuiBox-root.css-aqff56 a.css-wl8pcm"
    links = await page.query_selector_all(link_sel)

    if not links:
        toggle = page.locator("div.MuiBox-root.css-1badijy").first
        if await toggle.is_visible(timeout=10_000):
            await toggle.click()
            await page.wait_for_selector(link_sel, timeout=60_000)
            links = await page.query_selector_all(link_sel)

    urls = set()
    for a in links:
        href = await a.get_attribute("href")
        if href and href.startswith("/query/"):
            urls.add(urljoin(BASE_URL, href))

    print(f"Discovered {len(urls)} category URLs.")
    await browser.close()
    return list(urls)

@async_with_retries()
async def scrape_one_category(playwright, url, sem):
    async with sem:
        # brand-new browser & context per category
        browser = await playwright.chromium.launch(headless=True, args=browser_args)
        ctx     = await browser.new_context(user_agent=USER_AGENT)
        page    = await ctx.new_page()

        products = []
        next_url = url
        page_num = 1

        while next_url:
            print(f"[Cat] {url} — Page {page_num}")
            try:
                await page.goto(next_url, timeout=120_000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2_000)
                await page.wait_for_selector("div.MuiBox-root.css-1yjvs5a", timeout=20_000)
            except PlaywrightTimeoutError as e:
                print(f"  → Timeout loading {next_url}: {e!r}, stopping paging.")
                break
            except PlaywrightError as e:
                # any context/page crash triggers a full retry
                raise

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("div.MuiBox-root.css-1yjvs5a")
            print(f"  → Found {len(cards)} cards")

            for card in cards:
                # … your existing extraction logic …
                data = {
                    "url": None,
                    "code": None,
                    "name": None,
                    "price": None,
                    "stock_status": None,
                }
                # populate data as before…
                code_tag = card.select_one("p.MuiTypography-root.css-cueani")
                if code_tag and "Cód:" in code_tag.text:
                    code = code_tag.text.replace("Cód:", "").strip()
                    if code.isdigit():
                        data["code"] = code
                        data["url"]  = f"{BASE_URL}product/{code}"

                nm = card.select_one("p.MuiTypography-root.css-5jkaug")
                if nm:
                    data["name"] = nm.text.strip()

                pr = card.select_one("p.MuiTypography-root.css-188qitz")
                if pr:
                    txt = pr.text.replace("U$D", "").replace("$", "").replace(",", "").strip()
                    try: data["price"] = float(txt)
                    except: data["price"] = None

                btn = card.select_one("button.MuiButton-root.css-6kxl0x")
                if btn:
                    cls = btn.get("class", [])
                    data["stock_status"] = "Out of Stock" if "Mui-disabled" in cls else "In Stock"

                if data["code"] and data["name"]:
                    products.append(data)

            # pagination
            next_btn = page.locator(
                'nav[aria-label="pagination navigation"] button[aria-label="Go to next page"]'
            )
            if await next_btn.count() and not await next_btn.is_disabled():
                try:
                    await next_btn.click(timeout=10_000)
                    await page.wait_for_timeout(2_000)
                    next_url = page.url
                    page_num += 1
                except PlaywrightError:
                    break
            else:
                break

        await browser.close()
        print(f"[Cat] Done {url}: {len(products)} products ")
        return products

async def main():
    start = time.time()
    async with async_playwright() as pw:
        # first fetch all categories with its own retries & teardown
        cat_urls = await get_category_urls(pw)

        sem   = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [
            scrape_one_category(pw, url, sem)
            for url in cat_urls
        ]
        all_results = await asyncio.gather(*tasks)

    # flatten + dedupe
    all_products = [p for sub in all_results for p in sub]
    unique = {p["code"]: p for p in all_products}.values()
    print(f"Finished in {time.time()-start:.1f}s — scraped {len(all_products)} items, {len(unique)} unique.")
    return list(unique)

if __name__ == "__main__":
    asyncio.run(main())
