import asyncio
import re
import time
import random
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi import requests as cureq
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
)
BASE_URL = "https://www.megaeletronicos.com/"

CONCURRENT_CATEGORIES = 5


def retry(max_retries=3, backoff_base=2, jitter=0.1):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        print(f"[ERROR] {fn.__name__} failed after {max_retries} retries: {e}")
                        if fn.__name__ == "get_category_page_data":
                            return [], True
                        return []
                    sleep_time = backoff_base**attempt + random.uniform(0, jitter)
                    print(f"[Retry {attempt+1}/{max_retries}] {fn.__name__} error: {e}. "
                          f"Sleeping {sleep_time:.1f}s before next try.")
                    time.sleep(sleep_time)
        return wrapper
    return decorator


async def get_categories(page):
    await page.goto(BASE_URL, timeout=60_000)
    menu_toggle = page.locator("button.menu-toggle")
    if await menu_toggle.is_visible():
        await menu_toggle.click()
        print("Menu toggle clicked.")
    else:
        print("Menu toggle not visible.")

    links = []
    cats = page.locator("div.menu-categories a")
    count = await cats.count()
    for i in range(count):
        cat = cats.nth(i)
        await cat.scroll_into_view_if_needed()
        await cat.click()
        sub = page.locator("div.menu-subcategories a")
        await sub.first.wait_for(state="visible", timeout=5_000)
        href = await sub.first.get_attribute("href")
        if href:
            full = urljoin(BASE_URL, href)
            print(f"Discovered category: {full}")
            links.append(full)
    return links


@retry(max_retries=3, backoff_base=2, jitter=0.2)
def get_category_page_data(category_url):
    print(f"Fetching: {category_url}")
    resp = cureq.get(category_url, impersonate="chrome", timeout=30_000)
    soup = BeautifulSoup(resp.content, "html.parser")

    products = []
    for product in soup.find_all("div", class_="producto"):
        if product.find('h4', class_='titulo'):
            parent_a = product.find_parent("a")
            url = parent_a["href"] if parent_a else None

            name_tag = product.find("h4", class_="titulo")
            name = name_tag.get_text(strip=True) if name_tag else None

            code_tag = product.find("p", class_="codigo")
            code = re.search(r"\d+", code_tag.get_text())[0] if code_tag else None

            price = None
            stock_status = None
            price_tag = product.find("p", class_="principal-br")
            if price_tag:
                # txt = price_tag.get_text(strip=True).replace("U$\xa0", "")
                txt = re.sub(r'[^\d.]', "", price_tag.get_text(strip=True))
                price = float(txt) if txt else ''

            stock_in_tag = product.find('span', class_='badge-in-stock')
            stock_out_tag = product.find('span', class_='bg-danger')
            if stock_in_tag:
                stock_status = "In Stock"
            elif stock_out_tag:
                stock_status = "Out of Stock"
            else:
                stock_status = "Out of Stock"

            
            products.append({
                "url": url,
                "code": code,
                "name": name,
                "price": price,
                "stock_status": stock_status,
            })

    pag = soup.select_one("div.paginaciones")
    last = not pag or bool(soup.select_one("div.last.active-search"))
    return products, last


def get_products_from_category(category_url):
    page_num = 1
    all_products = []
    while True:
        page_url = f"{category_url}?page={page_num}"
        prods, last = get_category_page_data(page_url)
        all_products.extend(prods)
        if last:
            break
        page_num += 1
    print(f"{len(all_products)} items from {category_url}")
    return all_products


async def main():
    start = time.time()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=browser_args)
        ctx = await browser.new_context(user_agent=USER_AGENT,
                                        viewport={"width": 1080, "height": 1800})
        page = await ctx.new_page()
        cat_urls = await get_categories(page)
        await browser.close()

    print(f"Found {len(cat_urls)} categories. Spawning {CONCURRENT_CATEGORIES} workers...")

    all_products = []
    with ThreadPoolExecutor(max_workers=CONCURRENT_CATEGORIES) as exe:
        futures = {exe.submit(get_products_from_category, url): url
                   for url in cat_urls}
        #this line here sets the only 2 categories to be scraped for debuggin purposes
        #would be removed in the deployed version
        for fut in as_completed(futures):
            all_products.extend(fut.result())

    print(f"Done! Total products scraped: {len(all_products)}")
    print(f"Total time: {time.time() - start:.1f}s")
    unique = {}
    for prod in all_products:
        code =  prod.get("code") 
        if code not in unique:
            unique[code] = prod

    deduped_list = list(unique.values())
    print(f"Unique items: {len(deduped_list)}")
    print(deduped_list)
    return deduped_list


if __name__ == "__main__":
    asyncio.run(main())
