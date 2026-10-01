# Test Report — DevAssist Chatbot

Last updated: 2026-10-01 (Asia/Calcutta)
Environment: Python 3.12.3, Node v24.20.0, npm 10.9.4, this VM + live external APIs.
Verification was performed in the REAL environment (real sentence-transformers model,
real Groq API via local backend/.env). The API key value is never printed in this report.

## 1. Automated test suites

### Backend — pytest
- Designed configuration (offline mock LLM, hash embedder forced by the test module):
  **14 passed**, 1 warning (Starlette/httpx deprecation, pre-existing).
- Same suite run with the live Groq key visible in .env: 13 passed, 1 failed —
  `test_websocket_uses_rag_context` asserts the offline mock's canned phrase
  "uploaded document context". With a real key the app calls real Groq, which answered
  "ZebraDB uses port **9876**." — i.e. the requirement (RAG context retrieved and used)
  holds live; only the mock-specific string assertion cannot match a real model.
  No test was modified. The live behavior is verified directly in §3.

### Frontend — vitest + build
- **13 passed** (2 files): 8 original lib tests (markdown/hljs rendering, XSS sanitization,
  canSend gating ×3, exact SRS rate-limit message, upload validation) + 5 App component
  tests added with the UI redesign (empty state + 4 example prompts, prompt populates input
  only, streamed markdown answer with decorated code block, upload success → "Ready" row,
  upload validation error display).
- `vite build`: **PASS** (pre-existing >500 kB chunk-size warning; unchanged dependency set).

### Dependency fix (2026-10-01, SRS §6 item 2)
`langchain 1.4.3` (with langchain-core 1.6.6) was installed into backend/.venv and added to
`backend/requirements.txt`, completing the SRS install checklist alongside
sentence-transformers and faiss-cpu. pip also moved `websockets` 17.1 → 16.1.1 as a
langchain dependency constraint. Post-install regression: backend pytest **14/14**,
live server health PASS, live WebSocket chat smoke test PASS (24 streaming frames + done,
real Groq). The RAG implementation remains hand-written so chunking/retrieval behavior is
byte-identical to the SRS spec.

## 2. Real embedding model — sentence-transformers/all-MiniLM-L6-v2
- Installed for real: torch 2.14.1+cpu, sentence-transformers 6.1.0 in backend/.venv.
- Direct check: embeddings shape (3, 384), float32, unit norms → PASS (384-dim per SRS stack).
- App-level check: the running app's embedder is the real MiniLM and the store backend is
  FAISS; top-3 semantic retrieval ranked the on-topic chunk #1 → PASS.
- `GET /health` on the real instance reports
  `embedding_backend: "sentence-transformers/all-MiniLM-L6-v2"`, `vector_backend: "faiss"`,
  `groq_configured: true`.

## 3. Live end-to-end (real backend + real Groq, WebSocket)
- Uploads to the live server: guide.txt (2,202 chars) → 5 chunks; notes.md → 3 chunks;
  doc.pdf → 1 chunk; `GET /documents` total 9. Chunk counts match the 500/50 spec exactly,
  and in-process checks confirmed chunk 2 starts at character 450 (500 − 50 overlap).
- Limits: a 5 MB + 1 byte file → `413 {"detail":"File too large. Maximum size is 5MB."}`;
  a .exe upload → `400` unsupported type.
- RAG + streaming: document question → 42 streaming frames + `done`; answer contained
  "9876" and "zebra-py" (ZebraDB is fictional, so grounding can only come from the upload).
  Re-verified after the UI redesign: 37 frames + `done`, grounded answer incl. code fence.
- Programming question (no document) → 393 frames + `done`, code answer with `[::-1]`.
- Non-programming questions (weather, pasta recipe) → politely declined (programming-only) → PASS.
- Empty/whitespace message → error frame "Message must not be empty."
- Context cap: prompt context ≤ `max_context_chars` 12,000 chars (< 4,000 tokens) → PASS.
- Rate limiting: a simulated Groq 429 is mapped to exactly
  "Traffic is high. Please wait 10 seconds before asking again." (A real 429 was not
  deliberately triggered against the live API.)
- Failure handling: a separate instance with an invalid Groq key returned a clean WebSocket
  error frame ("Chat failed: … 401 Invalid API Key") and stayed healthy → PASS.
  Main backend log scan: no errors/tracebacks.

## 4. Groq model finding (important)
Both SRS-named models are **decommissioned by Groq globally** (verified live, 2026-10-01):
`llama3-70b-8192` → 400 decommissioned; `mixtral-8x7b-32768` → 400 decommissioned.
Authentication itself works. This account can access 11 models; the general chat model
chosen and verified live (streaming + non-streaming) is **`openai/gpt-oss-120b`**.
Documented deviation, kept as a local uncommitted change at the user's instruction:
`backend/.env` sets `GROQ_MODEL=openai/gpt-oss-120b`; `backend/app/config.py` default and
`backend/.env.example` / README updated with an explanatory note. No commit was made.

## 5. Frontend UI redesign (2026-10-01) — verified
- Light premium theme (off-white/indigo), brand sidebar with drag-and-drop upload card,
  format/limit chips, upload state machine (idle/uploading+processing/success/error —
  icon + text, not color alone), indexed-document rows with "Ready" badge, empty state with
  4 example prompts (populate input only), typing indicator while generating, code blocks
  with language label + copy button, auto-scroll, responsive layout (collapsible sidebar on
  small screens), aria labels / live regions / focus-visible rings.
- All backend contracts untouched: same endpoints, payloads, status strings, test IDs.
- Component tests (jsdom) mounted the real App with a stub socket/fetch: streaming render,
  code-block decoration, upload success/error all PASS (see §1).
- Live regression after redesign: real upload (5 chunks) + real WS chat (37 frames, done,
  grounded answer) → PASS.
- Limitation: the sandboxed browser runs in a separate VM and cannot reach this VM's
  localhost, and a local headless Chromium could not be downloaded (CDN blocked), so a
  live in-browser console check was not possible here; the jsdom component tests + build
  + live API regression above are the evidence instead. No console errors occurred in tests.

## 6. Security
- The Groq key exists only in `backend/.env` (chmod 600, covered by `.gitignore` rule
  `**/.env` — confirmed via `git check-ignore`); a repo-wide scan found it nowhere else.
- XSS: assistant Markdown is sanitized with DOMPurify (unit-tested).

## 7. Sandbox quirks (not project defects)
- This VM's inherited `NO_PROXY` is malformed and crashes httpx; runs here need
  `NO_PROXY="localhost,127.0.0.1"`. `/tmp` is a 512 MB tmpfs (pip needs a workspace TMPDIR).
  Neither applies on a normal developer machine.
