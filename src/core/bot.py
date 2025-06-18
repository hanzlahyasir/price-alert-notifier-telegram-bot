import asyncio
import logging
import re
import time
from datetime import datetime
import os

from src.common import load_config
from src.alerter import send_telegram_message_sync #, email_sender
from src.scraper.mobilezone_scraper import main as scrape_mobilezone_playwright
from src.scraper.megaeletronicos_scraper import main as scrape_megaeletronicos
from src.storage.db_manager import DBManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("core.bot")


async def scrape_with_retry(scraper_fn, max_retries=3, backoff=1.0):
    delay = backoff
    for attempt in range(1, max_retries + 1):
        try:
            result = scraper_fn()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"{scraper_fn.__name__} failed after {attempt} attempts", exc_info=e)
                return []
            else:
                logger.warning(
                    f"{scraper_fn.__name__} failed (attempt {attempt}/{max_retries}), retrying in {delay:.1f}s…"
                )
                await asyncio.sleep(delay)
                delay *= 2


class Alerter:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.t_msgs = []
        self.e_msgs = []

    def queue_price_drop(self, site, name, old, new, url):
        txt = (
            f"📉Price Drop Alert!\n\n"
            f"Product: {name}\n"
            f"Site: {site}\n"
            f"Old Price: ${old:.2f}\n"
            f"New Price: ${new:.2f}\n"
            f"URL: {url}"
        )
        self.t_msgs.append(txt)
        # self.e_msgs.append({
        #     "subject": f"Price Drop: {name}",
        #     "message": (
        #         f"<h1>{name}</h1>"
        #         f"<p>Site: {site}</p>"
        #         f"<p>Old Price: ${old:.2f}</p>"
        #         f"<p>New Price: ${new:.2f}</p>"
        #         f'<a href="{url}">Buy now</a>'
        #     )
        # })
    def queue_price_increase(self, site, name, old, new, url):
        txt = (
            f"📈Price Increase Alert!\n\n"
            f"Product: {name}\n"
            f"Site: {site}\n"
            f"Old Price: ${old:.2f}\n"
            f"New Price: ${new:.2f}\n"
            f"URL: {url}"
        )
        self.t_msgs.append(txt)
        # self.e_msgs.append({
        #     "subject": f"Price Increase: {name}",
        #     "message": (
        #         f"<h1>{name}</h1>"
        #         f"<p>Site: {site}</p>"
        #         f"<p>Old Price: ${old:.2f}</p>"
        #         f"<p>New Price: ${new:.2f}</p>"
        #         f'<a href="{url}">Buy now</a>'
        #     )
        # })

    def queue_back_in_stock(self, site, name, price, url):
        txt = (
            f"📦Back in Stock!\n\n"
            f"Product: {name}\n"
            f"Site: {site}\n"
            f"Price: ${price:.2f}\n"
            f"URL: {url}"
        )
        self.t_msgs.append(txt)
        # self.e_msgs.append({
        #     "subject": f"Back in Stock: {name}",
        #     "message": (
        #         f"<h1>{name}</h1>"
        #         f"<p>Site: {site}</p>"
        #         f"<p>Price: ${price:.2f}</p>"
        #         f'<a href="{url}">Check it out</a>'
        #     )
        # })
    def queue_out_of_stock(self, site, name, price, url):
        txt = (
            f"📦Out of Stock!\n\n"
            f"Product: {name}\n"
            f"Site: {site}\n"
            f"Price: ${price:.2f}\n"
            f"URL: {url}"
        )
        self.t_msgs.append(txt)
        # self.e_msgs.append({
        #     "subject": f"Out of Stock: {name}",
        #     "message": (
        #         f"<h1>{name}</h1>"
        #         f"<p>Site: {site}</p>"
        #         f"<p>Price: ${price:.2f}</p>"
        #         f'<a href="{url}">Check it out</a>'
        #     )
        # })

    def flush(self):
        if self.bot_token and self.chat_id and self.t_msgs:
            logger.info(f"Sending {len(self.t_msgs)} Telegram alerts")
            for m in self.t_msgs:
                send_telegram_message_sync(self.bot_token, self.chat_id, m)
        # if self.e_msgs:
        #     logger.info(f"Sending {len(self.e_msgs)} email alerts")
        #     for e in self.e_msgs:
        #         email_sender(e["subject"], e["message"])


def process_scraped_data(db: DBManager, site: str, items: list, alerter: Alerter):
    if not items:
        logger.info(f"No data from {site}")
        return

    logger.info(f"Processing {len(items)} items from {site}")
    for p in items:
        code  = p.get("code")
        if not code:
            continue

        stored = db.get_product(site, code)
        price  = p.get("price")
        stock  = p.get("stock_status")
        name   = p.get("name", "Unknown")
        url    = p.get("url", "#")

        if not isinstance(price, (int, float)):
            try:
                price = float(re.sub(r"[^\d.]", "", str(price)))
            except:
                price = None


        old_stock = stored.get("last_stock_status") if stored else None
        old_stock_str = str(old_stock).lower() if old_stock is not None else None
        new_stock_str = str(stock).lower() if stock is not None else ""
        in_stock = lambda s: "in stock" in s
        out_stock = lambda s: "out of stock" in s or "out stock" in s

        if stored:
            if out_stock(old_stock_str or "") and in_stock(new_stock_str):
                alerter.queue_back_in_stock(site, name, price or 0.0, url)

            elif in_stock(old_stock_str or "") and out_stock(new_stock_str):
                alerter.queue_out_of_stock(site, name, price or 0.0, url)
            else:
                if price is not None and in_stock(new_stock_str) and in_stock(old_stock_str or ""):
                    old_price = stored.get("last_price_usd")
                    if old_price is not None:
                        if price < old_price:
                            alerter.queue_price_drop(site, name, old_price, price, url)
                        elif price > old_price:
                            alerter.queue_price_increase(site, name, old_price, price, url)
        else:
            logger.info(f"New product: {name} (${price}) on {site}")


        db.add_or_update_product(
            site_name=site,
            product_code=code,
            name=name,
            url=url,
            price_usd=price if price is not None else stored.get("last_price_usd", 0.0),
            stock_status=new_stock_str,
        )


async def run_all_scrapers_async(db: DBManager, alerter: Alerter):

    scrapers = {
        "mobilezone":       scrape_mobilezone_playwright,
        "megaeletronicos":  scrape_megaeletronicos,
    }

    tasks = {
        site: asyncio.create_task(scrape_with_retry(fn))
        for site, fn in scrapers.items()
    }


    for site, task in tasks.items():
        items = await task
        process_scraped_data(db, site, items, alerter)

def run_all_scrapers():
    logger.info("=== Starting scraping run ===")
    config    = load_config()
    bot_token = os.getenv("BOT_TOKEN") or config.get("TELEGRAM", "BOT_TOKEN", fallback=None)
    chat_id   = os.getenv("CHAT_ID") or config.get("TELEGRAM", "CHAT_ID",   fallback=None)
    alerter   = Alerter(bot_token, chat_id)

    with DBManager() as db:
        db.initialize_database()
        asyncio.run(run_all_scrapers_async(db, alerter))

    alerter.flush()
    logger.info("=== Scraping run complete ===")

if __name__ == "__main__":
    run_all_scrapers()
