from pathlib import Path
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .chunking import chunk_text
from .embeddings import get_embedder
from .vector_store import VectorStore
from .ingestion import validate_extension, extract_text
from .prompts import build_prompt, RATE_LIMIT_MESSAGE
from .groq_client import stream_chat, RateLimitError_

# Built Vue bundle. backend/app/main.py -> backend/app -> backend -> repo root.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

app = FastAPI(title="DevAssist Chatbot", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

_embedder = None
store = VectorStore()

def embedder():
    global _embedder
    if _embedder is None:
        _embedder = get_embedder(settings.embedding_backend, settings.embedding_model)
    return _embedder

@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(store), "vector_backend": store.backend,
            "embedding_backend": getattr(embedder(), "name", "unknown"),
            "groq_configured": bool(settings.groq_api_key),
            "frontend": "built" if FRONTEND_DIST.is_dir() else "not-built"}

# Service metadata moved off "/" because GET / now serves the Vue application.
@app.get("/api-info", include_in_schema=False)
def api_info():
    return {"service": "DevAssist Chatbot", "docs": "/docs", "health": "/health"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """SRS 4.1 POST /upload"""
    try:
        validate_extension(file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = await file.read()
    if len(data) > settings.max_file_bytes:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 5MB.")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")
    try:
        text = extract_text(file.filename, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not extract text: {e}")
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="No extractable text found in file.")
    embeddings = embedder().encode(chunks)
    store.add(embeddings, chunks, source=file.filename)
    return {"status": "success", "chunks_processed": len(chunks), "filename": file.filename}

@app.get("/documents")
def documents():
    from collections import Counter
    return {"total_chunks": len(store), "files": dict(Counter(store.sources))}

@app.delete("/documents")
def clear_documents():
    store.clear(); return {"status": "cleared"}

@app.delete("/documents/{filename}")
def delete_document(filename: str):
    """Remove one document's indexed chunks. The filename must match the value
    reported by GET /documents (it is percent-encoded by the client)."""
    removed = store.remove_source(filename)
    if removed == 0:
        raise HTTPException(status_code=404, detail="Document is not in the index.")
    return {"status": "removed", "filename": filename, "chunks_removed": removed}

@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """SRS 4.2 WebSocket /ws/chat — streaming tokens."""
    await ws.accept()
    try:
        while True:
            payload = await ws.receive_json()
            message = (payload or {}).get("message", "").strip()
            document_id = (payload or {}).get("document_id", "").strip()
            if not message:
                await ws.send_json({"status": "error", "error": "Message must not be empty."}); continue

            # Validate document_id exists in store; if not, treat as no document selected
            document_selected = bool(document_id and document_id in store.sources)

            context: list[str] = []
            if document_selected and len(store) > 0:
                q = embedder().encode([message])
                context = store.search(q, top_k=settings.top_k, source=document_id)
                # SRS 5.2 keep context < 4000 tokens (~ chars cap)
                joined, total = [], 0
                for c in context:
                    if total + len(c) > settings.max_context_chars:
                        break
                    joined.append(c); total += len(c)
                context = joined
            # If document_selected but no context found, let the model handle it via prompt (not an error)

            messages = build_prompt(message, context, document_selected=document_selected)
            try:
                async for token in stream_chat(messages, settings.groq_api_key, settings.groq_model):
                    await ws.send_json({"token": token, "status": "streaming"})
                await ws.send_json({"status": "done"})
            except RateLimitError_:
                await ws.send_json({"token": RATE_LIMIT_MESSAGE, "status": "error", "error": RATE_LIMIT_MESSAGE})
            except Exception as e:
                if "429" in str(e):
                    await ws.send_json({"token": RATE_LIMIT_MESSAGE, "status": "error", "error": RATE_LIMIT_MESSAGE})
                else:
                    await ws.send_json({"status": "error", "error": f"Chat failed: {e}"})
    except WebSocketDisconnect:
        return


# ---------------------------------------------------------------------------
# Static frontend (single-server deployment).
#
# Everything below is registered AFTER the API routes and the WebSocket route, so
# FastAPI's first-match-wins ordering guarantees /health, /documents, /upload and
# /ws/chat always win and the catch-all can never intercept them. /ws/chat is also
# unreachable from here because a websocket handshake is not a GET request.
#
# Dev note: `npm run dev` (Vite on 5173) is unaffected. This only serves the bundle
# produced by `npm run build`.
# ---------------------------------------------------------------------------
_RESERVED = ("health", "documents", "upload", "ws", "docs", "openapi.json", "redoc", "api-info")


def _resolve_in_dist(rel_path: str) -> Path | None:
    """Resolve rel_path inside FRONTEND_DIST, or None if it escapes the directory."""
    if not rel_path:
        return None
    candidate = (FRONTEND_DIST / rel_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST.resolve())
    except ValueError:
        return None  # path traversal attempt
    return candidate


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def serve_index():
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        return JSONResponse(
            status_code=503,
            content={"error": "Frontend not built",
                     "hint": "run `npm run build` in frontend/, then reload",
                     "api_docs": "/docs", "health": "/health"},
        )
    return FileResponse(index)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """Serve a real file from dist when it exists, otherwise index.html for client-side routing."""
    if full_path.split("/")[0] in _RESERVED:
        raise HTTPException(status_code=404, detail="Not Found")
    if FRONTEND_DIST.is_dir():
        target = _resolve_in_dist(full_path)
        if target is not None and target.is_file():
            return FileResponse(target)
    return serve_index()
