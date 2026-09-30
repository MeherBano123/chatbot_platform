import os
import json
from flask import Flask, request, jsonify
from groq import Groq
from database.models import DatabaseManager

app = Flask(__name__)

class GroqFAQGenerator:
    def __init__(self, model="llama-3.1-8b-instant"):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = model
        self.db = DatabaseManager()

    def generate_faqs_from_data(self, modules_data, website_id):
        """Processes the list of modules provided directly from the uploaded file."""
        total_faqs = 0
        errors = []

        for module in modules_data:
            try:
                content = module.get("content", "")
                heading = module.get("heading", "General")

                if not content or len(content.strip()) < 50:
                    continue

                # Generate FAQs via LLM
                faqs = self._get_llm_response(content)

                for faq in faqs:
                    question = faq.get("question", "").strip()
                    answer = faq.get("answer", "").strip()

                    if len(question) < 10 or len(answer) < 10:
                        continue

                    # Store using your specific function signature
                    self.db.store_faq(
                        website_id=website_id,
                        question=question,
                        answer=answer,
                        category=heading,
                        priority=0,
                        
                    )
                    total_faqs += 1

            except Exception as e:
                errors.append(f"Error in module {module.get('heading')}: {str(e)}")

        return {
            "total_modules_processed": len(modules_data),
            "total_faqs_created": total_faqs,
            "errors": errors
        }

    def _get_llm_response(self, text):
        prompt = f"""
        From the content below, generate 2 helpful FAQs.
        Format: [{{"question": "...", "answer": "..."}}]
        Content: {text[:4000]}
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You output strictly JSON lists."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        # Extract list if LLM wraps it in a key
        return data if isinstance(data, list) else list(data.values())[0]

