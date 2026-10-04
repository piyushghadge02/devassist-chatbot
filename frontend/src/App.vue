<script setup>
import { ref, shallowRef, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { renderMarkdown, canSend, validateUpload, createChatSocket, RATE_LIMIT_MESSAGE } from './lib/chat.js'

/* In development the Vite dev server (5173) talks to the API on 8000, so an absolute
   base is required. In the production build FastAPI serves this same bundle on the
   same origin, so requests stay relative and the WebSocket follows the current host
   (ws:// for HTTP, wss:// for HTTPS/ngrok). The host is never hardcoded. */
const DEV = import.meta.env.DEV
const envAPI = import.meta.env.VITE_API_BASE
const API = envAPI || (DEV ? 'http://localhost:8000' : '')

function resolveWsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}/ws/chat`
}
const WS_URL = resolveWsUrl()

/* ---------------- Session state (no persistence — SRS 3.1) ---------------- */
const messages = ref([]) // session only — refresh clears history
const input = ref('')
const isGenerating = ref(false)
const uploaded = ref([])
const uploadStatus = ref('')
const uploadState = ref('idle') // idle | uploading | success | error (UI state only)
const dragOver = ref(false)
const sidebarOpen = ref(false)
const selectedDocument = ref('') // currently selected document for scoped chat
// shallowRef: a WebSocket must stay the raw object so `socket.value === ws` identity
// checks in the drop handler work (a deep `ref` would hand back a reactive proxy).
const socket = shallowRef(null)
const pendingPrompt = ref('')
const socketState = ref('idle') // idle | connecting | online | offline (derived from real readyState)
const inputEl = ref(null)
const chatScroll = ref(null)

const suggestions = [
  'Explain this architecture',
  'Analyze the uploaded documents',
  'Find requirements in the documents',
  'Suggest an implementation approach'
]

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

function fileKind(name = '') {
  const ext = String(name).toLowerCase().slice(String(name).toLowerCase().lastIndexOf('.'))
  if (ext === '.pdf') return { tag: 'PDF', cls: 'text-danger bg-danger/10 border-danger/25' }
  if (ext === '.md') return { tag: 'MD', cls: 'text-brand-soft bg-brand-wash border-brand/25' }
  return { tag: 'TXT', cls: 'text-signal-soft bg-signal-wash border-signal/25' }
}

/* ---------------- WebSocket (unchanged protocol) ---------------- */
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

// A dropped socket must never leave the composer locked on "Generating". If the turn
// produced no tokens yet, drop the empty bubble and restore the draft so it can be resent;
// if tokens already arrived, keep the partial answer and just release the lock.
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

/* ---------------- Upload (unchanged flow: validate -> POST /upload) ---------------- */
async function handleFile(file) {
  if (!file) return
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
    // Auto-select the newly uploaded document for scoped chat
    selectedDocument.value = body.filename
    uploadState.value = 'success'
    uploadStatus.value = `Indexed ${body.filename}: ${body.chunks_processed} chunks`
  } catch (e) {
    uploadState.value = 'error'
    // Keep the filename in the failure copy so the error is attributable.
    uploadStatus.value = `${file.name}: ${e.message}`
  }
}

/* ---------------- Document removal ----------------
   The backend exposes DELETE /documents/{filename}, which drops that document's
   chunks from the in-memory vector store (index rebuilt from retained vectors).
   Rows are removed only after the server confirms, so the list never lies. */
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
    // If the removed document was selected, clear selection or pick another
    if (selectedDocument.value === name) {
      selectedDocument.value = uploaded.value.length > 0 ? uploaded.value[0].filename : ''
    }
    uploadState.value = 'success'
    uploadStatus.value = `Removed ${name} (${body.chunks_removed} chunks). ${fileCount.value} file${fileCount.value === 1 ? '' : 's'} · ${totalChunks.value} chunks`
  } catch (e) {
    uploadState.value = 'error'
    uploadStatus.value = `${name}: ${e.message}`
  } finally {
    removing.value = ''
  }
}
function onUpload(event) {
  handleFile(event.target.files?.[0])
  event.target.value = ''
}
function onDrop(event) {
  dragOver.value = false
  handleFile(event.dataTransfer?.files?.[0])
}

/* ---------------- Document selection ---------------- */
function selectDocument(filename) {
  selectedDocument.value = selectedDocument.value === filename ? '' : filename
}

/* ---------------- Chat ---------------- */
function pickSuggestion(text) {
  input.value = text
  nextTick(() => inputEl.value?.focus())
}
function newChat() {
  messages.value = []
  isGenerating.value = false
  pendingPrompt.value = ''
  nextTick(() => inputEl.value?.focus())
}
function send() {
  if (!canSend(input.value, isGenerating.value)) return
  // If documents exist but the selected one is no longer in the list, clear selection
  if (selectedDocument.value && !uploaded.value.some(f => f.filename === selectedDocument.value)) {
    selectedDocument.value = ''
  }
  const text = input.value.trim(); input.value = ''
  pendingPrompt.value = text
  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '' })
  isGenerating.value = true
  const ws = ensureSocket()
  // Only send document_id if a valid document is selected
  const docId = (selectedDocument.value && uploaded.value.some(f => f.filename === selectedDocument.value))
    ? selectedDocument.value
    : ''
  const payload = JSON.stringify({ message: text, document_id: docId })
  if (ws.readyState === 1) ws.send(payload)
  else ws.addEventListener('open', () => ws.send(payload), { once: true })
}

// Keep the newest message in view while streaming.
watch(messages, () => nextTick(() => {
  const el = chatScroll.value
  if (el) el.scrollTop = el.scrollHeight
}), { deep: true })

// On wide screens the sidebar is always docked open.
let mq = null
onMounted(() => {
  if (typeof window !== 'undefined' && window.matchMedia) {
    mq = window.matchMedia('(min-width: 768px)')
    if (mq.matches) sidebarOpen.value = true
    mq.addEventListener?.('change', (e) => { if (e.matches) sidebarOpen.value = true })
  }
})
onBeforeUnmount(() => { /* listeners are per-component; nothing global to release */ })

/* ---------- Code block decoration (UI only) ---------- */
const copySvg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
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
</script>

<template>
  <div class="app-atmosphere flex h-[100dvh] w-full overflow-hidden text-ink-2">
    <!-- ==================== Mobile drawer scrim ==================== -->
    <transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0" leave-to-class="opacity-0">
      <div v-if="sidebarOpen" class="fixed inset-0 z-30 bg-canvas/80 backdrop-blur-[2px] md:hidden"
        aria-hidden="true" @click="sidebarOpen = false" />
    </transition>

    <!-- ==================== Sidebar / explorer ==================== -->
    <aside
      class="fixed inset-y-0 left-0 z-40 flex w-[282px] shrink-0 flex-col border-r border-edge bg-sidebar
             transition-transform duration-200 ease-out
             md:static md:w-[292px] md:translate-x-0"
      :class="sidebarOpen ? 'translate-x-0 shadow-lift' : '-translate-x-full'"
      aria-label="Document workspace">
      <!-- Brand. h-app-header + items-center keeps this row the exact same height as the
           chat header, so both bottom borders land on one continuous line. -->
      <div class="flex h-app-header shrink-0 items-center gap-2.5 border-b border-edge px-4">
        <div class="grid h-8 w-8 shrink-0 place-items-center rounded-control border border-brand/30 bg-brand-wash text-brand-soft" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 7-5 5 5 5M16 7l5 5-5 5"/><path d="M13.5 4.5 10.5 19.5"/></svg>
        </div>
        <div class="min-w-0 flex-1">
          <h1 class="font-mono text-[14px] font-semibold leading-tight tracking-tight text-ink">DevAssist</h1>
          <p class="truncate text-[11px] leading-tight text-ink-4">AI Developer Assistant</p>
        </div>
        <button type="button"
          class="rounded-control p-1.5 text-ink-4 transition hover:bg-raised hover:text-ink-2 md:hidden"
          :aria-expanded="sidebarOpen" aria-label="Close document panel" @click="sidebarOpen = false">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <div class="slim-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        <!-- Actions -->
        <div class="py-3">
          <button type="button" @click="newChat" :disabled="!messages.length || isGenerating"
            class="flex w-full items-center gap-2 rounded-control border border-edge bg-panel px-2.5 py-2 text-left text-[12.5px] font-medium text-ink-2 transition hover:border-brand/40 hover:bg-raised hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-edge disabled:hover:bg-panel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            <span>New chat</span>
          </button>
        </div>

        <!-- Documents explorer -->
        <section aria-labelledby="docs-heading">
          <div class="flex items-center justify-between gap-2 px-1.5 pb-2 pt-1">
            <h2 id="docs-heading" class="section-label">Documents</h2>
            <span v-if="fileCount" class="mono-meta truncate">{{ fileCount }} file{{ fileCount === 1 ? '' : 's' }} · {{ totalChunks }} chunks</span>
          </div>

          <div class="rounded-panel border border-edge bg-panel p-2.5 shadow-panel">
            <!-- Compact dropzone: same file input + drag/drop as before -->
            <div
              class="relative rounded-control border border-dashed transition-colors"
              :class="dragOver ? 'border-signal/70 bg-signal-wash' : 'border-edge bg-terminal hover:border-brand/50 hover:bg-brand-wash'"
              @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false" @drop.prevent="onDrop">
              <input data-testid="file-input" type="file" accept=".txt,.md,.pdf"
                class="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                aria-label="Upload a document (TXT, Markdown or PDF, up to 5 MB)" @change="onUpload" />
              <div class="pointer-events-none flex flex-col items-center px-3 py-4 text-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="text-brand-soft" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>
                <p class="mt-1.5 text-[12px] font-medium text-ink-2">Drop technical documents</p>
                <p class="mt-0.5 font-mono text-[10.5px] tracking-wide text-ink-4">PDF · TXT · MD · max 5 MB</p>
                <span class="mt-2.5 inline-flex items-center gap-1.5 rounded-control border border-edge bg-raised px-2.5 py-1 font-mono text-[10.5px] font-medium uppercase tracking-wider text-ink-2">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z"/></svg>
                  Browse files
                </span>
              </div>
            </div>

            <!-- Upload status: idle | uploading | success | error -->
            <div v-if="uploadStatus" data-testid="upload-status" role="status" aria-live="polite"
              class="mt-2.5 flex items-start gap-1.5 rounded-control border px-2.5 py-2 text-[11.5px] leading-[1.45] transition-colors"
              :class="uploadStatusClasses">
              <svg v-if="uploadState === 'uploading'" class="mt-[1px] shrink-0 animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
              <svg v-else-if="uploadState === 'success'" class="mt-[1px] shrink-0" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.2 2.4 2.4 4.6-5"/></svg>
              <svg v-else-if="uploadState === 'error'" class="mt-[1px] shrink-0" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V13m0 3.4v.4"/></svg>
              <span class="min-w-0 break-words">{{ uploadStatus }}</span>
            </div>
            <div v-if="uploadState === 'uploading'" class="mt-2" aria-hidden="true">
              <div class="relative h-[3px] overflow-hidden rounded-full bg-raised">
                <div class="animate-pulse-line absolute inset-y-0 w-1/2 rounded-full bg-brand/70"></div>
              </div>
              <p class="mt-1.5 font-mono text-[10px] tracking-wide text-ink-4">chunking + indexing for retrieval…</p>
            </div>

            <!-- Indexed documents -->
            <ul v-if="uploaded.length" class="mt-2.5 space-y-1 border-t border-edge pt-2.5" aria-label="Indexed documents">
              <li v-for="(f, i) in uploaded" :key="f.filename + i"
                class="group flex items-center gap-2 rounded-control border border-transparent bg-terminal px-2 py-1.5 transition hover:border-edge hover:bg-raised cursor-pointer"
                @click="selectDocument(f.filename)"
                :class="{ 'ring-2 ring-brand/50 bg-brand-wash': selectedDocument === f.filename }">
                <span class="grid h-6 w-6 shrink-0 place-items-center rounded border font-mono text-[8.5px] font-bold tracking-tight"
                  :class="fileKind(f.filename).cls" aria-hidden="true">{{ fileKind(f.filename).tag }}</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-mono text-[11.5px] text-ink-2">{{ f.filename }}</span>
                  <span class="block font-mono text-[10px] text-ink-4">{{ f.chunks_processed }} chunks indexed</span>
                </span>
                <span class="inline-flex shrink-0 items-center gap-1 font-mono text-[9.5px] font-semibold uppercase tracking-wider text-ok">
                  <span class="status-dot bg-ok" aria-hidden="true"></span>Ready
                </span>
                <span v-if="selectedDocument === f.filename" class="ml-auto inline-flex items-center gap-1 font-mono text-[9.5px] font-semibold uppercase tracking-wider text-brand-soft">
                  <span class="status-dot bg-brand-soft" aria-hidden="true"></span>Selected
                </span>
                <button type="button" data-testid="remove-doc"
                  :disabled="removing !== '' || isGenerating"
                  class="grid h-6 w-6 shrink-0 place-items-center rounded border border-edge bg-panel text-ink-4 transition hover:border-danger/45 hover:bg-danger/10 hover:text-danger disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-edge disabled:hover:bg-panel disabled:hover:text-ink-4"
                  :aria-label="`Remove ${f.filename} from the index`"
                  @click.stop="removeDocument(f)">
                  <svg v-if="removing !== f.filename" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2M9 11v6M15 11v6M6 7l1 13h10l1-13"/></svg>
                  <svg v-else class="animate-spin" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
                </button>
              </li>
            </ul>
          </div>
        </section>

        <!-- Workspace meta -->
        <section aria-labelledby="ws-heading" class="mt-4">
          <h2 id="ws-heading" class="section-label px-1.5 pb-2">Workspace</h2>
          <dl class="space-y-1 rounded-panel border border-edge bg-panel px-2.5 py-2 font-mono text-[10.5px]">
            <div class="flex items-center justify-between gap-2">
              <dt class="text-ink-4">index</dt>
              <dd class="text-ink-2">{{ fileCount }} files · {{ totalChunks }} chunks</dd>
            </div>
            <div class="flex items-center justify-between gap-2">
              <dt class="text-ink-4">retrieval</dt>
              <dd class="text-ink-2">top-3 semantic</dd>
            </div>
            <div class="flex items-center justify-between gap-2">
              <dt class="text-ink-4">scope</dt>
              <dd class="text-ink-2">programming only</dd>
            </div>
          </dl>
        </section>

        <p class="px-1.5 pt-3 text-[10.5px] leading-[1.5] text-ink-4">
          Answers are grounded in the documents you index. Chat history is kept for this session only.
        </p>
      </div>
    </aside>

    <!-- ==================== Chat workspace ==================== -->
    <main class="flex min-h-0 min-w-0 flex-1 flex-col">
      <!-- Header. Same h-app-header as the sidebar brand row above. -->
      <header class="flex h-app-header shrink-0 items-center gap-3 border-b border-edge bg-workspace/80 px-3 backdrop-blur sm:px-5">
        <button type="button"
          class="rounded-control border border-edge bg-panel p-2 text-ink-3 transition hover:border-brand/40 hover:text-ink md:hidden"
          :aria-expanded="sidebarOpen" aria-label="Open document panel" @click="sidebarOpen = !sidebarOpen">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
        </button>

        <div class="min-w-0 flex-1">
          <p class="truncate text-[13px] font-semibold leading-tight text-ink">Chat workspace</p>
          <p class="truncate font-mono text-[10.5px] leading-tight text-ink-4">
            {{ selectedDocument ? `Chatting with: ${selectedDocument}` : fileCount ? `${totalChunks} chunks indexed from ${fileCount} file${fileCount === 1 ? '' : 's'} — select a document to chat` : 'no documents indexed yet' }}
          </p>
        </div>

        <!-- Connection status: reflects the real WebSocket readyState. Fixed height so it
             can never stretch the header row. -->
        <div class="flex h-7 shrink-0 items-center gap-1.5 rounded-control border border-edge bg-panel px-2"
          role="status" aria-live="polite">
          <span class="status-dot" :class="connectionMeta.dot" aria-hidden="true"></span>
          <span class="font-mono text-[10.5px] font-medium leading-none tracking-wide" :class="connectionMeta.text">{{ connectionMeta.label }}</span>
        </div>
      </header>

      <!-- Messages -->
      <div ref="chatScroll" class="slim-scroll min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div class="mx-auto w-full max-w-[860px] px-4 pt-6 pb-10 sm:px-6">
          <!-- Empty state -->
          <div v-if="!messages.length" class="animate-fade-up mx-auto flex max-w-2xl flex-col items-center px-1 pt-4 text-center sm:pt-8 [@media(max-height:760px)]:pt-1">
            <div class="grid h-12 w-12 place-items-center rounded-panel border border-brand/25 bg-brand-wash text-brand-soft" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 7-5 5 5 5M16 7l5 5-5 5"/><path d="M13.5 4.5 10.5 19.5"/></svg>
            </div>
            <h2 class="mt-5 text-[26px] font-semibold leading-tight tracking-tight text-ink sm:text-[30px]">Your developer workspace is ready.</h2>
            <p class="mt-2.5 max-w-xl text-[14.5px] leading-6 text-ink-3">
              Upload your project documentation and ask DevAssist about the code, architecture, APIs, or implementation details.
            </p>

            <div class="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-2" role="group" aria-label="Example prompts">
              <button v-for="s in suggestions" :key="s" type="button"
                class="group flex items-center gap-2.5 rounded-panel border border-edge bg-panel px-3.5 py-3 text-left text-[13px] text-ink-2 shadow-panel transition hover:border-brand/45 hover:bg-raised hover:text-ink"
                :aria-label="`Use example prompt: ${s}`" @click="pickSuggestion(s)">
                <svg class="shrink-0 text-ink-4 transition group-hover:text-brand-soft" width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="m8 5-1 14 4-1 1-5 5 2 1-2-5-2 1-5z"/></svg>
                <span class="min-w-0">{{ s }}</span>
              </button>
            </div>

            <p class="mt-6 pb-3 font-mono text-[11px] text-ink-4">
              <span class="text-signal-soft">$</span> index a document, then run
              <span class="text-ink-3">“Analyze the uploaded documents”</span>
            </p>
          </div>

          <!-- Conversation -->
          <div v-else class="space-y-7 pb-2">
            <div v-for="(m, i) in messages" :key="i" class="animate-fade-up">
              <!-- User: elevated panel, right-aligned -->
              <div v-if="m.role === 'user'" class="flex justify-end">
                <div class="max-w-[86%] whitespace-pre-wrap rounded-panel border border-brand/25 bg-brand-wash px-3.5 py-2.5 text-[14.5px] leading-[1.65] text-ink sm:max-w-[75%]">
                  <span class="sr-only">You said:</span>{{ m.content }}
                </div>
              </div>

              <!-- Assistant: the primary workspace, spacious and readable -->
              <div v-else class="flex gap-3">
                <div class="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-control border border-brand/25 bg-brand-wash text-brand-soft" aria-hidden="true">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 7-5 5 5 5M16 7l5 5-5 5"/></svg>
                </div>
                <div class="min-w-0 flex-1">
                  <div class="mb-1.5 flex items-baseline gap-2">
                    <span class="text-[12.5px] font-semibold text-ink">DevAssist</span>
                    <span class="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-4">Assistant</span>
                    <span v-if="isGenerating && i === messages.length - 1" class="font-mono text-[10px] uppercase tracking-[0.12em] text-brand-soft">streaming</span>
                  </div>

                  <div v-if="m.content" class="markdown-body" v-enhance v-html="renderMarkdown(m.content)"></div>
                  <div v-else class="flex items-center gap-2.5 py-1" role="status" aria-label="DevAssist is generating a response">
                    <span class="typing-dots flex items-center gap-1.5"><span></span><span></span><span></span></span>
                    <span class="font-mono text-[11.5px] text-ink-4">DevAssist is thinking…</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Composer -->
      <div class="shrink-0 border-t border-edge bg-workspace/85 px-3 pb-3 pt-3 backdrop-blur sm:px-5 sm:pb-4">
        <form class="mx-auto w-full max-w-[860px]" @submit.prevent="send">
          <div class="flex items-end gap-2 rounded-panel border border-edge bg-raised p-2 shadow-panel transition focus-within:border-brand/60 focus-within:shadow-focus-brand">
            <textarea ref="inputEl" v-model="input" data-testid="chat-input" rows="2"
              placeholder="Ask DevAssist about your code…" aria-label="Message DevAssist"
              class="max-h-40 min-h-[42px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] leading-6 text-ink outline-none placeholder:text-ink-4"
              @keydown.enter.exact.prevent="send"></textarea>
            <button data-testid="send-button" type="submit" :disabled="!canSend(input, isGenerating)"
              class="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-brand text-white shadow-sm transition hover:bg-brand-deep active:scale-95 disabled:cursor-not-allowed disabled:bg-edge disabled:text-ink-4"
              :aria-label="isGenerating ? 'Generating response, please wait' : 'Send message'">
              <svg v-if="isGenerating" class="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5m0 0-6 6m6-6 6 6"/></svg>
              <span class="sr-only">{{ isGenerating ? 'Generating…' : 'Send' }}</span>
            </button>
          </div>
          <div class="mt-1.5 flex items-center justify-between gap-3 px-0.5 font-mono text-[10.5px] text-ink-4">
            <span>Enter to send · Shift + Enter for a new line</span>
            <span class="hidden sm:inline">programming questions only</span>
          </div>
        </form>
      </div>
    </main>
  </div>
</template>