from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict
from ..utils.config import config

class EmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer(config.EMBEDDING_MODEL)
        # BGE models benefit from a query instruction prefix for retrieval
        self._is_bge = "bge" in config.EMBEDDING_MODEL.lower()
        self._query_prefix = "Represent this sentence for searching relevant passages: " if self._is_bge else ""
        
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for document passages (no prefix needed)"""
        embeddings = self.model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
        return embeddings
    
    def generate_single_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text (document passage, no prefix)"""
        embedding = self.model.encode([text], normalize_embeddings=True)
        return embedding[0]
    
    def generate_query_embedding(self, query: str) -> np.ndarray:
        """Generate embedding for a search query (with BGE prefix if applicable)"""
        query_text = self._query_prefix + query if self._query_prefix else query
        embedding = self.model.encode([query_text], normalize_embeddings=True)
        return embedding[0]
    
    def process_chunks_to_embeddings(self, chunks: List[Dict]) -> tuple:
        """
        Process chunks and return embeddings with metadata
        Returns: (embeddings_array, chunk_data_list)
        """
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.generate_embeddings(texts)
        
        # Prepare chunk data with embeddings
        chunk_data = []
        for i, chunk in enumerate(chunks):
            chunk_data.append({
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "embedding": embeddings[i]
            })
        
        return embeddings, chunk_data
