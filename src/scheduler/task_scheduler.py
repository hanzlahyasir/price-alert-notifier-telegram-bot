import schedule
import time
import threading
import logging
from datetime import datetime
from src.core.bot import run_all_scrapers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

_run_lock = threading.Lock()

def safe_run():
    if _run_lock.locked():
        logger.warning("Previous run still in progress ⏳ — skipping this interval")
        return

    def _target():
        with _run_lock:
            try:
                logger.info("🔁 Starting scraper job")
                run_all_scrapers()
                logger.info("✅ Scraper job complete")
            except Exception:
                logger.exception("💥 Unhandled exception in scraper job")

    threading.Thread(target=_target, daemon=True).start()

def start_scheduler():
    """
    Run the scraper immediately, then every `interval_minutes`.
    """
    logger.info(f"🚀 First run at {datetime.now()}")
    safe_run()

    schedule.clear()  
    schedule.every().hour.do(safe_run)
    logger.info(f"⏰ Scheduled every hour.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("👋 Scheduler stopped by user")

if __name__ == "__main__":
    start_scheduler()
