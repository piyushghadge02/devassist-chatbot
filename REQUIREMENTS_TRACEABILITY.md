# Requirements Traceability — DevAssist SRS v1.0 (LOCAL verification; final audit after clean clone)

| SRS Req | Implementation | Local Test |
|---|---|---|
| Vue 3 + Tailwind dual-pane, sidebar upload/status, chat main (§3.1) | frontend/src/App.vue | build passes; manual dev-server check |
| Session-only chat history (§3.1) | messages ref in App.vue (no persistence) | code review |
| Markdown + syntax highlighting (§3.1) | lib/chat.js marked+highlight.js+DOMPurify | frontend test: renders code/hljs, sanitizes script |
| Programming-only via system prompt (§3.2) | backend/app/prompts.py SYSTEM_PROMPT (verbatim strategy) | test_system_prompt_programming_only |
| RAG .txt/.md/.pdf, <5MB, in-memory (§3.3) | ingestion.py, main.py upload, VectorStore in-memory | upload txt/md/pdf, oversize 413, bad-ext 400 tests |
| Chunk 500 / overlap 50 (§3.3) | chunking.py | test_chunking_srs_500_50 |
| Retrieval top-3 (§3.3/§2.2) | VectorStore.search(top_k=3) | test_vector_store_topk_limit, upload+search test |
| Embeddings all-MiniLM-L6-v2 local (§2.1) | embeddings.py SentenceTransformerEmbedder (auto), hash fallback same 384-dim | health reports backend; hash used locally (see TEST_REPORT environment limitation) |
| FAISS local (§2.1) | vector_store.py IndexFlatIP (numpy fallback if absent) | live health: vector_backend=faiss |
| POST /upload response shape (§4.1) | main.py | upload tests assert status/chunks_processed/filename |
| WebSocket /ws/chat streaming tokens + done (§4.2) | main.py ws_chat, groq_client.stream_chat | websocket tests + live WS check |
| Groq streaming, llama3-70b-8192 default (§2.1) | config GROQ_MODEL, groq AsyncGroq stream=True | offline mode w/o key; live Groq requires user key (not verified locally) |
| Rate limit: disable send (§5.1) | canSend + :disabled in App.vue | frontend canSend tests |
| Rate limit 429 message (§5.1) | prompts.RATE_LIMIT_MESSAGE, WS error frame | constant test; frontend constant test |
| Context <4000 tokens (§5.2) | max_context_chars cap in ws_chat | code review + config test |
| API key only in .env, never frontend (§5.2) | backend .env.example, .gitignore, secret scan | security scan: no key in repo |

Status: LOCAL PASS for all rows except live-Groq inference, which needs the user's own Groq API key.
Final SRS audit is pending clean-clone verification after the user provides a GitHub repository.
