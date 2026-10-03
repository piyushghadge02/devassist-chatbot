### Byte 7: Vector store (FAISS with NumPy fallback)

**Builds on:** Byte 6

**In plain terms:**
The `VectorStore` holds embeddings, text chunks, and source filenames in memory. It uses FAISS `IndexFlatIP` (inner product = cosine on normalized vectors) when `faiss-cpu` is installed; otherwise it falls back to a pure NumPy cosine-similarity matrix with the exact same interface. The store keeps a parallel `vectors` list so individual documents can be removed — FAISS doesn't support row deletion, so `remove_source()` rebuilds the index from retained vectors. The backend is exposed via the `.backend` property (`"faiss"` or `"numpy-fallback"`).

**The code:**
```python
# backend/app/vector_store.py
import numpy as np
try:
    import faiss
    _HAS_FAISS = True
except Exception:
    faiss = None
    _HAS_FAISS = False

class VectorStore:
    def __init__(self, dim: int = 384):
        self.dim = dim
        self.chunks: list[str] = []
        self.sources: list[str] = []
        self.vectors: list[np.ndarray] = []
        self._index = faiss.IndexFlatIP(dim) if _HAS_FAISS else None
        self._matrix: np.ndarray | None = None

    @property
    def backend(self): return "faiss" if _HAS_FAISS else "numpy-fallback"

    def add(self, embeddings: np.ndarray, chunks: list[str], source: str = "") -> int:
        emb = np.array(embeddings, dtype="float32")
        if emb.ndim == 1: emb = emb.reshape(1, -1)
        if _HAS_FAISS:
            faiss.normalize_L2(emb); self._index.add(emb)
        else:
            norms = np.linalg.norm(emb, axis=1, keepdims=True); norms[norms == 0] = 1
            emb = emb / norms
            self._matrix = emb if self._matrix is None else np.vstack([self._matrix, emb])
        self.chunks.extend(chunks); self.sources.extend([source] * len(chunks))
        self.vectors.extend(emb[i] for i in range(emb.shape[0]))
        return len(chunks)

    def search(self, query_embedding: np.ndarray, top_k: int = 3) -> list[str]:
        if len(self.chunks) == 0: return []
        k = min(top_k, len(self.chunks))
        q = np.array(query_embedding, dtype="float32")
        if q.ndim == 1: q = q.reshape(1, -1)
        if _HAS_FAISS:
            faiss.normalize_L2(q); _, idx = self._index.search(q, k); indices = idx[0].tolist()
        else:
            n = np.linalg.norm(q); qn = q / n if n else q
            scores = (self._matrix @ qn.T).ravel(); indices = np.argsort(-scores)[:k].tolist()
        return [self.chunks[i] for i in indices if 0 <= i < len(self.chunks)]

    def remove_source(self, source: str) -> int:
        keep = [i for i, s in enumerate(self.sources) if s != source]
        removed = len(self.sources) - len(keep)
        if removed == 0: return 0
        if _HAS_FAISS:
            self._index = faiss.IndexFlatIP(self.dim)
            if keep:
                self._index.add(np.array([self.vectors[i] for i in keep], dtype="float32"))
        elif keep:
            self._matrix = np.vstack([self._matrix[i] for i in keep])
        else:
            self._matrix = None
        self.chunks = [self.chunks[i] for i in keep]
        self.sources = [self.sources[i] for i in keep]
        self.vectors = [self.vectors[i] for i in keep]
        return removed
```

---

### Byte 8: RAG retrieval and context capping

**Builds on:** Byte 7

**In plain terms:**
When a WebSocket message arrives, the handler embeds the user question, calls `store.search(q, top_k=3)` to get up to 3 relevant chunks, then enforces SRS §5.2 by truncating the combined context to `max_context_chars` (12000 chars ≈ 4000 tokens). Chunks are added in retrieval order until the cap is reached. The capped context is then injected into the system prompt. If the store is empty, no context is added and the bare guardrail prompt is used.

**The code:**
```python
# backend/app/main.py — ws_chat handler (excerpt)
@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = await ws.receive_json()
            message = (payload or {}).get("message", "").strip()
            if not message:
                await ws.send_json({"status": "error", "error": "Message must not be empty."}); continue

            context: list[str] = []
            if len(store) > 0:
                q = embedder().encode([message])
                context = store.search(q, top_k=settings.top_k)
                # SRS 5.2 keep context < 4000 tokens (~ chars cap)
                joined, total = [], 0
                for c in context:
                    if total + len(c) > settings.max_context_chars: break
                    joined.append(c); total += len(c)
                context = joined

            messages = build_prompt(message, context)
            ...
```

---

### Byte 9: System prompt and RAG prompt building

**Builds on:** Byte 8

**In plain terms:**
The system prompt enforces the programming-only guardrail (SRS §3.2). `build_prompt()` takes the user message and retrieved context chunks. If context exists, it joins chunks with `\n\n---\n\n` separators and appends them to the system prompt under a "Use the following retrieved document context if relevant:" header. The function returns a two-message list: `[{"role": "system", "content": ...}, {"role": "user", "content": user_message}]`. This exact structure is what the Groq client streams.

**The code:**
```python
# backend/app/prompts.py
SYSTEM_PROMPT = (
    "You are a helpful coding assistant. You strictly answer questions related to "
    "software engineering, algorithms, system design, and code. If a user asks about "
    "general topics (weather, news, cooking, casual chat), politely decline and state "
    "that you are designed only for programming assistance."
)
RATE_LIMIT_MESSAGE = "Traffic is high. Please wait 10 seconds before asking again."

def build_prompt(user_message: str, context_chunks: list[str]) -> list[dict]:
    system = SYSTEM_PROMPT
    if context_chunks:
        context = "\n\n---\n\n".join(context_chunks)
        system = f"{SYSTEM_PROMPT}\n\nUse the following retrieved document context if relevant:\n\n{context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user_message}]
```

---

### Byte 10: Groq streaming client with offline fallback

**Builds on:** Byte 9

**In plain terms:**
`stream_chat()` is an async generator that yields tokens. If no `GROQ_API_KEY` is set, it runs in offline mode: it yields a canned response mentioning the user's question and whether document context was present — this makes the full upload→retrieve→stream flow testable without credentials. With a key, it uses `AsyncGroq` to create a streaming chat completion and yields each `delta.content` token. Rate-limit errors (HTTP 429 or `RateLimitError`) are caught and re-raised as a custom `RateLimitError_` with the standardized message.

**The code:**
```python
# backend/app/groq_client.py
from .prompts import RATE_LIMIT_MESSAGE

class RateLimitError_(Exception): pass

def _is_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "ratelimit" in name or getattr(exc, "status_code", None) == 429 or "429" in str(exc)

async def stream_chat(messages: list[dict], api_key: str, model: str):
    """Yield tokens. Without a Groq key, yields a deterministic offline response."""
    if not api_key:
        user = messages[-1]["content"] if messages else ""
        has_context = len(messages) > 0 and "retrieved document context" in messages[0]["content"]
        prefix = "[Offline mode: set GROQ_API_KEY for live Groq answers] "
        text = (f"{prefix}This is a programming-assistance response to: {user[:200]}. "
                + ("I used your uploaded document context to ground this answer. " if has_context else "")
                + "```python\n# example\nprint('hello from DevAssist')\n```")
        for word in text.split(" "):
            yield word + " "
        return
    try:
        from groq import AsyncGroq, RateLimitError
    except Exception:
        from groq import AsyncGroq
        RateLimitError = ()
    client = AsyncGroq(api_key=api_key)
    try:
        stream = await client.chat.completions.create(model=model, messages=messages, stream=True)
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except Exception:
                delta = None
            if delta:
                yield delta
    except Exception as exc:
        if _is_rate_limit(exc) or (RateLimitError and isinstance(exc, RateLimitError)):
            raise RateLimitError_(RATE_LIMIT_MESSAGE) from exc
        raise
```

---

### Byte 11: WebSocket chat handler

**Builds on:** Byte 10

**In plain terms:**
The `/ws/chat` endpoint accepts a WebSocket, then loops: receive JSON `{"message": "..."}`, validate non-empty, retrieve context, build prompt, stream tokens via `stream_chat()`, send each token as `{"token": "...", "status": "streaming"}`, finally send `{"status": "done"}`. Errors (empty message, rate limit, other exceptions) send `{"status": "error", "error": "..."}`. The handler catches `WebSocketDisconnect` silently. Rate-limit errors surface the exact SRS message to the user.

**The code:**
```python
# backend/app/main.py — ws_chat handler (excerpt)
@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = await ws.receive_json()
            message = (payload or {}).get("message", "").strip()
            if not message:
                await ws.send_json({"status": "error", "error": "Message must not be empty."}); continue

            context: list[str] = []
            if len(store) > 0:
                q = embedder().encode([message])
                context = store.search(q, top_k=settings.top_k)
                joined, total = [], 0
                for c in context:
                    if total + len(c) > settings.max_context_chars: break
                    joined.append(c); total += len(c)
                context = joined

            messages = build_prompt(message, context)
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
```

---

### Byte 12: Frontend architecture (Vue 3 single-component SPA)

**Builds on:** Byte 11

**In plain terms:**
The frontend is a single Vue 3 component (`App.vue`) using Composition API with `<script setup>`. It manages all state locally: messages array, input text, generating flag, uploaded documents list, upload status, WebSocket connection, and sidebar visibility. The layout is a two-panel design: a fixed left sidebar (document explorer, upload, workspace meta) and a right chat workspace (messages + composer). In production, the built bundle is served by FastAPI; in dev, Vite proxies to the backend. No Vuex/Pinia — reactive refs are sufficient for this scope.

**The code:**
```javascript
// frontend/src/App.vue — key state and layout (excerpt)
<script setup>
import { ref, shallowRef, computed, watch, nextTick, onMounted } from 'vue'
import { renderMarkdown, canSend, validateUpload, createChatSocket, RATE_LIMIT_MESSAGE } from './lib/chat.js'

const DEV = import.meta.env.DEV
const envAPI = import.meta.env.VITE_API_BASE
const API = envAPI || (DEV ? 'http://localhost:8000' : '')
const WS_URL = import.meta.env.VITE_WS_URL || `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/chat`

/* Session state (no persistence — SRS 3.1) */
const messages = ref([])
const input = ref('')
const isGenerating = ref(false)
const uploaded = ref([])
const uploadStatus = ref('')
const uploadState = ref('idle')
const dragOver = ref(false)
const sidebarOpen = ref(false)
const socket = shallowRef(null)  // shallowRef: raw WS object, not a proxy
const pendingPrompt = ref('')
const socketState = ref('idle')
</script>

<template>
  <div class="app-atmosphere flex h-[100dvh] w-full overflow-hidden">
    <!-- Mobile drawer scrim -->
    <transition> <div v-if="sidebarOpen" class="fixed inset-0 z-30 bg-canvas/80 md:hidden" @click="sidebarOpen = false" /> </transition>

    <!-- Sidebar / explorer -->
    <aside class="fixed inset-y-0 left-0 z-40 w-[282px] md:static md:w-[292px]" :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full'">
      <!-- Brand, New Chat, Upload dropzone, Document list, Workspace meta -->
    </aside>

    <!-- Chat workspace -->
    <main class="flex min-h-0 min-w-0 flex-1 flex-col">
      <header>...</header>
      <div ref="chatScroll" class="slim-scroll min-h-0 flex-1 overflow-y-auto">
        <!-- Messages with markdown rendering -->
      </div>
      <div class="shrink-0 border-t ..."> <!-- Composer with textarea + send button --> </div>
    </main>
  </div>
</template>
```