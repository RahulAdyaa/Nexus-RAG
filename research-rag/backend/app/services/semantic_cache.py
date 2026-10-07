import os
import uuid
import json
import chromadb
from chromadb.config import Settings
import numpy as np
from typing import Optional, Dict
from app.utils.config import config

class SemanticCache:
    def __init__(self, db_path: str = None, threshold: float = 0.40):
        # We use a threshold of 0.40 L2 distance (approx 0.92 cosine similarity) to allow variations in phrasing
        self.db_path = db_path or os.path.join(config.CHROMA_DB_PATH, "semantic_cache")
        self.collection_name = "semantic_cache"
        self.threshold = threshold
        self.client = None
        self.collection = None
        self._initialize_client()
        
    def _initialize_client(self):
        os.makedirs(self.db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except Exception:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Semantic cache for answered questions"}
            )
            
    def get(self, query_embedding: np.ndarray, scope_key: str) -> Optional[Dict]:
        """Check the cache for a similar question. Returns cached answer data if found."""
        if not self.collection:
            return None
            
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=1,
                include=["metadatas", "distances"],
                where={"scope": {"$eq": scope_key}}
            )
            
            if results["distances"] and results["distances"][0]:
                distance = results["distances"][0][0]
                if distance <= self.threshold:
                    metadata = results["metadatas"][0][0]
                    cache_entry = {
                        "answer": metadata["answer"],
                        "sources": json.loads(metadata.get("sources", "[]")),
                        "context_used": int(metadata.get("context_used", 0)),
                        "distance": distance
                    }
                    if "quality" in metadata:
                        try:
                            cache_entry["quality"] = json.loads(metadata["quality"])
                        except:
                            pass
                    return cache_entry
        except Exception as e:
            print(f"Cache get error: {e}")
        return None
        
    def set(self, query: str, query_embedding: np.ndarray, answer: str, sources: list, context_used: int, scope_key: str, quality: dict = None, judge_model: str = "unknown", threshold_version: str = "1.0"):
        """Store the generated answer in the semantic cache."""
        if not self.collection:
            return
            
        try:
            cache_id = str(uuid.uuid4())
            metadata = {
                "answer": answer,
                "sources": json.dumps(sources),
                "context_used": str(context_used),
                "scope": scope_key,
                "judge_model": judge_model,
                "threshold_version": threshold_version
            }
            if quality is not None:
                metadata["quality"] = json.dumps(quality)
            
            self.collection.add(
                documents=[query],
                embeddings=[query_embedding.tolist()],
                metadatas=[metadata],
                ids=[cache_id]
            )
        except Exception as e:
            print(f"Error saving to cache: {e}")

    def clear(self):
        """Clear all cached entries."""
        try:
            if self.collection:
                self.client.delete_collection(name=self.collection_name)
                self.collection = None
                self._initialize_client()
        except Exception as e:
            print(f"Error clearing cache: {e}")
