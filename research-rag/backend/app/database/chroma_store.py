import chromadb
from chromadb.config import Settings
import numpy as np
import os
from typing import List, Dict, Tuple, Optional
import uuid
# pyrefly: ignore [missing-import]
from app.utils.config import config

class ChromaStore:
    def __init__(self, db_path: str = None, collection_name: str = "pdf_chunks"):
        self.db_path = db_path or config.CHROMA_DB_PATH
        self.client = None
        self.collection = None
        self.collection_name = collection_name
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Chroma client and collection"""
        # Create directory if it doesn't exist
        os.makedirs(self.db_path, exist_ok=True)
        
        # Initialize Chroma client with persistent storage
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            col_meta = self.collection.metadata or {}
            self.uses_l2 = col_meta.get("hnsw:space", "l2") != "cosine"
            if self.uses_l2:
                print(f"Warning: Collection '{self.collection_name}' uses L2 distance. Re-ingestion is recommended for pure cosine similarity. Using L2 fallback mapping.")
        except Exception:
            # Collection doesn't exist, create it
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "PDF document chunks for Q&A", "hnsw:space": "cosine"}
            )
            self.uses_l2 = False
    
    def add_chunks(self, chunks: List[Dict], embeddings: Optional[np.ndarray] = None):
        """Add chunks to Chroma collection"""
        if not chunks:
            return
            
        try:
            self._do_add_chunks(chunks, embeddings)
        except Exception:
            # Re-initialize in case collection was deleted by another process
            self._initialize_client()
            self._do_add_chunks(chunks, embeddings)
            
    def _do_add_chunks(self, chunks: List[Dict], embeddings: Optional[np.ndarray] = None):
        
        # Prepare data for Chroma
        documents = []
        metadatas = []
        ids = []
        
        for i, chunk in enumerate(chunks):
            # Generate unique ID for each chunk
            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)
            
            # Document text
            documents.append(chunk["text"])
            
            # Metadata (Chroma requires string values)
            metadata = {
                "source_file": str(chunk["metadata"]["source_file"]),
                "page_number": str(chunk["metadata"]["page_number"]),
                "chunk_id": str(chunk["metadata"]["chunk_id"]),
                "tokens": str(chunk.get("tokens", 0)),
                "session_id": str(chunk.get("session_id", ""))
            }
            metadatas.append(metadata)
        
        # Add to collection
        if embeddings is not None:
            # Use provided embeddings
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings.tolist()
            )
        else:
            # Let Chroma generate embeddings
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
    
    def search(self, query: str, top_k: int = 5, query_embedding: Optional[np.ndarray] = None, filter_criteria: Dict = None) -> List[Tuple[Dict, float]]:
        """Search for similar chunks with optional filtering"""
        if not self.collection:
            return []
            
        try:
            return self._do_search(query, top_k, query_embedding, filter_criteria)
        except Exception:
            self._initialize_client()
            return self._do_search(query, top_k, query_embedding, filter_criteria)
            
    def _do_search(self, query: str, top_k: int = 5, query_embedding: Optional[np.ndarray] = None, filter_criteria: Dict = None) -> List[Tuple[Dict, float]]:
        if not self.collection:
            return []
        
        try:
            # Build where clause from filter criteria
            where_clause = self._build_where_clause(filter_criteria)
            
            if query_embedding is not None:
                # Use provided embedding for search
                results = self.collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                    where=where_clause
                )
            else:
                # Use text query (Chroma will generate embedding)
                results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                    where=where_clause
                )
            
            # Format results
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    raw_dist = results["distances"][0][i]
                    if getattr(self, "uses_l2", False):
                        # L2 squared fallback for normalized embeddings (ranges 0 to 4)
                        score = 1.0 - (raw_dist / 2.0)
                    else:
                        # Cosine distance (ranges 0 to 2)
                        score = 1.0 - raw_dist
                        
                    # Clamp to [0, 1]
                    score = max(0.0, min(1.0, score))
                    
                    result = {
                        "text": results["documents"][0][i],
                        "metadata": {
                            "source_file": results["metadatas"][0][i]["source_file"],
                            "page_number": int(results["metadatas"][0][i]["page_number"]),
                            "chunk_id": int(results["metadatas"][0][i]["chunk_id"]),
                            "tokens": int(results["metadatas"][0][i]["tokens"])
                        },
                        "score": score
                    }
                    formatted_results.append((result, score))
            
            return formatted_results
            
        except Exception as e:
            print(f"Error searching Chroma: {str(e)}")
            return []
    
    def _build_where_clause(self, filter_criteria: Dict) -> Optional[Dict]:
        """Build Chroma where clause from filter criteria"""
        if not filter_criteria:
            return None
        
        where_conditions = []
        
        for key, value in filter_criteria.items():
            if key == "session_id":
                where_conditions.append({"session_id": {"$eq": str(value)}})
            elif key == "source":
                if isinstance(value, dict) and "$in" in value:
                    # Handle $in operator for multiple sources
                    where_conditions.append({"source_file": {"$in": [str(v) for v in value["$in"]]}})
                else:
                    where_conditions.append({"source_file": {"$eq": str(value)}})
            else:
                where_conditions.append({key: {"$eq": str(value)}})
        
        if len(where_conditions) == 1:
            return where_conditions[0]
        elif len(where_conditions) > 1:
            return {"$and": where_conditions}
        
        return None
    
    def get_collection_count(self) -> int:
        """Get number of documents in collection"""
        if not self.collection:
            return 0
        return self.collection.count()
    
    def delete_collection(self):
        """Delete the entire collection"""
        if self.collection:
            self.client.delete_collection(name=self.collection_name)
            self.collection = None
            
    def delete_by_source_file(self, source_file: str):
        """Delete all chunks from a specific source file"""
        if not self.collection:
            return
        try:
            self.collection.delete(where={"source_file": {"$eq": source_file}})
        except Exception as e:
            print(f"Error deleting from Chroma: {str(e)}")
    
    def reset_collection(self):
        """Reset collection (delete and recreate)"""
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            pass  # Collection might not exist
        
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"description": "PDF document chunks for Q&A", "hnsw:space": "cosine"}
        )
        self.uses_l2 = False
    
    def get_chunk_by_metadata(self, source_file: str, page_number: int) -> List[Dict]:
        """Get chunks by source file and page number"""
        if not self.collection:
            return []
        
        try:
            results = self.collection.get(
                where={
                    "$and": [
                        {"source_file": {"$eq": source_file}},
                        {"page_number": {"$eq": str(page_number)}}
                    ]
                },
                include=["documents", "metadatas"]
            )
            
            chunks = []
            if results["documents"]:
                for i in range(len(results["documents"])):
                    chunk = {
                        "text": results["documents"][i],
                        "metadata": {
                            "source_file": results["metadatas"][i]["source_file"],
                            "page_number": int(results["metadatas"][i]["page_number"]),
                            "chunk_id": int(results["metadatas"][i]["chunk_id"]),
                            "tokens": int(results["metadatas"][i]["tokens"])
                        }
                    }
                    chunks.append(chunk)
            
            return chunks
            
        except Exception as e:
            print(f"Error retrieving chunks: {str(e)}")
            return []
    
    def update_chunk_metadata(self, chunk_id: str, new_metadata: Dict):
        """Update metadata for a specific chunk"""
        try:
            # Convert metadata values to strings
            string_metadata = {k: str(v) for k, v in new_metadata.items()}
            
            self.collection.update(
                ids=[chunk_id],
                metadatas=[string_metadata]
            )
        except Exception as e:
            print(f"Error updating chunk metadata: {str(e)}")
