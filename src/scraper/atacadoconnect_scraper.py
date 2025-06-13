import re
import warnings
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi import requests as cureq
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import easyocr

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BASE_URL = 'https://www.atacadoconnect.com/'
HEADERS = {
    'accept': 'application/xml, text/xml, */*; q=0.01',
    'accept-language': 'en-PK,en-US;q=0.9,en;q=0.8',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'faces-request': 'partial/ajax',
    'origin': BASE_URL.rstrip('/'),
    'referer': BASE_URL,
    'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
}
# initialize EasyOCR reader once
reader = easyocr.Reader(['en', 'pt'], gpu=False)

# Thread pool for OCR tasks
ocr_executor = ThreadPoolExecutor(max_workers=8)


def price_from_image(src: str) -> str:
    """
    Download image and OCR price in US format.
    """
    byts = cureq.get(src, impersonate='chrome').content
    ocr_results = reader.readtext(byts)
    for _, text, _ in ocr_results:
        t = text.replace(' ', '')
        if t.count(',') == 1 and '.' not in t:
            t = t.replace(',', '.')
        else:
            t = t.replace(',', '')
        m = re.search(r'\d+(\.\d+)?', t)
        if m:
            return f"{float(m.group()):,.2f}"
    return "N/A"


def scrape_one_page(products):
    """
    Scrape product info from list of product divs using threaded OCR.
    """
    results = []
    futures = {}
    # Submit OCR tasks for each product image
    for product in products:
        img = product.find('img', class_='img-moeda-dolar')
        if img and img.get('src'):
            src = urljoin(BASE_URL, img['src'])
            futures[ocr_executor.submit(price_from_image, src)] = product
        else:
            # no price image
            code = product.find('label', class_='cod-prod-card').text.strip()
            name = product.find('label', class_='prod-nome-card').text.strip()
            url = urljoin(BASE_URL, product.find('a').get('href'))
            results.append({
                'code': code,
                'name': name,
                'stock_status': 'In Stock',
                'price': 'N/A',
                'url': url
            })
    # Collect OCR results
    for fut in as_completed(futures):
        prod = futures[fut]
        price = fut.result()
        code = prod.find('label', class_='cod-prod-card').text.strip()
        name = prod.find('label', class_='prod-nome-card').text.strip()
        url = urljoin(BASE_URL, prod.find('a').get('href'))
        results.append({
            'code': code,
            'name': name,
            'stock_status': 'In Stock',
            'price': price,
            'url': url
        })
    return results


def get_next_page_products(url, first: int, view_state: str, cookies):
    data = [
        ('javax.faces.partial.ajax', 'true'),
        ('javax.faces.source', 'dtvListaProdutos'),
        ('javax.faces.partial.execute', 'dtvListaProdutos'),
        ('javax.faces.partial.render', 'dtvListaProdutos'),
        ('javax.faces.behavior.event', 'page'),
        ('javax.faces.partial.event', 'page'),
        ('dtvListaProdutos_pagination', 'true'),
        ('dtvListaProdutos_first', str(first)),
        ('dtvListaProdutos_rows', '60'),
        ('dtvListaProdutos_rppDD', '60'),
        ('javax.faces.ViewState', view_state),
    ]
    resp = cureq.post(
        url,
        cookies=cookies,
        headers=HEADERS,
        data=data,
        impersonate='chrome'
    )
    soup = BeautifulSoup(resp.content, 'lxml')
    return soup.find_all('div', id='componentePai'), soup


def scrape_one_category(url: str) -> list:
    """
    Scrape all product pages from a main category URL.
    """
    sess = cureq.Session()
    resp = sess.get(url, impersonate='chrome')
    soup = BeautifulSoup(resp.content, 'lxml')
    view_state = soup.find('input', {'name': 'javax.faces.ViewState'})['value']
    cookies = sess.cookies

    products, soup = soup.find_all('div', id='componentePai'), soup
    results = []
    total = 0
    # loop through pages
    while products:
        page_results = scrape_one_page(products)
        # break if duplicate last code
        if results and page_results and results[-1]['code'] == page_results[-1]['code']:
            break
        results.extend(page_results)
        total += len(products)
        products, soup = get_next_page_products(url, total, view_state, cookies)
        view_state = soup.find('input', {'name': 'javax.faces.ViewState'})['value']

    # dedupe
    unique = {p['code']: p for p in results}
    print(f"Scraped {len(unique)} products from {url}")
    return list(unique.values())


def get_category_urls() -> list:
    resp = cureq.get(BASE_URL, impersonate='chrome')
    soup = BeautifulSoup(resp.content, 'lxml')
    links = [
        urljoin(BASE_URL, a['href'])
        for a in soup.select('ul.ui-helper-reset a')
        if a.string == 'Exibir Tudo' and re.search(r'/\d+$', a['href'])
    ]
    print(f"Discovered {len(links)} categories.")
    return links


def main():
    category_urls = get_category_urls()
    all_results = []
    # Parallelize categories
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(scrape_one_category, url): url for url in category_urls}
        for fut in as_completed(futures):
            all_results.extend(fut.result())
    print(f"TOTAL scraped products: {len(all_results)}")
    return all_results


if __name__ == '__main__':
    main()
