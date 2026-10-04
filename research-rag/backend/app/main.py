from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
import shutil
import tempfile
from datetime import datetime
import uuid
import time

from .services.pdf_loader import PDFLoader
from .services.text_splitter import TextSplitter
from .services.retriever import HybridRetriever
from .services.llm import GeminiLLMService
from .services.semantic_cache import SemanticCache
from .database.sqlite_store import SQLiteStore
from .utils.config import config

# Initialize FastAPI app
app = FastAPI(
    title="Multi-PDF Q&A Assistant",
    description="A hybrid retrieval system for PDF question answering using BM25 and embeddings",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
pdf_loader = PDFLoader()
text_splitter = TextSplitter()
retriever = HybridRetriever()
llm_service = GeminiLLMService()
semantic_cache = SemanticCache()
db_store = SQLiteStore()

# Create upload directory
os.makedirs(config.UPLOAD_DIR, exist_ok=True)

# Mount the uploads directory to serve PDFs
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")

# Pydantic models
class QuestionRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5
    bm25_weight: Optional[float] = 0.5
    embedding_weight: Optional[float] = 0.5
    search_scope: Optional[str] = "session"  # "session", "selected", "all"
    selected_documents: Optional[List[str]] = None
    session_id: Optional[str] = None
    chat_history: Optional[List[Dict[str, str]]] = []

class SuggestRequest(BaseModel):
    chat_history: List[Dict[str, str]]

class QuestionResponse(BaseModel):
    answer: str
    sources: List[dict]
    context_used: int
    success: bool
    confidence: Optional[str] = None
    error: Optional[str] = None

class UploadResponse(BaseModel):
    message: str
    files_processed: int
    total_chunks: int
    success: bool
    session_id: str
    uploaded_files: List[str]
    task_id: Optional[str] = None
    error: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "Multi-PDF Q&A Assistant API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    try:
        stats = retriever.get_collection_stats()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "collections": stats
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def cleanup_old_uploads():
    """Remove PDF files older than 2 hours from the uploads cache to save space"""
    try:
        now = time.time()
        max_age = 2 * 3600  # 2 hours
        for filename in os.listdir(config.UPLOAD_DIR):
            file_path = os.path.join(config.UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                if os.stat(file_path).st_mtime < now - max_age:
                    os.remove(file_path)
    except Exception as e:
        print(f"Error during upload cache cleanup: {e}")

@app.post("/upload", response_model=UploadResponse)
async def upload_pdfs(files: List[UploadFile] = File(...)):
    try:
        cleanup_old_uploads()
        
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        session_id = str(uuid.uuid4())
        uploaded_files = []
        file_metadata_list = []
        
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                continue
            
            file_path = os.path.join(config.UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            uploaded_files.append(file.filename)
            file_metadata_list.append({
                "file_path": file_path,
                "filename": file.filename
            })
        
        if not file_metadata_list:
            raise HTTPException(status_code=400, detail="No valid PDF files provided")
            
        # Send to Celery worker
        from app.worker import process_documents_task
        task = process_documents_task.delay(file_metadata_list, session_id)
        
        return UploadResponse(
            message="Processing started in the background",
            files_processed=len(uploaded_files),
            total_chunks=0,
            success=True,
            session_id=session_id,
            uploaded_files=uploaded_files,
            task_id=task.id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing files: {str(e)}")

@app.get("/upload/status/{task_id}")
async def get_upload_status(task_id: str):
    from app.worker import celery_app
    task_result = celery_app.AsyncResult(task_id)
    
    if task_result.state == 'PENDING':
        return {"status": "processing", "message": "Task is waiting or running..."}
    elif task_result.state != 'FAILURE':
        return {"status": "completed", "result": task_result.info}
    else:
        return {"status": "failed", "error": str(task_result.info)}

@app.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    try:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        
        # Prepare filter criteria based on search scope
        filter_criteria = None
        cache_scope_key = "all"
        if request.search_scope == "session" and request.session_id:
            filter_criteria = {"session_id": request.session_id}
            cache_scope_key = f"session_{request.session_id}"
        elif request.search_scope == "selected" and request.selected_documents:
            filter_criteria = {"source": {"$in": request.selected_documents}}
            cache_scope_key = f"selected_{','.join(sorted(request.selected_documents))}"
        
        # Check Semantic Cache
        query_emb = retriever.embedding_service.generate_query_embedding(request.question)
        cached_result = semantic_cache.get(query_emb, cache_scope_key)
        
        if cached_result:
            return QuestionResponse(
                answer=cached_result["answer"],
                sources=cached_result["sources"],
                context_used=cached_result["context_used"],
                success=True,
                confidence="High (Cache Hit)",
                error=None
            )
        
        # Expand the query using LLM for better recall
        expanded_queries = llm_service.expand_query(request.question)

        retrieved_chunks = retriever.hybrid_search(
            query=request.question,
            top_k=request.top_k,
            bm25_weight=request.bm25_weight,
            embedding_weight=request.embedding_weight,
            filter_criteria=filter_criteria,
            expanded_queries=expanded_queries
        )
        
        if not retrieved_chunks:
            scope_message = ""
            if request.search_scope == "session":
                scope_message = " in the current session"
            elif request.search_scope == "selected":
                scope_message = " in the selected documents"
            
            return QuestionResponse(
                answer=f"I couldn't find any relevant information{scope_message} to answer your question.",
                sources=[],
                context_used=0,
                success=True
            )
        
        llm_response = llm_service.generate_answer(
            query=request.question,
            context_chunks=retrieved_chunks,
            chat_history=request.chat_history
        )
        
        if llm_response["success"]:
            semantic_cache.set(
                query=request.question,
                query_embedding=query_emb,
                answer=llm_response["answer"],
                sources=llm_response["sources"],
                context_used=llm_response["context_used"],
                scope_key=cache_scope_key
            )
        
        return QuestionResponse(
            answer=llm_response["answer"],
            sources=llm_response["sources"],
            context_used=llm_response["context_used"],
            success=llm_response["success"],
            confidence=llm_response.get("confidence", "Low"),
            error=llm_response.get("error")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

@app.post("/ask/stream")
async def ask_question_stream(request: QuestionRequest):
    """Stream answer tokens via Server-Sent Events for instant-feeling responses"""
    try:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        
        # Prepare filter criteria based on search scope
        filter_criteria = None
        cache_scope_key = "all"
        if request.search_scope == "session" and request.session_id:
            filter_criteria = {"session_id": request.session_id}
            cache_scope_key = f"session_{request.session_id}"
        elif request.search_scope == "selected" and request.selected_documents:
            filter_criteria = {"source": {"$in": request.selected_documents}}
            cache_scope_key = f"selected_{','.join(sorted(request.selected_documents))}"
            
        # Check Semantic Cache
        query_emb = retriever.embedding_service.generate_query_embedding(request.question)
        cached_result = semantic_cache.get(query_emb, cache_scope_key)
        
        import json
        if cached_result:
            def cache_stream():
                yield json.dumps({"type": "sources", "sources": cached_result["sources"], "context_used": cached_result["context_used"]}) + "\n"
                yield json.dumps({"type": "token", "content": cached_result["answer"]}) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
            return StreamingResponse(cache_stream(), media_type="text/event-stream")
        
        # Expand the query using LLM for better recall
        expanded_queries = llm_service.expand_query(request.question)
        
        retrieved_chunks = retriever.hybrid_search(
            query=request.question,
            top_k=request.top_k,
            bm25_weight=request.bm25_weight,
            embedding_weight=request.embedding_weight,
            filter_criteria=filter_criteria,
            expanded_queries=expanded_queries
        )
        
        if not retrieved_chunks:
            import json
            def empty_stream():
                yield json.dumps({"type": "sources", "sources": [], "context_used": 0}) + "\n"
                yield json.dumps({"type": "token", "content": "I couldn't find any relevant information to answer your question."}) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
            return StreamingResponse(empty_stream(), media_type="text/event-stream")
        
        def cache_wrapper_stream(generator):
            full_answer = ""
            sources = []
            context_used = 0
            for chunk in generator:
                yield chunk
                try:
                    data = json.loads(chunk.strip())
                    if data.get("type") == "token":
                        full_answer += data.get("content", "")
                    elif data.get("type") == "sources":
                        sources = data.get("sources", [])
                        context_used = data.get("context_used", 0)
                except:
                    pass
            
            if full_answer:
                semantic_cache.set(
                    query=request.question,
                    query_embedding=query_emb,
                    answer=full_answer,
                    sources=sources,
                    context_used=context_used,
                    scope_key=cache_scope_key
                )
                
        base_stream = llm_service.generate_answer_stream(
            query=request.question,
            context_chunks=retrieved_chunks,
            chat_history=request.chat_history
        )
        
        return StreamingResponse(
            cache_wrapper_stream(base_stream),
            media_type="text/event-stream"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

@app.post("/ask/suggest")
async def suggest_followup_questions(request: SuggestRequest):
    """Generate follow-up questions based on chat history"""
    try:
        suggestions = llm_service.generate_suggestions(request.chat_history)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating suggestions: {str(e)}")

@app.get("/documents")
async def get_documents():
    try:
        documents = db_store.get_documents()
        return {"documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving documents: {str(e)}")

@app.get("/sessions/{session_id}/documents")
async def get_session_documents(session_id: str):
    try:
        documents = db_store.get_documents_by_session(session_id)
        return {"session_id": session_id, "documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving session documents: {str(e)}")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: int):
    try:
        doc = db_store.get_document_by_id(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        filename = doc["filename"]
        
        # Delete from SQLite
        db_store.delete_document(document_id)
        
        # Delete from Chroma and BM25
        retriever.delete_document(filename)
        
        # Delete file from uploads directory
        file_path = os.path.join(config.UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        return {"message": f"Document {filename} deleted successfully", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")

@app.get("/stats")
async def get_stats():
    try:
        collection_stats = retriever.get_collection_stats()
        documents = db_store.get_documents()
        
        return {
            "total_documents": len(documents),
            "total_chunks": collection_stats.get("chroma_count", 0),
            "bm25_index_size": collection_stats.get("bm25_count", 0),
            "chroma_collection_size": collection_stats.get("chroma_count", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")

@app.delete("/clear")
async def clear_all_data():
    try:
        retriever.clear_indices()
        
        # Also clear the uploads cache
        for filename in os.listdir(config.UPLOAD_DIR):
            file_path = os.path.join(config.UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                
        return {"message": "All data cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
