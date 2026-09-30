# Test Report — Local (pre-GitHub)

Date: 2026-10-01 (Asia/Calcutta)
Environment: Python 3.12.3, Node v24.20.0, npm 10.9.4

## Backend — pytest (EMBEDDING_BACKEND=hash)
14 tests: health, chunking 500/50, empty chunking, system prompt, upload TXT+retrieval,
upload MD, upload PDF, bad extension 400, oversize 413, WebSocket streaming+done,
WebSocket RAG context, WebSocket empty-message error, rate-limit message, FAISS top-3 limit.
Result: PASS (after fixing a malformed test PDF fixture and marked-highlight integration on frontend).

## Frontend — vitest + build
8 tests: markdown code highlighting, XSS sanitization, canSend gating (×3), rate-limit message,
upload validation (accept ×3 types, reject exe, reject >5MB). Result: PASS. `vite build`: PASS.

## Live local run
- Backend uvicorn :8000 — GET /health → {"status":"ok","vector_backend":"faiss","embedding_backend":"hash-fallback","groq_configured":false}
- POST /upload (sample.md) → {"status":"success","chunks_processed":13}
- WebSocket ws://localhost:8000/ws/chat → streamed tokens, RAG context used, terminated with done
- Frontend vite :5173 → serves index/App correctly
- e2e/e2e_test.py → PASS

## Not verified locally
Live Groq inference — no user Groq API key was provided/used. Offline mode covers the full pipeline.

## Known environment limitation
`pip install sentence-transformers` could not complete in this sandbox: its `torch`
wheel (554.6 MB) repeatedly truncated at 231.7 MB after 6 + 11 download attempts
(PyPI network issue, not a project defect). All other backend dependencies — including
faiss-cpu — installed and ran. Impact: local verification used the documented
384-dim hash embedder fallback (EMBEDDING_BACKEND=hash/auto-fallback); the
SentenceTransformer code path is present and is the default on machines where the
install completes (expected in the clean-clone phase).
