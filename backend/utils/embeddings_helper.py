# utils/embedding_helper.py

from sentence_transformers import SentenceTransformer

class EmbeddingHelper:
    def __init__(self, model_name="intfloat/e5-large-v2"):
        self.model = SentenceTransformer(model_name)

    def generate_query_embedding(self, query: str):
        formatted = "query: " + query
        return self.model.encode(formatted).tolist()

    def generate_passage_embedding(self, text: str):
        formatted = "passage: " + text
        return self.model.encode(formatted).tolist()