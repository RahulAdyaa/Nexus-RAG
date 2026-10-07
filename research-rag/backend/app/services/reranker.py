from sentence_transformers import CrossEncoder
from typing import List, Dict
from ..utils.config import config


class Reranker:
    """
    Cross-encoder reranker for improving retrieval precision.
    
    Unlike bi-encoders (which encode query and document separately),
    cross-encoders jointly encode the query-document pair, producing
    much more accurate relevance scores at the cost of higher latency.
    
    Typical improvement: 15-30% precision boost over raw BM25+embedding scores.
    """
    
    def __init__(self):
        self.model = CrossEncoder(
            config.RERANKER_MODEL,
            max_length=512  # Limit input length for speed
        )
        print(f"[Reranker] Loaded cross-encoder: {config.RERANKER_MODEL}")
    
    def rerank(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Rerank retrieved chunks using a cross-encoder model.
        
        Args:
            query: The user's search query
            chunks: List of candidate chunks from hybrid search (with text + metadata)
            top_k: Number of top results to return after reranking
            
        Returns:
            Reranked list of chunks with updated scores
        """
        if not chunks:
            return []
        
        # Prepare query-document pairs for cross-encoder
        pairs = [(query, chunk.get("text", "")) for chunk in chunks]
        
        # Get cross-encoder scores (higher = more relevant)
        scores = self.model.predict(pairs)
        
        import math
        
        # Attach reranker scores and sort
        reranked = []
        for i, chunk in enumerate(chunks):
            result = chunk.copy()
            
            # The cross encoder prediction is already a probability in [0, 1]
            raw_score = float(scores[i])
            
            result["reranker_score"] = raw_score
            # Keep original scores for transparency
            result["original_combined_score"] = chunk.get("combined_score", 0.0)
            # Use reranker score as the primary ranking signal
            result["combined_score"] = raw_score
            reranked.append(result)
        
        # Sort by reranker score (descending)
        reranked.sort(key=lambda x: x["reranker_score"], reverse=True)
        
        return reranked[:top_k]
