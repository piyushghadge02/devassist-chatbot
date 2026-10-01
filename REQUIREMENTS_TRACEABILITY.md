# Requirements Traceability — DevAssist SRS v1.0

Verified 2026-10-01 in the real environment (real all-MiniLM-L6-v2 embeddings, live Groq API).
Evidence detail: see TEST_REPORT.md.

| SRS Req | Implementation | Verification | Status |
|---|---|---|---|
| Vue 3 + Tailwind dual-pane, sidebar upload/status, chat main (§3.1) | frontend/src/App.vue | build PASS; component tests mount the layout; live dev server serves the app | PASS |
| Session-only chat history (§3.1) | messages ref in App.vue (no persistence) | code review (unchanged by redesign) | PASS |
| Markdown + syntax highlighting (§3.1) | lib/chat.js marked + highlight.js + DOMPurify | unit tests (code/hljs markup, script sanitized); live streamed answer rendered with decorated code block | PASS |
| Programming-only via system prompt (§3.2) | backend/app/prompts.py SYSTEM_PROMPT | unit test; live: weather + recipe questions politely declined | PASS |
| RAG .txt/.md/.pdf, <5MB, in-memory (§3.3) | ingestion.py, main.py upload, in-memory VectorStore | live uploads txt/md/pdf; 5MB+1 → 413 with exact SRS message; .exe → 400 | PASS |
| Chunk 500 / overlap 50 (§3.3) | chunking.py | unit test exact slices; live chunk counts match (2202 chars → 5 chunks; chunk 2 starts at char 450) | PASS |
| Retrieval top-3 (§3.3/§2.2) | VectorStore.search(top_k=3) | unit test top-k limit; live semantic ranking with real MiniLM put the on-topic chunk #1 | PASS |
| Embeddings all-MiniLM-L6-v2 local (§2.1) | embeddings.py SentenceTransformerEmbedder | real model installed and run: (3, 384) float32 unit-norm embeddings; /health reports the model name | PASS |
| FAISS local (§2.1) | vector_store.py IndexFlatIP | /health reports vector_backend=faiss on the real instance | PASS |
| POST /upload response shape (§4.1) | main.py | live + unit tests assert status/chunks_processed/filename | PASS |
| WebSocket /ws/chat streaming tokens + done (§4.2) | main.py ws_chat, groq_client.stream_chat | live: 42 / 393 / 37 streaming frames ending in done across sessions | PASS |
| Groq streaming (§2.1) | config GROQ_MODEL, groq AsyncGroq stream=True | live streaming verified end-to-end | PASS (see model note) |
| Groq model llama3-70b-8192 default (§2.1) | config GROQ_MODEL | **Model decommissioned by Groq (live 400), as is mixtral-8x7b-32768.** Substituted `openai/gpt-oss-120b` (verified live on this account); documented in config/.env.example/README | DEVIATION — provider-side, documented |
| Rate limit: disable send (§5.1) | canSend + :disabled in App.vue | unit tests ×3; component test asserts disabled state | PASS |
| Rate limit 429 message (§5.1) | prompts.RATE_LIMIT_MESSAGE, WS error frame | simulated Groq 429 maps to the exact SRS sentence; constant unit-tested both sides | PASS |
| Context <4000 tokens (§5.2) | max_context_chars cap (12,000) in ws_chat | in-process check: context within cap | PASS |
| API key only in .env, never frontend (§5.2) | backend/.env (gitignored, chmod 600), secret scan | git check-ignore confirms ignore rule; repo scan: key only in backend/.env | PASS |
| UI/UX redesign (user request, 2026-10-01) | App.vue / style.css / tailwind.config / index.html only | 5 new component tests PASS; production build PASS; live upload+chat regression PASS; no backend/API changes (git diff confirms frontend-only) | PASS |
| Implementation checklist (§6 item 2): langchain, sentence-transformers, faiss-cpu installed | backend/requirements.txt | verified in the venv 2026-10-01: langchain 1.4.3, sentence-transformers 6.1.0, faiss-cpu present. The RAG pipeline itself is hand-implemented so chunking/retrieval match the SRS exactly; langchain is installed per the checklist. Post-install regression: pytest 14/14 + live WS smoke test PASS | PASS |

Notes:
- Backend pytest: 14/14 in its designed offline configuration. With the live key in .env,
  one mock-phrase assertion cannot match the real model (13/14); the underlying RAG behavior
  was verified live instead. No tests were removed or weakened.
- Clean-clone audit remains pending by definition (see FINAL_REQUIREMENT_AUDIT.md) and is
  blocked only by the user's hold on all GitHub operations.
