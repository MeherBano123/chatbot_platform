import os
import json
from groq import Groq
from database.models import DatabaseManager


class GroqFAQGenerator:
    """
    Generate FAQs from scraped page content using Groq LLMs
    and store them in the database.
    """

    def __init__(self, model="llama-3.1-8b-instant"):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = model
        self.db = DatabaseManager()

    # --------------------------------------------------

    def generate_faqs_for_website(self, website_id, faqs_per_page=3):
        pages = self.db.fetch_document_pages_by_website_id(website_id)

        total_pages = len(pages)
        total_faqs = 0
        errors = []

        print(f"Pages found for website {website_id}: {total_pages}")

        for page in pages:
            try:
                count = self._generate_faqs_for_page(
                    website_id,
                    page,
                    faqs_per_page,
                )
                total_faqs += count
            except Exception as e:
                errors.append(f"Page {page['id']} error: {str(e)}")
                print(f"Page error: {e}")

        return {
            "total_pages": total_pages,
            "total_faqs": total_faqs,
            "errors": errors
        }

    # --------------------------------------------------

    def _generate_faqs_for_page(self, website_id, page, faqs_per_page):
        content = page.get("content")
        page_id = page.get("id")

        if not content or len(content.strip()) < 50:
            print(f"Skipping page {page_id} (empty or too short)")
            return 0

        print(f"Generating FAQs for page {page_id}...")

        prompt = self._build_prompt(content, faqs_per_page)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You generate structured FAQs strictly in JSON format."
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        output = response.choices[0].message.content.strip()

        # Try parsing JSON safely
        try:
            faqs = json.loads(output)
        except json.JSONDecodeError:
            print(f"Invalid JSON response for page {page_id}")
            return 0

        created = 0

        for faq in faqs:
            question = faq.get("question", "").strip()
            answer = faq.get("answer", "").strip()

            if len(question) < 10 or len(answer) < 20:
                continue

            # Optional: prevent duplicates
            if self.db.faq_exists(website_id, question):
                continue

            self.db.store_faq(
                website_id=website_id,
                page_id=page_id,
                question=question,
                answer=answer,
                category="ai_generated",
            )

            created += 1

        print(f"{created} FAQs stored for page {page_id}")

        return created

    # --------------------------------------------------

    def _build_prompt(self, text, count):
        return f"""
From the website content below, generate {count} clear and helpful FAQs.

Rules:
- Use ONLY the provided content
- Be concise and factual
- Avoid marketing language
- Return output STRICTLY in JSON format
- Do NOT include explanations
- Output format:

[
  {{
    "question": "string",
    "answer": "string"
  }}
]

Website content:
{text[:6000]}
"""