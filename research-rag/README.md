# Nexus-RAG

Nexus-RAG is a highly advanced, full-stack Retrieval-Augmented Generation (RAG) application. It allows users to upload PDF documents, intelligently chunk and embed the text, and perform highly accurate Question & Answering over the documents using a Hybrid Search (BM25 + ChromaDB Vectors) followed by a Cross-Encoder Reranking process.

## 🚀 Key Features

- **True Hybrid Retrieval:** Combines keyword search (BM25) and semantic search (ChromaDB + SentenceTransformers).
- **Cross-Encoder Reranking:** Ensures maximum precision by rescoring query/document pairs before sending them to the LLM.
- **LLM Agnostic:** Supports local inference via Ollama, or cloud inference via Groq, Google Gemini, and OpenRouter.
- **Streaming Responses:** Provides real-time streaming of LLM tokens via Server-Sent Events (SSE).
- **Query Expansion:** Automatically expands user queries into 2-3 variations to maximize document recall.
- **Smart Text Chunking:** Preserves semantic meaning using regex boundary protection for academic abbreviations and decimals.

## 🏗️ System Architecture

### Document Ingestion Flow
```mermaid
graph TD
    classDef process fill:#059669,stroke:#333,stroke-width:2px,color:#fff
    classDef storage fill:#F59E0B,stroke:#333,stroke-width:2px,color:#fff
    classDef error fill:#EF4444,stroke:#333,stroke-width:2px,color:#fff

    User((User)) --> |"1. Upload PDF"| API["API Endpoint<br/>POST /upload"]:::process
    API --> |"2. Save raw bytes"| FS[("Local Filesystem<br/>(uploads/)")]:::storage
    API --> |"3. Extract text"| Loader["PDF Loader<br/>(PyMuPDF)"]:::process
    Loader --> |"4. Clean & normalize"| Preprocessor["Text Preprocessor"]:::process
    Preprocessor --> |"5. Split text"| Chunking["Text Splitter<br/>(tiktoken)"]:::process
    Chunking --> |"6. Add metadata"| SQLite[("SQLite<br/>(Metadata)")]:::storage
    Chunking --> |"7. Distribute"| Retriever["Hybrid Retriever"]:::process
    Retriever --> |"8. Vectorize"| Embedder["Embedding Service"]:::process
    Embedder --> Chroma[("ChromaDB<br/>(Vectors)")]:::storage
    Retriever --> BM25["BM25 Indexer"]:::process
    BM25 --> Pickle[("BM25 Pickle")]:::storage
```

### Question Answering Flow
```mermaid
graph TD
    classDef process fill:#059669,stroke:#333,stroke-width:2px,color:#fff
    classDef storage fill:#F59E0B,stroke:#333,stroke-width:2px,color:#fff
    classDef external fill:#8B5CF6,stroke:#333,stroke-width:2px,color:#fff

    User((User)) --> |"1. Question"| API["API Endpoint<br/>POST /ask"]:::process
    API --> Expander["Query Expansion<br/>(LLM Service)"]:::process
    Expander --> Hybrid["Hybrid Retriever"]:::process
    Hybrid --> BM25Search["BM25 Search"]:::process
    Hybrid --> EmbSearch["Vector Search"]:::process
    BM25Search & EmbSearch --> ScoreCombiner["Score Combiner"]:::process
    ScoreCombiner --> Reranker["Cross-Encoder Reranker"]:::process
    Reranker --> ContextFilter["Relevance Filter"]:::process
    ContextFilter --> PromptBuilder["Prompt Builder"]:::process
    PromptBuilder --> LLMRoute{"LLM Provider"}
    LLMRoute --> LocalLLM["Ollama / Gemini / Groq"]:::external
    LocalLLM --> Formatter["Response Formatter"]:::process
    Formatter --> User
```

## 🛠️ Tech Stack

- **Frontend:** React, Tailwind CSS
- **Backend:** FastAPI (Python), PyMuPDF, TikToken
- **Machine Learning:** SentenceTransformers (BAAI/bge-small-en for embeddings), CrossEncoder for reranking
- **Databases:** ChromaDB (Vector), SQLite (Relational), rank_bm25 (Keyword)
- **Deployment:** Vercel (Frontend), Render/Railway (Backend API)

## ⚙️ Local Setup

### 1. Backend Setup
Navigate to the `backend/` directory:
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.ENV` file in the `backend/` directory with the necessary keys (DO NOT commit this file to GitHub):
```env
# Example .ENV
LLM_PROVIDER=gemini # ollama | gemini | groq | openrouter
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-pro

GROQ_API_KEY=your_key_here
GROQ_MODEL=llama3-70b-8192

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3

EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

Start the backend server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup
Navigate to the `frontend/` directory:
```bash
cd frontend
npm install
npm start
```
The React app will proxy requests to the FastAPI backend running on port 8000.
