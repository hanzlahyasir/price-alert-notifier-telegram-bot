import asyncio
import re
import time
from urllib.parse import urljoin

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
    TargetClosedError
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
    '--single-process',  
    '--disable-gpu'
]

MAX_CONCURRENT = 5

async def get_category_urls(playwright, max_retries: int = 4):
    for attempt in range(1, max_retries + 1):
        browser = await playwright.chromium.launch(headless=True, args=browser_args)
        ctx     = await browser.new_context(user_agent=USER_AGENT)
        page    = await ctx.new_page()
        try:
            await page.goto(BASE_URL, timeout=120_000)
            print('page loaded')
            links = await page.locator('xpath=//*[@id="root"]/div[2]/div[2]/div/div/div/div/a').all()
            urls = set()
            for a in links:
                href = await a.get_attribute("href")
                if href and href.startswith("/query/"):
                    urls.add(urljoin(BASE_URL, href))
            print(f"Discovered {len(urls)} categories.")
            return list(urls)
        except PlaywrightError as e:
            print(f"get_category_urls failed (attempt {attempt}/{max_retries}): {e!r}")
            if attempt == max_retries:
                raise
            backoff = 2 ** (attempt - 1)
            print(f"  retrying in {backoff}s…")
            await asyncio.sleep(backoff)
        finally:
            await page.close()
            await ctx.close()
            await browser.close()

async def scrape_one_category(browser, url, sem, max_retries: int = 4):
    async with sem:
        for attempt in range(1, max_retries + 1):
            ctx  = await browser.new_context(user_agent=USER_AGENT)
            page = await ctx.new_page()
            products = []
            page_num = 1
            current_url = url
            try:
                while True:
                    print(f"[Cat] {current_url} — Page {page_num}")
                    try:
                        await page.goto(current_url, timeout=120_000)
                    except PlaywrightError as e:
                        if "net::ERR_ABORTED" in str(e):
                            print(f"  → Ignored ERR_ABORTED on {current_url}")
                        else:
                            raise

                    await page.wait_for_load_state('networkidle')
                    locator = page.locator('xpath=//*[@id="root"]/div[3]/div[1]/div[4]/div[2]/div')
                    blob = await locator.all_text_contents()

                    for card in blob[0].split("Cód:"):
                        text = card.strip()
                        if not text:
                            continue

                        m = re.match(r"^(\d+)", text)
                        code = m.group(1) if m else None

                        m = re.match(r"^\d+(.*)G\$", text)
                        name = m.group(1).strip() if m else None

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

                    next_btn = page.locator('//*[@id="root"]/div[3]/div[1]/nav/ul/li[4]/button')
                    if await next_btn.count() and not await next_btn.is_disabled():
                        await next_btn.click()
                        page_num += 1
                        await page.wait_for_load_state('networkidle')
                        current_url = page.url
                    else:
                        break

                print(f"[Cat] Done {url}: {len(products)} products")
                return products

            except TargetClosedError as e:
                print(f"[Cat] attempt {attempt}/{max_retries} failed: {e!r}")
                if attempt == max_retries:
                    raise
                backoff = 2 ** (attempt - 1)
                print(f"    retrying in {backoff}s…")
                await asyncio.sleep(backoff)

            finally:
                await page.close()
                await ctx.close()

async def main():
    start = time.time()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=browser_args)
        sem     = asyncio.Semaphore(MAX_CONCURRENT)

        cats = await get_category_urls(pw)

        tasks = [
            scrape_one_category(browser, cat_url, sem)
            for cat_url in cats
        ]
        results = await asyncio.gather(*tasks)

        await browser.close()

    all_products = [p for sub in results for p in sub]
    print(f"Finished scraping {len(all_products)} items in {time.time() - start:.1f}s")
    return all_products

if __name__ == "__main__":
    asyncio.run(main())
