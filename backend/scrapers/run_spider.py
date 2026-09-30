"""
Spider Runner - Uses multiprocessing to avoid Twisted reactor issues
Triggers embedding generation AFTER scraping completes
"""

from scrapy.crawler import CrawlerProcess
from multiprocessing import Process
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_spider_process(website_id, url, max_pages=50):
    """Run spider in a separate process and trigger embeddings after scraping"""

    from scrapers.scrapy_spider import ScrapySpider
    from database.models import DatabaseManager
    from app import _generate_embeddings_task

    # Scrapy settings
    settings = {
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 4,
        'DOWNLOAD_DELAY': 2,
        'LOG_LEVEL': 'INFO',
        'COOKIES_ENABLED': False,
        'HTTPCACHE_ENABLED': True,
        'USER_AGENT': 'IntelligentChatbotScraper/1.0',
        'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7'
    }

    process = CrawlerProcess(settings)

    process.crawl(
        ScrapySpider,
        website_id=website_id,
        start_url=url,
        max_pages=max_pages
    )

    #  BLOCKS until spider finishes
    process.start()

    print(f" Scraping completed for website_id={website_id}")

    # ------------------------------------------------------------------
    #  START EMBEDDING GENERATION
    # ------------------------------------------------------------------

    try:
        db = DatabaseManager()

        pages = db.fetch_pages_by_website_id(website_id)

        if not pages:
            print(f" No pages scraped for website {website_id}, skipping embeddings")
            return

        print(f" Starting embeddings for {len(pages)} pages")

        embedding_process = Process(
            target=_generate_embeddings_task,
            args=(
                website_id,
                pages,
                800,   # chunk_size
                100    # overlap
            ),
            daemon=False
        )

        embedding_process.start()

        print(f" Embedding process started (PID: {embedding_process.pid})")

    except Exception as e:
        print(f" Failed to start embedding generation: {e}")
        import traceback
        traceback.print_exc()


def run_spider(website_id, url, max_pages=50):
    """Launch spider in a separate process to avoid reactor issues"""

    p = Process(
        target=run_spider_process,
        args=(website_id, url, max_pages),
        daemon=False
    )

    p.start()
    return p


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python run_spider.py <website_id> <url> [max_pages]")
        sys.exit(1)

    website_id = int(sys.argv[1])
    url = sys.argv[2]
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    print(f" Starting spider for website_id={website_id}, url={url}")
    run_spider_process(website_id, url, max_pages)
