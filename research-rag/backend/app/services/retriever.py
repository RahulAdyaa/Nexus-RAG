from typing import List, Dict, Tuple
import numpy as np
from .bm25_index import BM25Index
from .embeddings import EmbeddingService
from .reranker import Reranker
from ..database.chroma_store import ChromaStore
from ..utils.config import config

class HybridRetriever:
    def __init__(self, bm25_index_path: str = "./bm25_index.pkl", chroma_db_path: str = None):
        self.bm25_index = BM25Index(bm25_index_path)
        self.chroma_store = ChromaStore(chroma_db_path)
        self.embedding_service = EmbeddingService()
        self.reranker = Reranker()
        
        # Load existing indices
        self.bm25_index.load_index()
    
    def add_documents(self, chunks: List[Dict]):
        """Add documents to both BM25 and Chroma indices"""
        if not chunks:
            return
        
        # Add to BM25 index
        self.bm25_index.add_chunks(chunks)
        
        # Generate embeddings and add to Chroma
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embedding_service.generate_embeddings(texts)
        self.chroma_store.add_chunks(chunks, embeddings)
    
    def build_indices(self, chunks: List[Dict]):
        """Build both BM25 and Chroma indices from scratch"""
        if not chunks:
            return
        
        # Build BM25 index
        self.bm25_index.build_index(chunks)
        
        # Reset and build Chroma collection
        self.chroma_store.reset_collection()
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embedding_service.generate_embeddings(texts)
        self.chroma_store.add_chunks(chunks, embeddings)
    
    def hybrid_search(self, query: str, top_k: int = 5, bm25_weight: float = 0.5, embedding_weight: float = 0.5, filter_criteria: Dict = None, expanded_queries: List[str] = None) -> List[Dict]:
        """
        Perform hybrid search combining BM25 and embedding similarity,
        followed by cross-encoder reranking for maximum precision.
        Supports query expansion by accepting multiple queries.
        
        Args:
            query: Search query
            top_k: Number of results to return
            bm25_weight: Weight for BM25 scores (0-1)
            embedding_weight: Weight for embedding scores (0-1)
            filter_criteria: Optional filter criteria for search
            expanded_queries: Optional alternative queries to also search for
        
        Returns:
            List of ranked results with combined scores
        """
        # Fetch more candidates than needed for reranking
        candidate_count = top_k * 3
        
        all_queries = [query]
        if expanded_queries:
            all_queries.extend(expanded_queries)
            
        all_bm25_results = []
        all_embedding_results = []
        
        for q in all_queries:
            # Get BM25 results
            bm25_res = self.bm25_index.search(q, top_k=candidate_count, filter_criteria=filter_criteria)
            all_bm25_results.extend(bm25_res)
            
            # Get embedding results
            query_emb = self.embedding_service.generate_query_embedding(q)
            emb_res = self.chroma_store.search(q, top_k=candidate_count, query_embedding=query_emb, filter_criteria=filter_criteria)
            all_embedding_results.extend(emb_res)
            
        # Combine and score results (it naturally handles deduplication)
        combined_results = self._combine_results(all_bm25_results, all_embedding_results, bm25_weight, embedding_weight)
        
        # Take top candidates for reranking (limit to 2x top_k to control latency)
        candidates_for_reranking = combined_results[:top_k * 2]
        
        # Cross-encoder reranking for final precision
        if candidates_for_reranking:
            reranked = self.reranker.rerank(query, candidates_for_reranking, top_k=top_k)
            return reranked
        
        return combined_results[:top_k]
    
    def _combine_results(self, bm25_results: List[Tuple[Dict, float]], 
                        embedding_results: List[Tuple[Dict, float]], 
                        bm25_weight: float, embedding_weight: float) -> List[Dict]:
        """Combine and rank results from BM25 and embedding search"""
        
        # Normalize scores
        bm25_scores = self._normalize_scores([score for _, score in bm25_results])
        embedding_scores = self._normalize_scores([score for _, score in embedding_results])
        
        # Create a dictionary to store combined scores
        result_scores = {}
        
        # Add BM25 results
        for i, (result, _) in enumerate(bm25_results):
            chunk_id = result["metadata"]["chunk_id"]
            result_scores[chunk_id] = {
                "result": result,
                "bm25_score": bm25_scores[i] if i < len(bm25_scores) else 0.0,
                "embedding_score": 0.0
            }
        
        # Add embedding results
        for i, (result, _) in enumerate(embedding_results):
            chunk_id = result["metadata"]["chunk_id"]
            if chunk_id in result_scores:
                result_scores[chunk_id]["embedding_score"] = embedding_scores[i] if i < len(embedding_scores) else 0.0
            else:
                result_scores[chunk_id] = {
                    "result": result,
                    "bm25_score": 0.0,
                    "embedding_score": embedding_scores[i] if i < len(embedding_scores) else 0.0
                }
        
        # Calculate combined scores
        final_results = []
        for chunk_id, data in result_scores.items():
            combined_score = (bm25_weight * data["bm25_score"]) + (embedding_weight * data["embedding_score"])
            
            result = data["result"].copy()
            result["combined_score"] = combined_score
            result["bm25_score"] = data["bm25_score"]
            result["embedding_score"] = data["embedding_score"]
            
            final_results.append(result)
        
        # Sort by combined score
        final_results.sort(key=lambda x: x["combined_score"], reverse=True)
        
        return final_results
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores to 0-1 range"""
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(score - min_score) / (max_score - min_score) for score in scores]
    
    def search_by_source(self, source_file: str, page_number: int = None) -> List[Dict]:
        """Search for chunks from a specific source file and optionally page"""
        return self.chroma_store.get_chunk_by_metadata(source_file, page_number)
    
    def get_collection_stats(self) -> Dict:
        """Get statistics about the collections"""
        return {
            "chroma_count": self.chroma_store.get_collection_count(),
            "bm25_count": len(self.bm25_index.chunk_metadata) if self.bm25_index.chunk_metadata else 0
        }
    
    def clear_indices(self):
        """Clear both indices"""
        self.chroma_store.reset_collection()
        self.bm25_index = BM25Index()  # Reset BM25 index

    def delete_document(self, source_file: str):
        """Delete a document from both indices"""
        self.chroma_store.delete_by_source_file(source_file)
        self.bm25_index.delete_by_source_file(source_file)
