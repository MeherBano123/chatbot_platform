# rag_query_engine.py

import time
import os 
from dotenv import load_dotenv
from openai import OpenAI
from utils.embeddings_helper import EmbeddingHelper
from database.models import DatabaseManager
from utils.context_builder import build_context


load_dotenv()


class RAGQueryEngine:

    def __init__(self,
                 embedding_model="intfloat/e5-large-v2",
                 ollama_model=os.getenv("ollama_model", "llama3"),
                 ollama_base_url="http://localhost:11434/v1"):

        self.embedder = EmbeddingHelper(embedding_model)
        self.db = DatabaseManager()

        self.client = OpenAI(
            api_key="ollama",
            base_url=ollama_base_url
        )

        self.model = ollama_model

    # =========================
    # Main Query Method
    # =========================
    def query(self, user_query, website_id=None, top_k=5):

        start_time = time.time()

        # Generate query embedding
        query_embedding = self.embedder.generate_query_embedding(user_query)

        #  Search similar documents
        search_results = self.db.search_similar_embeddings_epay(
            query_embedding=query_embedding,
            website_id=website_id
        )
        print(f"Found {len(search_results)} similar documents")

        if not search_results:
            return {
                "query": user_query,
                "response": "I don't have enough information to answer that.",
                "sources": [],
                "status": "no_results"
            }

        #  Build context (with metadata)
        context = build_context(search_results)

        #  Generate LLM response
        print("generating response with context length:", len(context))
        response = self.generate_llm_response(user_query, context)

        return {
            "query": user_query,
            "response": response,
            "sources": search_results,
            "num_sources": len(search_results),
            "time_taken": round(time.time() - start_time, 2),
            "status": "success"
        }

    # =========================
    # LLM Generation
    # =========================
    def generate_llm_response(self, query, context):

        system_prompt = """
You are a helpful domain-specific assistant.
Use ONLY the provided context to answer the question.

The metadata field contains important keywords describing the content.
Use it to better understand relevance.

If the answer is not present in context, say:
"I don't have enough information to answer that."
Do not hallucinate.
Be concise and informative. Do not mention the sources in the answer, but use them to inform your response.Do not mention conetxt in the response.
Answer in human-like language, like a helpful assistant would. Do not sound like an AI model.
If web or mobile app development is mentioned in the context, you can assume the user is asking about epay balochistan's web or mobile app services.
If neither web nor mobile app development is mentioned, you can assume the user is asking about epay balochistan's web services.
"""

        user_prompt = f"""
Context:
{context}

Question:
{query}

Answer:
"""

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=500,
                stream=False
            )

            return completion.choices[0].message.content.strip()

        except Exception as e:
            return f"Error generating response: {e}"