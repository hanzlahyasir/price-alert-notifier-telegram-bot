from curl_cffi import requests as cureq
from curl_cffi import Session
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
import urllib.parse
from slugify import slugify
import random
import time

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CHROME_PROFILES = ["chrome", "chrome110", "chrome120"]
BASE_URL = "https://www.atacadoconnect.com/"
VIEWSTATE = "-744970836134698848:-5915530980751057657"


def with_retries(max_retries=3, backoff=1.0):
    def deco(f):
        def wrapper(*args, **kwargs):
            delay = backoff
            for i in range(max_retries):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if i < max_retries - 1:
                        print(f"↻ {f.__name__} failed ({e}), retrying in {delay:.1f}s…")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        print(f"✗ {f.__name__} failed after {max_retries} attempts: {e}")
                        raise
        return wrapper
    return deco


@with_retries(max_retries=4, backoff=1)
def get_product_links_from_list():
    profile = random.choice(CHROME_PROFILES)
    payload = [
        ("javax.faces.partial.ajax", "true"),
        ("javax.faces.source", "dtProdutosListaPreco"),
        ("javax.faces.partial.execute", "dtProdutosListaPreco"),
        ("javax.faces.partial.render", "dtProdutosListaPreco"),
        ("dtProdutosListaPreco", "dtProdutosListaPreco"),
        ("dtProdutosListaPreco_pagination", "true"),
        ("dtProdutosListaPreco_first", "0"),
        ("dtProdutosListaPreco_rows", "*"),
        ("dtProdutosListaPreco_skipChildren", "true"),
        ("dtProdutosListaPreco_encodeFeature", "true"),
        ("dtProdutosListaPreco_reflowDD", "dtProdutosListaPreco:j_idt168_0"),
        ("dtProdutosListaPreco_rppDD", "*"),
        ("dtProdutosListaPreco:j_idt166:filter", ""),
        ("dtProdutosListaPreco:j_idt168:filter", ""),
        ("dtProdutosListaPreco:j_idt171_input", ""),
        ("dtProdutosListaPreco:j_idt176_input", ""),
        ("dtProdutosListaPreco_rppDD", "*"),
        ("javax.faces.ViewState", VIEWSTATE),
    ]
    url = urllib.parse.urljoin(BASE_URL, "lista-preco")
    print(f"→ Listing page via impersonate={profile}")
    resp = cureq.post(
        url,
        data=urllib.parse.urlencode(payload, doseq=True).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Faces-Request": "partial/ajax",
            "Referer": BASE_URL
        },
        impersonate=profile,
        timeout=30000,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    rows = soup.find_all("tr", attrs={"data-ri": True})

    links = []
    for row in rows:
        code_span = row.find("span", class_="cod-prod-lista-desejo")
        names = row.find_all("span", class_="nome-prod-lista-desejo")
        if not code_span or len(names) < 2:
            continue
        code = code_span.get_text(strip=True)
        raw_name = names[0].get_text(strip=True)
        raw_cat = names[1].get_text(strip=True)
        slug_name = slugify(raw_name)
        slug_cat = slugify(raw_cat)
        links.append(urllib.parse.urljoin(
            BASE_URL, f"produto/{slug_cat}/{slug_name}/{code}"
        ))
    print(f"{len(links)} product URLs found")
    return links


@with_retries(max_retries=4, backoff=1)
def scrape_individual_product_page(url, session):
    # Random human-like delay
    time.sleep(random.uniform(1.0, 3.0))
    # Clear cookies to force fresh handshake (optional)
    session.cookies.clear()

    print(f"  • Fetching {url}")
    resp = session.get(
        url,
        impersonate=random.choice(CHROME_PROFILES),
        headers={"Referer": BASE_URL},
        timeout=30000,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml")
    # Price parsing
    pd = soup.find("label", id="j_idt461")
    if pd:
        raw = pd.get_text(strip=True).replace("U$\xa0", "").replace(".", "").replace(",", ".")
    try:
        price = float(raw)
        stock = "In Stock"
    except:
        price, stock = None, "Out of Stock"

    # Code & name
    cl = soup.find("label", id="j_idt171")
    nl = soup.find("label", id="j_idt173")
    if not cl or not nl:
        return {}

    return {
        "url": url,
        "code": cl.get_text(strip=True),
        "name": nl.get_text(strip=True),
        "price": price,
        "stock_status": stock,
    }


def scrape_all_products(links):
    results = []
    # Single Session for the whole run
    with Session() as session:
        session.headers.update({"Referer": BASE_URL})
        for url in links:
            try:
                data = scrape_individual_product_page(url, session)
                print(data)
                if data:
                    results.append(data)
            except Exception as e:
                print(f"Error on {url}: {e}")

    print(f"Total products scraped: {len(results)}")
    # Dedupe by code
    unique = {}
    for prod in results:
        code = prod.get("code")
        if code and code not in unique:
            unique[code] = prod

    deduped_list = list(unique.values())
    print(f"Unique items: {len(deduped_list)}")
    return deduped_list


def main():
    start = time.time()
    links = get_product_links_from_list()
    products = scrape_all_products(links)
    print(f"Scraped {len(products)} products in {time.time() - start:.1f}s")
    return products


if __name__ == '__main__':
    main()
