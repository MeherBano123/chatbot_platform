import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional

import numpy as np
import torch
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()


class StructuralEmbeddingGenerator:
    def __init__(
        self,
        model_name: str = "intfloat/e5-large-v2",
        force_download: bool = False
    ):
        print(f"Loading embedding model: {model_name}")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        if force_download:
            self._clear_model_cache(model_name)

        self.model = SentenceTransformer(
            model_name,
            device=self.device,
            trust_remote_code=True
        )

        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"Embedding dimension: {self.embedding_dim}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_model_cache(self, model_name: str):
        cache_dir = Path.home() / ".cache" / "torch" / "sentence_transformers"
        model_dir = cache_dir / model_name.replace("/", "_")
        if model_dir.exists():
            shutil.rmtree(model_dir)
            print(f"Cleared model cache: {model_dir}")

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def structural_chunk_json(self, modules: List[Dict]) -> List[Dict]:
        """
        Structural chunking:
        Each module (heading + content) becomes ONE chunk.
        No artificial splitting.
        """

        if not modules:
            return []

        chunks = []

        for index, module in enumerate(modules):
            heading = module.get("heading", "").strip()
            content = module.get("content", "").strip()

            if not content:
                continue

            full_text = f"Heading: {heading}\n\n{content}"

            chunks.append({
                "chunk_text": full_text,
                "chunk_index": index,
                "token_count": int(len(full_text.split()) * 0.75),
                "heading": heading
            })

        return chunks

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate a single embedding (E5 requires 'passage:' prefix)
        """
        return self.model.encode(
            f"passage: {text}",
            convert_to_numpy=True,
            normalize_embeddings=True
        )

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 32
    ) -> List[np.ndarray]:
        """
        Generate embeddings for multiple chunks
        """
        if not texts:
            return []

        prefixed = [f"passage: {t}" for t in texts]

        return self.model.encode(
            prefixed,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True
        )

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def extract_tags(self, text: str, title: str = "") -> List[str]:
        combined = f"{title} {text}".lower()

        categories = {
            "pricing": ["price", "pricing", "cost", "plan"],
            "technical": ["api", "code", "developer", "sdk"],
            "support": ["support", "help", "faq"],
            "product": ["product", "feature", "service"],
            "company": ["about", "company", "team"],
            "legal": ["privacy", "terms", "policy"],
            "getting_started": ["getting started", "quickstart"]
        }

        tags = [
            category
            for category, keywords in categories.items()
            if any(k in combined for k in keywords)
        ]

        return tags or ["general"]

    ### processing sof json file to create embeddings for each chunk and return list of dicts ready for DB insertion

    def process_structural_json(
        self,
        *,
        website_id: int,
        modules: List[Dict],
        source: str,
        website_page_id: Optional[int] = None,
        document_id: Optional[int] = None,
        page_id: Optional[int] = None,
        title: str = "",
    ) -> List[Dict]:
        """
        Process structured JSON modules into embeddings.

        EXACTLY ONE of website_page_id OR document_id must be provided.
        """

        if (website_page_id is None and document_id is None) or \
           (website_page_id is not None and document_id is not None):
            raise ValueError("Provide exactly one of website_page_id or document_id")

        chunks = self.structural_chunk_json(modules)

        if not chunks:
            return []

        texts = [c["chunk_text"] for c in chunks]
        embeddings = self.generate_embeddings_batch(texts)

        results = []

        for chunk, vector in zip(chunks, embeddings):
            row = {
                "website_id": website_id,
                "chunk_text": chunk["chunk_text"],
                "chunk_index": chunk["chunk_index"],
                "embedding_vector": vector.tolist(),
                "token_count": chunk["token_count"],
                "tags": self.extract_tags(chunk["chunk_text"], chunk.get("heading", "")),
                "source": source,
                "heading": chunk.get("heading")
            }

            if website_page_id is not None:
                row["website_page_id"] = website_page_id
                row["document_id"] = None
            else:
                row["document_id"] = document_id
                row["page_id"] = page_id

            results.append(row)

        return results
