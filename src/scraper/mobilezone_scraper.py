import asyncio
import re
import time
from functools import wraps
from urllib.parse import urljoin

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup

browser_args = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--single-process', # This can help, but might be less stable
    '--disable-gpu'
]

BASE_URL = "https://www.mobilezone.com.py/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

MAX_CONCURRENT = 5

def async_with_retries(max_retries=3, backoff_factor=0.5):
    def decorator(fn):
        @wraps(fn)
        async def wrapped(*args, **kwargs):
            delay = backoff_factor
            for attempt in range(1, max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        print(f"{fn.__name__} failed after {max_retries} attempts: {e!r}")
                        raise
                    print(f"  → {fn.__name__} failed (attempt {attempt}/{max_retries}): {e!r}")
                    print(f"    retrying in {delay}s…")
                    await asyncio.sleep(delay)
                    delay *= 2
        return wrapped
    return decorator


@async_with_retries(max_retries=4, backoff_factor=1)
async def get_category_urls(page):
    await page.goto(BASE_URL, timeout=60_000)
    await page.wait_for_load_state("domcontentloaded")
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
    return list(urls)


@async_with_retries(max_retries=4, backoff_factor=1)
async def scrape_one_category(context, url, sem):
    async with sem:
        page = await context.new_page()
        products = []
        next_url = url
        page_num = 1

        while next_url:
            print(f"[Cat] {url} — Page {page_num}")
            try:
                await page.goto(next_url, timeout=60_000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3_000)
                await page.wait_for_selector("div.MuiBox-root.css-1yjvs5a", timeout=20_000)
            except PlaywrightTimeoutError as e:
                print(f"  → Timeout loading {next_url}: {e!r}, stopping paging.")
                break

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("div.MuiBox-root.css-1yjvs5a")
            print(f"  → Found {len(cards)} cards")

            for card in cards:
                data = {
                    "url": None,
                    "code": None,
                    "name": None,
                    "price": None,
                    "stock_status": None,
                }

                code_tag = card.select_one("p.MuiTypography-root.css-cueani")
                if code_tag and "Cód:" in code_tag.text:
                    code = code_tag.text.replace("Cód:", "").strip()
                    if code.isdigit():
                        data["code"] = code
                        data["url"] = f"{BASE_URL}product/{code}"

                nm = card.select_one("p.MuiTypography-root.css-5jkaug")
                if nm:
                    data["name"] = nm.text.strip()

                pr = card.select_one("p.MuiTypography-root.css-188qitz")
                if pr:
                    txt = pr.text.replace("U$D", "").replace("$", "").replace(",", "").strip()
                    try:
                        data["price"] = float(txt)
                    except:
                        data["price"] = None

                btn = card.select_one("button.MuiButton-root.css-6kxl0x")
                if btn:
                    classes = btn.get("class", [])
                    data["stock_status"] = "Out of Stock" if "Mui-disabled" in classes else "In Stock"

                if data["code"] and data["name"] and data["url"]:
                    products.append(data)

            next_btn = page.locator(
                'nav[aria-label="pagination navigation"] button[aria-label="Go to next page"]'
            )
            if await next_btn.count() and not await next_btn.is_disabled():
                try:
                    await next_btn.click(timeout=10_000)
                    await page.wait_for_timeout(2_000)
                    next_url = page.url
                    page_num += 1
                except Exception:
                    break
            else:
                break

        await page.close()
        print(f"[Cat] Done {url}: {len(products)} products ")
        return products


async def main():
    start = time.time()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(user_agent=USER_AGENT)

        page = await context.new_page()
        cat_urls = await get_category_urls(page)
        await page.close()

        sem = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [scrape_one_category(context, url, sem) for url in cat_urls]
        # this line here sets categories to be scraped for debugging and time saving purposes
        # will be removed in the final version
        all_results = await asyncio.gather(*tasks, return_exceptions=False)

        await browser.close()

    all_products = [p for sub in all_results for p in sub]
    print(f"Finished in {time.time() - start:.1f}s — scraped {len(all_products)} items total.")
    unique = {}
    for prod in all_products:
        code =  prod.get("code") 
        if code not in unique:
            unique[code] = prod

    deduped_list = list(unique.values())
    print(f"Unique items: {len(deduped_list)}")
    return deduped_list


if __name__ == "__main__":
    asyncio.run(main())
