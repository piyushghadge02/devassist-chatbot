### Byte 13: Frontend reactive state and derived values

**Builds on:** Byte 12

**In plain terms:**
All UI state lives in Vue `ref`/`shallowRef` variables: `messages` (chat history), `input` (composer text), `isGenerating` (locks the send button), `uploaded` (indexed documents with chunk counts), `uploadState`/`uploadStatus` (feedback for upload/remove), `socket` (WebSocket instance — `shallowRef` keeps the raw object so identity checks work), `socketState` (derived from `readyState`), and `sidebarOpen` (mobile drawer). Computed properties like `fileCount`, `totalChunks`, `uploadStatusClasses`, and `connectionMeta` derive display values from state reactively.

**The code:**
```javascript
// frontend/src/App.vue — state and computed (excerpt)
const messages = ref([])           // session only — refresh clears history
const input = ref('')
const isGenerating = ref(false)
const uploaded = ref([])
const uploadStatus = ref('')
const uploadState = ref('idle')    // idle | uploading | success | error
const dragOver = ref(false)
const sidebarOpen = ref(false)
const socket = shallowRef(null)    // raw WS object; deep ref would give a proxy
const pendingPrompt = ref('')
const socketState = ref('idle')    // idle | connecting | online | offline

const fileCount = computed(() => uploaded.value.length)
const totalChunks = computed(() => uploaded.value.reduce((n, f) => n + (f.chunks_processed || 0), 0))

const uploadStatusClasses = computed(() => ({
  uploading: 'border-brand/40 bg-brand-wash text-brand-soft',
  success: 'border-ok/30 bg-ok/10 text-ok',
  error: 'border-danger/40 bg-danger/10 text-danger',
  idle: 'border-edge bg-raised text-ink-3'
}[uploadState.value]))

const connectionMeta = computed(() => ({
  idle: { label: 'Not connected', dot: 'bg-ink-4', text: 'text-ink-4' },
  connecting: { label: 'Connecting', dot: 'bg-signal animate-pulse', text: 'text-signal-soft' },
  online: { label: 'Connected', dot: 'bg-ok', text: 'text-ok' },
  offline: { label: 'Disconnected', dot: 'bg-danger', text: 'text-danger' }
}[socketState.value]))
```

---

### Byte 14: WebSocket lifecycle and error recovery

**Builds on:** Byte 13

**In plain terms:**
`ensureSocket()` creates a new WebSocket if none exists or the current one is closed. It attaches handlers for `onToken` (appends to the last assistant message), `onDone` (clears `isGenerating`), and `onError` (shows error in the chat). Native `open`/`close`/`error` events update `socketState`. `handleSocketDrop()` runs when the socket closes unexpectedly mid-generation: if no tokens arrived yet, it removes the empty assistant bubble and restores the user's draft into the composer; if tokens already arrived, it keeps the partial answer and just unlocks the composer. This prevents the "stuck generating" state.

**The code:**
```javascript
// frontend/src/App.vue — WebSocket management (excerpt)
function syncSocketState(ws) {
  if (!ws) return
  if (ws.readyState === 0) socketState.value = 'connecting'
  else if (ws.readyState === 1) socketState.value = 'online'
  else socketState.value = 'offline'
}

function ensureSocket() {
  if (socket.value && socket.value.readyState <= 1) { syncSocketState(socket.value); return socket.value }
  socketState.value = 'connecting'
  const ws = createChatSocket(WS_URL, {
    onToken(token) {
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') last.content += token
    },
    onDone() { isGenerating.value = false; pendingPrompt.value = '' },
    onError(err) {
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant' && !last.content) last.content = err
      else messages.value.push({ role: 'assistant', content: err })
      isGenerating.value = false
      pendingPrompt.value = ''
    }
  })
  ws.addEventListener?.('open', () => syncSocketState(ws))
  ws.addEventListener?.('close', () => handleSocketDrop(ws))
  ws.addEventListener?.('error', () => handleSocketDrop(ws))
  socket.value = ws
  syncSocketState(ws)
  return ws
}

function handleSocketDrop(ws) {
  if (socket.value !== ws) return
  socketState.value = 'offline'
  if (!isGenerating.value) return
  isGenerating.value = false
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant' && !last.content) {
    messages.value.pop()
    if (pendingPrompt.value) input.value = pendingPrompt.value
    pendingPrompt.value = ''
    nextTick(() => inputEl.value?.focus())
  }
}
```

---

### Byte 15: Document upload, listing, and removal UI

**Builds on:** Byte 14

**In plain terms:**
The sidebar dropzone accepts drag-drop or file-input for `.txt/.md/.pdf` (<5MB). Client-side `validateUpload()` mirrors backend rules. On submit, `handleFile()` POSTs to `/upload` with `FormData`, shows uploading/success/error states, and on success pushes the response (`{filename, chunks_processed}`) to `uploaded[]`. Each document row shows a file-type badge, name, chunk count, and a Remove button. `removeDocument()` calls `DELETE /documents/{filename}` (percent-encoded), and only on 200 removes the row from `uploaded[]`. The "Removing…" state disables other removals and the composer.

**The code:**
```javascript
// frontend/src/App.vue — upload and removal (excerpt)
async function handleFile(file) {
  const err = validateUpload(file)
  if (err) { uploadState.value = 'error'; uploadStatus.value = err; return }
  uploadState.value = 'uploading'
  uploadStatus.value = `Uploading ${file.name}…`
  const form = new FormData(); form.append('file', file)
  try {
    const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
    const body = await res.json()
    if (!res.ok) throw new Error(body.detail || 'Upload failed')
    uploaded.value.push(body)
    uploadState.value = 'success'
    uploadStatus.value = `Indexed ${body.filename}: ${body.chunks_processed} chunks`
  } catch (e) {
    uploadState.value = 'error'
    uploadStatus.value = `${file.name}: ${e.message}`
  }
}

const removing = ref('')
async function removeDocument(entry) {
  const name = entry.filename
  if (removing.value || isGenerating.value) return
  removing.value = name
  uploadState.value = 'uploading'
  uploadStatus.value = `Removing ${name}…`
  try {
    const res = await fetch(`${API}/documents/${encodeURIComponent(name)}`, { method: 'DELETE' })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(body.detail || 'Could not remove document')
    uploaded.value = uploaded.value.filter(f => f.filename !== name)
    uploadState.value = 'success'
    uploadStatus.value = `Removed ${name} (${body.chunks_removed} chunks). ${fileCount.value} file${fileCount.value === 1 ? '' : 's'} · ${totalChunks.value} chunks`
  } catch (e) {
    uploadState.value = 'error'
    uploadStatus.value = `${name}: ${e.message}`
  } finally {
    removing.value = ''
  }
}
```

---

### Byte 16: Markdown rendering with syntax highlighting and sanitization

**Builds on:** Byte 15

**In plain terms:**
`lib/chat.js` configures `marked` with `marked-highlight` using `highlight.js`. Code blocks get language-aware highlighting (`hljs.highlight` for known languages, `highlightAuto` otherwise). The output is sanitized by `DOMPurify` before being set as `v-html`. A custom directive `v-enhance` runs `decorateCodeBlocks()` on mount/update: it wraps each `<pre>` in a `.code-block` div, adds a header with the language label and a Copy button (uses `navigator.clipboard`). The CSS (in `style.css`) styles code blocks with `github-dark-dimmed` theme, horizontal scrolling, and the copy button.

**The code:**
```javascript
// frontend/src/lib/chat.js
import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

const marked = new Marked(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value
    return hljs.highlightAuto(code).value
  }
}))
export function renderMarkdown(text = '') {
  return DOMPurify.sanitize(marked.parse(text))
}
```

```javascript
// frontend/src/App.vue — v-enhance directive (excerpt)
const copySvg = '<svg ...>...</svg>'
function decorateCodeBlocks(el) {
  el.querySelectorAll('pre').forEach((pre) => {
    if (pre.parentElement?.classList.contains('code-block')) return
    const code = pre.querySelector('code')
    const match = code?.className.match(/language-([\w-]+)/)
    const wrap = document.createElement('div'); wrap.className = 'code-block'
    const header = document.createElement('div'); header.className = 'code-block-header'
    const label = document.createElement('span'); label.className = 'code-block-lang'
    label.textContent = match ? match[1] : 'code'
    const btn = document.createElement('button')
    btn.type = 'button'; btn.className = 'code-copy-btn'
    btn.setAttribute('aria-label', 'Copy code to clipboard')
    btn.innerHTML = `${copySvg}<span>Copy</span>`
    btn.addEventListener('click', async () => {
      const text = code?.innerText ?? pre.innerText
      let ok = false
      try { await navigator.clipboard.writeText(text); ok = true } catch { ok = false }
      btn.querySelector('span').textContent = ok ? 'Copied' : 'Copy failed'
      setTimeout(() => { const s = btn.querySelector('span'); if (s) s.textContent = 'Copy' }, 1600)
    })
    header.append(label, btn)
    pre.replaceWith(wrap); wrap.append(header, pre)
  })
}
const vEnhance = { mounted: decorateCodeBlocks, updated: decorateCodeBlocks }
```

```html
<!-- In template: -->
<div v-if="m.content" class="markdown-body" v-enhance v-html="renderMarkdown(m.content)"></div>
```

---

### Byte 17: Static frontend serving and SPA fallback

**Builds on:** Byte 16

**In plain terms:**
FastAPI serves the built Vue bundle from `frontend/dist/` in production. Routes are ordered so API endpoints (`/health`, `/documents`, `/upload`, `/ws/chat`, `/docs`, `/openapi.json`) are registered first — FastAPI's first-match-wins ensures they're never intercepted. `/assets/` is mounted as static files. `/` serves `index.html` (503 if not built). The catch-all `/{full_path:path}` serves real files from `dist/` (with path-traversal protection via `_resolve_in_dist()`) or falls back to `index.html` for client-side routing. Reserved prefixes (`health`, `documents`, `upload`, `ws`, `docs`, `openapi.json`, `redoc`, `api-info`) always 404.

**The code:**
```python
# backend/app/main.py — static serving (excerpt)
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# ... API routes registered first ...

_RESERVED = ("health", "documents", "upload", "ws", "docs", "openapi.json", "redoc", "api-info")

def _resolve_in_dist(rel_path: str) -> Path | None:
    if not rel_path: return None
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
        return JSONResponse(status_code=503, content={
            "error": "Frontend not built",
            "hint": "run `npm run build` in frontend/, then reload",
            "api_docs": "/docs", "health": "/health"
        })
    return FileResponse(index)

@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.split("/")[0] in _RESERVED:
        raise HTTPException(status_code=404, detail="Not Found")
    if FRONTEND_DIST.is_dir():
        target = _resolve_in_dist(full_path)
        if target is not None and target.is_file():
            return FileResponse(target)
    return serve_index()
```

---

### Byte 18: Testing strategy (backend pytest + frontend vitest)

**Builds on:** Byte 17

**In plain terms:**
Backend tests use `fastapi.testclient.TestClient` with `EMBEDDING_BACKEND=hash` (forces deterministic offline embedder, no downloads). `setup_function` clears the vector store before each test. Tests cover: health, chunking logic, system prompt guardrails, upload (txt/md/pdf), validation (bad type, oversize, empty), single-document deletion (removes only its chunks, preserves others, handles URL-encoded filenames), WebSocket streaming (offline mode), RAG context injection (monkeypatches `stream_chat` to capture the built prompt and assert retrieved chunks appear), context char cap enforcement, and rate-limit message constant. Frontend tests use `vitest` on pure utility functions: markdown rendering (code blocks, XSS sanitization), send gating (rate-limit prevention), and upload validation.

**The code:**
```python
# backend/tests/test_api.py — key tests (excerpt)
import io, os, sys
os.environ["EMBEDDING_BACKEND"] = "hash"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app.config as cfg
cfg.settings.embedding_backend = "hash"
from fastapi.testclient import TestClient
from app.main import app, store
from app.chunking import chunk_text
from app.prompts import SYSTEM_PROMPT, build_prompt
from app.vector_store import VectorStore
from app.embeddings import HashEmbedder

client = TestClient(app)

def setup_function(): store.clear()

def test_chunking_srs_500_50():
    text = "a" * 1200
    chunks = chunk_text(text, 500, 50)
    assert chunks[0] == text[:500]
    assert chunks[1] == text[450:950]   # overlap = 50
    assert len(chunks) == 3

def test_system_prompt_programming_only():
    assert "strictly answer questions related to software engineering" in SYSTEM_PROMPT
    msgs = build_prompt("hi", ["ctx chunk"])
    assert "ctx chunk" in msgs[0]["content"]

def test_delete_single_document_removes_only_its_chunks():
    a = client.post("/upload", files={"file": ("alpha.txt", io.BytesIO(b"alpha doc "*40), "text/plain")})
    b = client.post("/upload", files={"file": ("beta.md", io.BytesIO(b"# Beta\n\nbeta doc "*40), "text/markdown")})
    n_a, n_b = a.json()["chunks_processed"], b.json()["chunks_processed"]
    assert len(store) == n_a + n_b
    r = client.delete("/documents/beta.md")
    assert r.status_code == 200 and r.json()["chunks_removed"] == n_b
    assert len(store) == n_a
    assert "beta.md" not in store.sources

def test_websocket_uses_rag_context(monkeypatch):
    data = ("ZebraDB is a fictional database whose port is 9876... " * 10).encode()
    client.post("/upload", files={"file": ("z.txt", io.BytesIO(data), "text/plain")})
    captured = {}
    async def fake_stream_chat(messages, api_key, model):
        captured["messages"] = messages
        yield "ZebraDB uses port **9876**."
    monkeypatch.setattr("app.main.stream_chat", fake_stream_chat)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "What port does ZebraDB use?"})
        # ... receive done ...
    system_prompt = captured["messages"][0]["content"]
    assert "ZebraDB" in system_prompt and "9876" in system_prompt
    assert "strictly answer questions related to software engineering" in system_prompt
```

```javascript
// frontend/tests/chat.test.js
import { describe, it, expect } from 'vitest'
import { renderMarkdown, canSend, validateUpload, RATE_LIMIT_MESSAGE } from '../src/lib/chat.js'

describe('markdown rendering', () => {
  it('renders code blocks with highlighting markup', () => {
    const html = renderMarkdown('```python\nprint(1)\n```')
    expect(html).toContain('<code')
    expect(html).toContain('hljs')
  })
  it('sanitizes script tags', () => {
    expect(renderMarkdown('<script>alert(1)</script>hello')).not.toContain('<script>')
  })
})
describe('send gating (rate-limit prevention, SRS 5.1)', () => {
  it('disables while generating', () => { expect(canSend('hi', true)).toBe(false) })
  it('allows when idle with text', () => { expect(canSend('hi', false)).toBe(true) })
  it('blocks empty', () => { expect(canSend('   ', false)).toBe(false) })
  it('rate limit message matches SRS', () => {
    expect(RATE_LIMIT_MESSAGE).toBe('Traffic is high. Please wait 10 seconds before asking again.')
  })
})
describe('upload validation', () => {
  it('accepts txt/md/pdf under 5MB', () => {
    expect(validateUpload({ name: 'a.txt', size: 10 })).toBeNull()
    expect(validateUpload({ name: 'a.md', size: 10 })).toBeNull()
    expect(validateUpload({ name: 'a.pdf', size: 10 })).toBeNull()
  })
  it('rejects bad type and oversize', () => {
    expect(validateUpload({ name: 'a.exe', size: 10 })).toContain('Unsupported')
    expect(validateUpload({ name: 'a.txt', size: 5 * 1024 * 1024 + 1 })).toContain('5MB')
  })
})
```