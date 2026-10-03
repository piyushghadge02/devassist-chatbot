### Byte 1: Project purpose and overall architecture

**Builds on:** None — starting point

**In plain terms:**
DevAssist Chatbot is a programming-only AI assistant with a rudimentary Retrieval-Augmented Generation (RAG) system. Users upload technical documents (.txt, .md, .pdf up to 5MB), which are chunked, embedded, and stored in an in-memory vector index. When a user asks a question, the system retrieves the top-3 relevant chunks, injects them into a programming-only system prompt, and streams the answer via WebSocket from Groq Cloud (or an offline fallback when no API key is set). The frontend is a Vue 3 SPA served by the same FastAPI process in production.

**The code:**
```python
# backend/app/main.py — API routes and WebSocket handler
app = FastAPI(title="DevAssist Chatbot", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

_embedder = None
store = VectorStore()

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # validate, extract, chunk, embed, store
    ...

@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    # retrieve top-3, build prompt with context, stream from Groq
    ...
```

---

### Byte 2: Project/repository structure

**Builds on:** Byte 1

**In plain terms:**
The repository is a monorepo with a Python FastAPI backend and a Vue 3 frontend. The backend lives in `backend/app/` with modules for config, chunking, embeddings, vector store, ingestion, prompts, and the Groq client. The frontend lives in `frontend/src/` with a single-file component (`App.vue`) and a small utility library (`lib/chat.js`). Tests are in `backend/tests/` (pytest) and `frontend/tests/` (vitest). The built frontend bundle is served by FastAPI from `frontend/dist/`.

**The code:**
```text
devassist-chatbot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI routes + WebSocket
│   │   ├── config.py        # Settings from environment
│   │   ├── chunking.py      # 500-char chunks, 50-char overlap
│   │   ├── embeddings.py    # MiniLM or hash fallback
│   │   ├── vector_store.py  # FAISS or NumPy cosine fallback
│   │   ├── ingestion.py     # File validation + text extraction
│   │   ├── prompts.py       # System prompt + RAG context builder
│   │   └── groq_client.py   # Streaming chat with offline fallback
│   ├── tests/test_api.py
│   ├── run.py
│   └── requirements*.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue          # Single component: sidebar + chat + composer
│   │   ├── main.js          # Vue mount
│   │   ├── style.css        # Tailwind + highlight.js theme
│   │   └── lib/chat.js      # Markdown rendering, validation, WS helper
│   ├── tests/chat.test.js
│   └── package.json
└── README.md
```

---

### Byte 3: Backend configuration

**Builds on:** Byte 2

**In plain terms:**
All settings are read from environment variables (with `.env` support via `python-dotenv`) at startup in `config.py`. The `Settings` class holds the Groq API key and model, embedding backend choice (`auto`, `hash`, or `sentence-transformers`), chunk size/overlap, retrieval `top_k`, context character cap (~4000 tokens = 12000 chars), and CORS origins. The SRS-specified Groq models were decommissioned, so the default is now `openai/gpt-oss-120b`. Configuration is a singleton instance `settings` imported everywhere.

**The code:**
```python
# backend/app/config.py
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
except Exception:
    pass

class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "auto")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", str(5 * 1024 * 1024)))
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 3
    max_context_chars: int = 12000  # ~ <4000 tokens, SRS 5.2
    cors_origins: list = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

settings = Settings()
```

---

### Byte 4: Document ingestion and file handling

**Builds on:** Byte 3

**In plain terms:**
Ingestion validates file extensions (only `.txt`, `.md`, `.pdf`), enforces the 5MB size limit, and extracts text. PDFs use `pypdf.PdfReader`; text/Markdown files are decoded as UTF-8 (with `errors="ignore"`). The `upload` endpoint in `main.py` orchestrates this: validate → read → extract → chunk → embed → store. Errors return 400 (bad type, empty) or 413 (oversize). The frontend mirrors this validation client-side for instant feedback.

**The code:**
```python
# backend/app/ingestion.py
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}

def validate_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext or '(none)'}'. Allowed: .txt, .md, .pdf")
    return ext

def extract_text(filename: str, data: bytes) -> str:
    ext = validate_extension(filename)
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return data.decode("utf-8", errors="ignore")
```

```python
# backend/app/main.py — upload endpoint (excerpt)
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    validate_extension(file.filename or "")
    data = await file.read()
    if len(data) > settings.max_file_bytes:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 5MB.")
    text = extract_text(file.filename, data)
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    embeddings = embedder().encode(chunks)
    store.add(embeddings, chunks, source=file.filename)
    return {"status": "success", "chunks_processed": len(chunks), "filename": file.filename}
```

---

### Byte 5: Text chunking

**Builds on:** Byte 4

**In plain terms:**
The chunker splits extracted text into fixed-size overlapping windows: 500 characters per chunk with 50 characters of overlap (so each new chunk starts 450 chars after the previous one). This matches SRS §3.3. The algorithm strips whitespace, then walks the text with a sliding window. Empty input returns an empty list. The step size is `chunk_size - overlap` (450). Chunking is deterministic and fast — no NLP or sentence-boundary awareness.

**The code:**
```python
# backend/app/chunking.py
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """SRS 3.3: chunk size 500 characters, overlap 50 characters."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    text = (text or "").strip()
    if not text:
        return []
    chunks, start, step = [], 0, chunk_size - overlap
    while start < len(text):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
        start += step
    return chunks
```

---

### Byte 6: Embeddings

**Builds on:** Byte 5

**In plain terms:**
Embeddings convert text chunks into 384-dimensional vectors (matching `all-MiniLM-L6-v2`). Two backends exist: `SentenceTransformerEmbedder` loads the real model via `sentence-transformers` (downloads on first use), and `HashEmbedder` is a deterministic offline fallback that hashes tokens into a fixed-size vector — used in tests and when the model can't be downloaded. `get_embedder()` selects the backend: explicit `"hash"` or `"sentence-transformers"`, or `"auto"` (tries the real model, falls back to hash on any error). The embedder is lazily initialized once per process and cached in `main.py`.

**The code:**
```python
# backend/app/embeddings.py
import hashlib, math
import numpy as np

DIM = 384  # all-MiniLM-L6-v2 dimension

class HashEmbedder:
    """Deterministic offline embedder (same dimension as MiniLM)."""
    name = "hash-fallback"
    def encode(self, texts: list[str]) -> np.ndarray:
        out = []
        for t in texts:
            vec = np.zeros(DIM, dtype="float32")
            tokens = t.lower().split() or [""]
            for tok in tokens:
                h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
                vec[h % DIM] += 1.0
                vec[(h >> 8) % DIM] += 0.5
            n = np.linalg.norm(vec)
            out.append(vec / n if n else vec)
        return np.array(out, dtype="float32")

class SentenceTransformerEmbedder:
    name = "sentence-transformers/all-MiniLM-L6-v2"
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
    def encode(self, texts: list[str]) -> np.ndarray:
        v = self._model.encode(texts, normalize_embeddings=True)
        return np.array(v, dtype="float32")

def get_embedder(backend: str = "auto", model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    if backend == "hash":
        return HashEmbedder()
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model_name)
    try:  # auto
        return SentenceTransformerEmbedder(model_name)
    except Exception:
        return HashEmbedder()
```