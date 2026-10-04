import os
import shutil
from celery import Celery
from typing import List

from .utils.config import config
from .services.pdf_loader import PDFLoader
from .services.text_splitter import TextSplitter
from .services.retriever import HybridRetriever
from .database.sqlite_store import SQLiteStore

# Initialize Celery
# Default Redis port is 6379 on localhost
celery_app = Celery(
    "rag_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# Initialize RAG components globally for the worker process
pdf_loader = PDFLoader()
text_splitter = TextSplitter()
db_store = SQLiteStore()
retriever = HybridRetriever()

@celery_app.task(name="process_documents_task")
def process_documents_task(file_metadata_list: List[dict], session_id: str):
    """
    Background task to process multiple PDFs.
    file_metadata_list: list of dicts with 'file_path' and 'filename'
    """
    total_files = len(file_metadata_list)
    processed_files = 0
    total_chunks = 0
    all_chunks = []

    for file_info in file_metadata_list:
        file_path = file_info["file_path"]
        filename = file_info["filename"]
        
        try:
            pages_data = pdf_loader.extract_text_from_pdf(file_path, filename)
            if not pages_data:
                continue
            
            chunks = text_splitter.process_pages_to_chunks(pages_data)
            if chunks:
                for chunk in chunks:
                    chunk['session_id'] = session_id
                
                all_chunks.extend(chunks)
                total_chunks += len(chunks)
                processed_files += 1
                
                file_size = os.path.getsize(file_path)
                db_store.add_document(
                    filename=filename,
                    total_pages=len(pages_data),
                    total_chunks=len(chunks),
                    file_size=file_size,
                    session_id=session_id
                )
                db_store.add_chunks(chunks)
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    # After processing all documents, add all chunks to retriever (creates embeddings)
    if all_chunks:
        retriever.add_documents(all_chunks)

    return {
        "status": "success",
        "processed_files": processed_files,
        "total_files": total_files,
        "total_chunks": total_chunks,
        "session_id": session_id
    }
