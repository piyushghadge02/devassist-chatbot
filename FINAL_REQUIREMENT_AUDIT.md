# Final Requirement Audit — DevAssist Chatbot

Audit date: 2026-10-01 (Asia/Calcutta). Scope: local implementation verified against SRS v1.0
in the real environment (real sentence-transformers/all-MiniLM-L6-v2, live Groq API).

## Verdict by requirement

PASS (verified live unless noted):
- Dual-pane Vue 3 + Tailwind UI; session-only history (§3.1)
- Markdown rendering with syntax highlighting, DOMPurify-sanitized (§3.1)
- Programming-only guardrail via system prompt — live refusals confirmed (§3.2)
- Document ingestion .txt/.md/.pdf under 5 MB, in-memory; exact 413/400 behaviors (§3.3)
- Chunking 500 chars / 50 overlap — exact, unit + live (§3.3)
- FAISS retrieval, top-3, real MiniLM embeddings (384-dim) (§2.1, §3.3)
- POST /upload contract; WebSocket /ws/chat token streaming ending in done (§4.1, §4.2)
- Send disabled while generating; exact 429 message on rate limit (§5.1)
- Context capped below 4,000 tokens (§5.2)
- API key confined to gitignored backend/.env; absent from frontend and repo (§5.2)
- UI/UX redesign (2026-10-01): presentation-only; every contract above re-verified after
  the change (13 frontend tests, production build, live upload + streaming regression)
- SRS §6 dependency checklist: langchain (1.4.3), sentence-transformers, faiss-cpu all
  installed (langchain added 2026-10-01; post-install regression 14/14 + live smoke PASS)

DEVIATION (provider-side, documented):
- SRS-named Groq models (`llama3-70b-8192`, `mixtral-8x7b-32768`) are decommissioned by
  Groq — confirmed live with 400 responses. The app runs on `openai/gpt-oss-120b`
  (accessible on the account; streaming verified). The substitution is a local,
  uncommitted config change with explanatory notes in config.py, .env.example and README,
  made only because the specified models no longer exist on the provider.

KNOWN LIMITATIONS:
- A live in-browser console check could not run inside this sandbox (the browser tool runs
  in a separate VM with no route to this VM's localhost; headless Chromium download was
  blocked). jsdom component tests mounted the full app with no errors. A temporary public
  tunnel was provided earlier so the user can test in their own Windows browser.
- Backend suite is 14/14 in its designed offline configuration; with the live key present,
  one assertion tied to the offline mock's canned text fails while the real behavior passes
  live (details in TEST_REPORT.md §1). No test was altered.

## Remaining step (blocked by user instruction, not by the code)
Per this project's definition of done, the final audit completes only after: push to the
user's exact GitHub repository → fresh clean clone → fresh install → clone runs → clone
tests pass → audit updated from the clone. The user has placed all GitHub operations on
hold ("Do not push, commit anything new, or perform any GitHub operation"), and the
Groq-model substitution is intentionally uncommitted. Everything verifiable locally has
been verified; the project is ready to push the moment the hold is lifted.
