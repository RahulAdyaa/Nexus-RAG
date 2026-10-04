import os
from dotenv import load_dotenv

load_dotenv(".ENV", override=True) # Force reload environment variables from .ENV

class Config:
    # LLM Provider: "ollama", "gemini", "groq", or "openrouter"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
    
    # OpenRouter settings
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.8-27b")
    
    # Groq settings
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    
    # Gemini settings (only needed when LLM_PROVIDER=gemini)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    
    # Ollama settings (only needed when LLM_PROVIDER=ollama)
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    
    # Storage
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
    SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./metadata.db")
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50
    EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
    RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    @classmethod
    def validate(cls):
        if cls.LLM_PROVIDER == "gemini" and not cls.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required when LLM_PROVIDER=gemini")

config = Config()
