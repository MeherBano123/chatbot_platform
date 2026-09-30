import os
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
# ==============================
# CONFIG
# ==============================

DB_CONFIG = {
    "dbname": os.getenv("DATABASE"),
    "user": os.getenv("USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("HOST"),
    "port": os.getenv("DB_PORT"),
}

WEBSITE_DATA = {
    "name": "ePay Balochistan",
    "url": "https://epaybalochistan.gov.pk",
    "status": "no"  # can be yes/no/true/false
}

JSON_FILE_PATH = "structured_output_epayBalochistan.json"
SOURCE_NAME = "pdf_upload"

MAX_PAGES = int(os.getenv("MAX_PAGES_PER_WEBSITE", 0))

# Load E5 model once
model = SentenceTransformer("intfloat/e5-large-v2")


# ==============================
# HELPERS
# ==============================

def generate_embed_hash():
    return uuid.uuid4().hex


def generate_embedding(text: str):
    formatted_text = "passage: " + text
    return model.encode(formatted_text).tolist()


def embeddings_exist(cursor, website_id):
    cursor.execute(
        "SELECT 1 FROM epay_embeddings WHERE website_id = %s LIMIT 1",
        (website_id,)
    )
    return cursor.fetchone() is not None


def convert_status_to_bool(status_value):
    if isinstance(status_value, str):
        return status_value.lower() in ['yes', 'true', '1', 'active', 'enabled']
    if isinstance(status_value, bool):
        return status_value
    if isinstance(status_value, int):
        return bool(status_value)
    return True


# ==============================
# MAIN DEPLOY FUNCTION
# ==============================

def register_website_and_embed():

    conn = None

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        print(" Connected to database")

        # Check if website exists
        

        cursor.execute(
            "SELECT id, embed_hash FROM websites WHERE url = %s",
            (WEBSITE_DATA["url"],)
        )

        existing = cursor.fetchone()

        if existing:
            website_id = existing["id"]
            embed_hash = existing["embed_hash"]
            print(f" Website already exists (ID: {website_id})")
        else:
            embed_hash = generate_embed_hash()

            scrape_permission = convert_status_to_bool(
                WEBSITE_DATA.get("status", "yes")
            )

            website_status = "scraping" if scrape_permission else "paused"

            insert_query = """
                INSERT INTO websites
                (name, url, embed_hash, scrape_permission, status, max_pages)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, embed_hash
            """

            cursor.execute(insert_query, (
                WEBSITE_DATA["name"],
                WEBSITE_DATA["url"],
                embed_hash,
                scrape_permission,
                website_status,
                MAX_PAGES
            ))

            website = cursor.fetchone()
            website_id = website["id"]

            print(f" Website registered (ID: {website_id})")

            # Insert scraping queue only if allowed
            if scrape_permission:
                cursor.execute("""
                    INSERT INTO scraping_queue
                    (website_id, status, priority)
                    VALUES (%s, %s, %s)
                """, (website_id, "pending", 0))

                print(" Scraping queue entry created")

        conn.commit()

        #  Insert embeddings
     

        if embeddings_exist(cursor, website_id):
            print(" Embeddings already exist. Skipping embedding import.")
            return

        print(" Starting embedding import...")

        with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:

            heading = item["heading"]
            sub_heading = item["sub_heading"]
            content = item["content"]
            meta_data = item.get("meta_data", "")

            chunk_text = f"{heading}\n{sub_heading}\n{content}"

            embedding_vector = generate_embedding(chunk_text)

            token_count = len(chunk_text.split())

            cursor.execute("""
                INSERT INTO epay_embeddings
                (website_id, heading, sub_heading, chunk_text,
                 embedding, token_count, meta_data, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                website_id,
                heading,
                sub_heading,
                chunk_text,
                embedding_vector,
                token_count,
                meta_data,
                SOURCE_NAME
            ))

        conn.commit()

        print(" All embeddings stored successfully.")
        print(" Deployment initialization complete.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f" Deployment failed: {e}")
        raise

    finally:
        if conn:
            conn.close()
            print(" Database connection closed.")


#  ENTRY POINT


if __name__ == "__main__":
    register_website_and_embed()