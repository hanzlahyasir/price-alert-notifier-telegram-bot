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

# Retry decorator for Playwright functions
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

    # XPath to category container and links
    container_xpath = "xpath=//*[@id='root']/div[2]/div[2]/div/div/div"
    links = page.locator(f"{container_xpath}//a")
    count = await links.count()

    urls = set()
    for i in range(count):
        href = await links.nth(i).get_attribute("href")
        if href and href.startswith("/query/" ):  # ensure valid category link
            urls.add(urljoin(BASE_URL, href))

    print(f"Discovered {len(urls)} category URLs.")
    await browser.close()
    return list(urls)

@async_with_retries()
async def scrape_one_category(playwright, url, sem):
    async with sem:
        browser = await playwright.chromium.launch(headless=True, args=browser_args)
        ctx     = await browser.new_context(user_agent=USER_AGENT)
        page    = await ctx.new_page()

        products = []
        page_num = 1
        next_page = True

        while next_page:
            print(f"[Cat] {url} — Page {page_num}")
            try:
                await page.goto(url if page_num == 1 else page.url, timeout=120_000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2_000)
                # Wait for product cards via XPath
                await page.wait_for_selector("xpath=//*[@id='root']/div[3]/div[1]/div[4]/div[2]/div", timeout=60_000)
            except PlaywrightTimeoutError as e:
                print(f"  → Timeout loading page: {e!r}")
                break
            except PlaywrightError:
                raise

            # Extract product cards
            cards = page.locator("xpath=//*[@id='root']/div[3]/div[1]/div[4]/div[2]/div")
            count = await cards.count()
            print(f"  → Found {count} product cards")

            for i in range(count):
                card = cards.nth(i)
                data = {"code": None, "name": None, "price": None, "stock_status": None, "url": None}

                # Code
                try:
                    code_text = await card.locator("xpath=.//p[contains(text(),'Cód:')]").inner_text()
                    code = code_text.replace("Cód:", "").strip()
                    if code.isdigit():
                        data['code'] = code
                        data['url'] = f"{BASE_URL}product/{code}"
                except:
                    pass

                # Name
                try:
                    name = await card.locator("xpath=.//p[contains(@class,'css-5jkaug')]").inner_text()
                    data['name'] = name.strip()
                except:
                    pass

                # Price in USD
                try:
                    price_text = await card.locator("xpath=.//p[contains(@class,'css-188qitz')]").inner_text()
                    data['price'] = float(re.sub(r"[^\d.]", "", price_text))
                except:
                    pass

                # Stock status
                try:
                    btn_class = await card.locator("xpath=.//button[contains(@class,'css-6kxl0x')]").get_attribute("class")
                    data['stock_status'] = "Out of Stock" if 'Mui-disabled' in btn_class else "In Stock"
                except:
                    pass

                if data['code'] and data['name']:
                    products.append(data)

            # Pagination: next button via XPath
            next_btn = page.locator("xpath=//*[@id='root']/div[3]/div[1]/nav//button[@aria-label='Go to next page']")
            if await next_btn.count() and not await next_btn.is_disabled():
                try:
                    await next_btn.click()
                    await page.wait_for_timeout(2_000)
                    page_num += 1
                except PlaywrightError:
                    next_page = False
            else:
                next_page = False

        await browser.close()
        print(f"[Cat] Done {url}: {len(products)} products")
        return products

async def main():
    start = time.time()
    async with async_playwright() as pw:
        cat_urls = await get_category_urls(pw)

        sem = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [scrape_one_category(pw, url, sem) for url in cat_urls]
        all_results = await asyncio.gather(*tasks)

    all_products = [item for sub in all_results for item in sub]
    unique = {p['code']: p for p in all_products}.values()
    print(f"Finished in {time.time() - start:.1f}s — scraped {len(all_products)} items, {len(unique)} unique.")
    return list(unique)

if __name__ == "__main__":
    asyncio.run(main())
