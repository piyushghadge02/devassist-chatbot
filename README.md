# DevAssist Chatbot

Programming-only assistant with rudimentary RAG, per SRS v1.0 (24 Nov 2025).

## Stack
- Frontend: Vue 3 (Composition API) + Vite + TailwindCSS, Markdown + syntax highlighting (marked + highlight.js + DOMPurify)
- Backend: Python FastAPI (async), WebSocket streaming
- AI: Groq Cloud API (model configurable, default `llama3-70b-8192` per SRS; e.g. set `GROQ_MODEL=llama-3.3-70b-versatile` if your Groq account no longer offers the legacy ID)
- Vector store: FAISS (in-memory; NumPy cosine fallback with identical interface if faiss-cpu is unavailable)
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` locally (384-dim). `EMBEDDING_BACKEND=hash` selects a deterministic offline embedder with the same dimension — useful for tests / no-download environments.

## Quick start
### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill GROQ_API_KEY
python run.py          # http://localhost:8000  (docs at /docs, health at /health)
```
Without a Groq key the backend still runs in a clearly-labelled offline mode, so the full upload → retrieval → streaming flow can be verified locally.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env   # optional; defaults match backend above
npm run dev            # http://localhost:5173
```

## API
- `POST /upload` — multipart file (.txt/.md/.pdf, < 5MB) → `{status, chunks_processed, filename}`
- `GET /health`, `GET /documents`, `DELETE /documents`
- `WebSocket /ws/chat` — send `{"message": "..."}`, receive `{"token": "...", "status": "streaming"}` … `{"status": "done"}`

## RAG specifics (SRS §3.3)
Chunk size 500 chars, overlap 50, retrieval top-3, in-memory only (restart clears documents), RAG context capped below 4000 tokens.

## Guardrails & limits (SRS §3.2, §5.1)
Programming-only enforced via system prompt (see `backend/app/prompts.py`). Send button disabled while generating. Groq HTTP 429 surfaces exactly: “Traffic is high. Please wait 10 seconds before asking again.”

## Tests
```bash
cd backend && EMBEDDING_BACKEND=hash python -m pytest tests/ -q
cd frontend && npm test && npm run build
python e2e/e2e_test.py   # backend running on :8000
```
