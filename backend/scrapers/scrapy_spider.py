import scrapy
from urllib.parse import urlparse, urljoin
import hashlib
import os
import sys
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import DatabaseManager


class ScrapySpider(scrapy.Spider):
    name = "intelligent_spider"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS": 4,
        "DOWNLOAD_DELAY": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, website_id, start_url, max_pages=50, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.website_id = int(website_id)
        self.start_urls = [start_url]
        self.max_pages = max_pages
        self.pages_scraped = 0
        self.visited_urls = set()

        parsed = urlparse(start_url)
        self.allowed_domain = parsed.netloc
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"

        self.db = DatabaseManager()

        print(f"""
==================================================
 INTELLIGENT SPIDER (CONTENT ONLY)
==================================================
Start URL   : {start_url}
Website ID : {self.website_id}
Max Pages  : {self.max_pages}
Domain     : {self.allowed_domain}
==================================================
""")

    def parse(self, response):
        if self.pages_scraped >= self.max_pages:
            return

        if response.url in self.visited_urls:
            return

        self.visited_urls.add(response.url)
        self.pages_scraped += 1

        print(f"\n [{self.pages_scraped}/{self.max_pages}] {response.url}")

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove junk
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # Extract content
        content = ""
        if soup.find("main"):
            content = soup.find("main").get_text("\n", strip=True)
        elif soup.find("body"):
            content = soup.find("body").get_text("\n", strip=True)
        else:
            content = soup.get_text("\n", strip=True)

        if not content.strip():
            print("Empty content, skipping DB save")
            return

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        metadata = {
            "content_hash": content_hash,
            "content_length": len(content),
            "scraper_version": "content_only_v1",
        }

        self.db.store_page(
            website_id=self.website_id,
            url=response.url,
            title=soup.title.get_text(strip=True) if soup.title else response.url,
            content=content,
            metadata=metadata,
        )

        print(f" Stored page | Length: {len(content)}")

        # Follow internal links
        for link in response.css("a::attr(href)").getall():
            absolute_url = urljoin(self.base_url, link)
            parsed_link = urlparse(absolute_url)

            if parsed_link.netloc != self.allowed_domain:
                continue

            if absolute_url in self.visited_urls:
                continue

            if any(ext in absolute_url.lower() for ext in [".pdf", ".jpg", ".png", ".zip", ".mp4"]):
                continue

            yield scrapy.Request(absolute_url, callback=self.parse)

    def closed(self, reason):
        status = "active" if self.pages_scraped > 0 else "failed"
        self.db.update_website_status(self.website_id, status)
        self.db.update_scraping_queue(self.website_id, 'completed')

        print(f"""
==================================================
 Spider closed
Reason        : {reason}
Pages scraped : {self.pages_scraped}
Website status: {status}
==================================================
""")
