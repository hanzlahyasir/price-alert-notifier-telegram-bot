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

BASE_URL = "https://www.mobilezone.com.py/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

browser_args = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--single-process',  # Railway-friendly
    '--disable-gpu'
]

MAX_CONCURRENT = 5

def async_with_retries(max_retries=4, backoff_factor=1):
    """Decorator to retry Playwright errors (except we swallow ERR_ABORTED on goto)."""
    def decorator(fn):
        @wraps(fn)
        async def wrapped(*args, **kwargs):
            delay = backoff_factor
            for attempt in range(1, max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except PlaywrightError as e:
                    msg = str(e)
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
    """Grab all category links from the main page."""
    browser = await playwright.chromium.launch(headless=True, args=browser_args)
    ctx     = await browser.new_context(user_agent=USER_AGENT)
    page    = await ctx.new_page()

    await page.goto(BASE_URL, timeout=120_000)
    print('page loaded')
    links = await page.locator('xpath=//*[@id="root"]/div[2]/div[2]/div/div/div/div/a').all()
    print(len(links))
    urls = set()
    for a in links:
        href = await a.get_attribute("href")
        if href and href.startswith("/query/"):
            urls.add(urljoin(BASE_URL, href))

    print(f"Discovered {len(urls)} categories.")
    await browser.close()
    return list(urls)

@async_with_retries()
async def scrape_one_category(playwright, url, sem):
    """Scrape every page of one category, return a list of product dicts."""
    async with sem:
        browser = await playwright.chromium.launch(headless=True, args=browser_args)
        ctx     = await browser.new_context(user_agent=USER_AGENT)
        page    = await ctx.new_page()

        products = []
        page_num = 1

        while True:
            print(f"[Cat] {url} — Page {page_num}")
            # navigate, swallow ERR_ABORTED if it happens
            try:
                await ctx.clear_cookies()
                await page.goto(url, timeout=120_000)
            except PlaywrightError as e:
                if "net::ERR_ABORTED" in str(e):
                    print(f"  → Ignored ERR_ABORTED on {url}")
                else:
                    raise
            await page.wait_for_timeout(2_000)

            # wait for the card containers
            # await page.wait_for_selector(
            #     'xpath=//*[@id="root"]/div[3]/div[1]/div[4]/div[2]/div',
            #     timeout=120_000
            # )

            # grab all card text blobs
            locator = page.locator(
                'xpath=//*[@id="root"]/div[3]/div[1]/div[4]/div[2]/div'
            )
            blob = await locator.all_text_contents()

            
            for card in blob[0].split("Cód:"):
                text = card.strip()
                if not text:
                    continue

                # parse code
                m = re.match(r"^(\d+)", text)
                code = m.group(1) if m else None

                # parse name (up to G$)
                m = re.match(r"^\d+(.*)G\$", text)
                name = m.group(1).strip() if m else None

                # USD price is last $…
                prices = re.findall(r"\$ ([\d.,]+)", text)
                price = float(prices[-1].replace(",", "")) if prices else None

                if code and name:
                    products.append({
                        "code": code,
                        "name": name,
                        "price": price,
                        "stock_status": "In Stock",
                        "url": urljoin(BASE_URL, f"product/{code}")
                    })

            # pagination next
            next_btn = page.locator(
                '//*[@id="root"]/div[3]/div[1]/nav/ul/li[4]/button'
            )
            # //*[@id="root"]/div[3]/div[1]/nav/ul/li[4]/button
            if await next_btn.count() and not await next_btn.is_disabled():
                await next_btn.click()
                page_num += 1
                await page.wait_for_timeout(2_000)
                # subsequent loops will use page.url automatically
                url = page.url
            else:
                break

        await browser.close()
        print(f"[Cat] Done {url}: {len(products)} products")
        return products

async def main():
    start = time.time()
    async with async_playwright() as pw:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        # 1) fetch categories
        cats = await get_category_urls(pw)

        # 2) schedule each category scrape with its own context
        tasks = [
            scrape_one_category(pw, cat_url, sem)
            for cat_url in cats
        ]
        # waits for all to finish
        results = await asyncio.gather(*tasks)

    # flatten
    all_products = [p for sub in results for p in sub]
    print(f"Finished scraping {len(all_products)} items in {time.time() - start:.1f}s")
    return all_products

if __name__ == "__main__":
    asyncio.run(main())
