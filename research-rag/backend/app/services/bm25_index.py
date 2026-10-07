from rank_bm25 import BM25Okapi
import pickle
import os
from typing import List, Dict, Tuple
import json

import re

STOP_WORDS = {
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 
    'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 
    'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 
    'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 
    'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 
    'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 
    'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 
    'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 
    'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 
    'should', 'now'
}

class BM25Index:
    def __init__(self, index_path: str = "./bm25_index.pkl"):
        self.index_path = index_path
        self.corpus = []
        self.bm25 = None
        self.chunk_metadata = []
        self.chunk_texts = []
        self.last_load_time = 0.0
        
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text by extracting alphanumeric words and removing stop words"""
        words = re.findall(r'\b[a-z0-9]+\b', text.lower())
        return [w for w in words if w not in STOP_WORDS]
        
    def build_index(self, chunks: List[Dict]):
        """Build BM25 index from text chunks"""
        # Extract text and tokenize
        corpus = []
        self.chunk_metadata = []
        
        for chunk in chunks:
            # Better tokenization with stopword removal
            tokens = self._tokenize(chunk["text"])
            corpus.append(tokens)
            self.chunk_metadata.append(chunk["metadata"])
            self.chunk_texts.append(chunk["text"])
        
        self.corpus = corpus
        self.bm25 = BM25Okapi(corpus)
        
        # Save index
        self.save_index()
    
    def save_index(self):
        """Save BM25 index to disk"""
        index_data = {
            "corpus": self.corpus,
            "chunk_metadata": self.chunk_metadata,
            "chunk_texts": getattr(self, "chunk_texts", [])
        }
        
        with open(self.index_path, 'wb') as f:
            pickle.dump(index_data, f)
        
        # Also save metadata separately for easier access
        metadata_path = self.index_path.replace('.pkl', '_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(self.chunk_metadata, f, indent=2)
    
    def load_index(self):
        """Load BM25 index from disk"""
        if not os.path.exists(self.index_path):
            return False
            
        with open(self.index_path, 'rb') as f:
            index_data = pickle.load(f)
        
        self.corpus = index_data["corpus"]
        self.chunk_metadata = index_data["chunk_metadata"]
        self.chunk_texts = index_data.get("chunk_texts", [" ".join(tokens) for tokens in self.corpus])
        self.bm25 = BM25Okapi(self.corpus)
        self.last_load_time = os.path.getmtime(self.index_path)
        
        return True
    
    def search(self, query: str, top_k: int = 5, filter_criteria: Dict = None) -> List[Tuple[Dict, float]]:
        """Search using BM25 with optional filtering"""
        # Auto-reload if file was updated by another process (e.g. Celery)
        if os.path.exists(self.index_path):
            current_mtime = os.path.getmtime(self.index_path)
            if current_mtime > self.last_load_time:
                self.load_index()

        if not self.bm25:
            return []
        
        # Tokenize query
        query_tokens = self._tokenize(query)
        
        # Get scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Apply filtering if criteria provided
        valid_indices = []
        for idx, metadata in enumerate(self.chunk_metadata):
            if self._matches_filter(metadata, filter_criteria):
                valid_indices.append(idx)
        
        # Filter scores to only include valid indices
        # Filter scores to only include valid indices
        if filter_criteria:
            if not valid_indices:
                return []
            filtered_scores = [(idx, scores[idx]) for idx in valid_indices if scores[idx] > 0]
            filtered_scores.sort(key=lambda x: x[1], reverse=True)
            top_results = filtered_scores[:top_k]
        else:
            # Get top results from all indices
            top_indices = scores.argsort()[-top_k:][::-1]
            top_results = [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]
        
        results = []
        for idx, score in top_results:
            chunk_text = self.chunk_texts[idx] if hasattr(self, 'chunk_texts') and idx < len(self.chunk_texts) else " ".join(self.corpus[idx])
            result = {
                "text": chunk_text,
                "metadata": self.chunk_metadata[idx],
                "score": float(score)
            }
            results.append((result, score))
        
        return results
    
    def _matches_filter(self, metadata: Dict, filter_criteria: Dict) -> bool:
        """Check if metadata matches filter criteria"""
        if not filter_criteria:
            return True
        
        for key, value in filter_criteria.items():
            if key == "session_id":
                # Check if chunk has session_id in metadata or as a direct field
                chunk_session_id = metadata.get("session_id")
                if chunk_session_id != value:
                    return False
            elif key == "source":
                if isinstance(value, dict) and "$in" in value:
                    # Handle $in operator for multiple sources
                    if metadata.get("source_file") not in value["$in"]:
                        return False
                else:
                    if metadata.get("source_file") != value:
                        return False
            else:
                if metadata.get(key) != value:
                        return False
        
        return True
    
    def add_chunks(self, new_chunks: List[Dict]):
        """Add new chunks to existing index"""
        # Add to corpus
        for chunk in new_chunks:
            tokens = self._tokenize(chunk["text"])
            self.corpus.append(tokens)
            
            # Include session_id in metadata if present
            metadata = chunk["metadata"].copy()
            if "session_id" in chunk:
                metadata["session_id"] = chunk["session_id"]
            
            self.chunk_metadata.append(metadata)
            
            if not hasattr(self, 'chunk_texts'):
                self.chunk_texts = [" ".join(t) for t in self.corpus[:-1]]
            self.chunk_texts.append(chunk["text"])
        
        # Rebuild index
        self.bm25 = BM25Okapi(self.corpus)
        self.save_index()

    def delete_by_source_file(self, source_file: str):
        """Delete all chunks from a specific source file and rebuild index"""
        new_corpus = []
        new_metadata = []
        new_texts = []
        
        for i, meta in enumerate(self.chunk_metadata):
            if meta.get("source_file") != source_file:
                new_corpus.append(self.corpus[i])
                new_metadata.append(meta)
                if hasattr(self, 'chunk_texts') and i < len(self.chunk_texts):
                    new_texts.append(self.chunk_texts[i])
                else:
                    new_texts.append(" ".join(self.corpus[i]))
                
        if len(new_corpus) == len(self.corpus):
            return  # No change
            
        self.corpus = new_corpus
        self.chunk_metadata = new_metadata
        self.chunk_texts = new_texts
        if self.corpus:
            self.bm25 = BM25Okapi(self.corpus)
        else:
            self.bm25 = None
        self.save_index()
