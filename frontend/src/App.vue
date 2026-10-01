<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { renderMarkdown, canSend, validateUpload, createChatSocket, RATE_LIMIT_MESSAGE } from './lib/chat.js'

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/chat'
const messages = ref([]) // session only — refresh clears history (SRS 3.1, acceptable for MVP)
const input = ref('')
const isGenerating = ref(false)
const uploaded = ref([])
const uploadStatus = ref('')
const uploadState = ref('idle') // idle | uploading | success | error (UI state only)
const dragOver = ref(false)
const sidebarOpen = ref(true)
const socket = ref(null)
const inputEl = ref(null)
const chatScroll = ref(null)

const suggestions = [
  'Explain this Python code',
  'Debug my JavaScript function',
  'Explain this document',
  'Design a REST API'
]

const statusClasses = computed(() => ({
  uploading: 'border-indigo-100 bg-indigo-50 text-indigo-700',
  success: 'border-emerald-100 bg-emerald-50 text-emerald-700',
  error: 'border-rose-100 bg-rose-50 text-rose-700',
  idle: 'border-slate-200 bg-slate-100 text-slate-600'
}[uploadState.value]))

function ensureSocket() {
  if (socket.value && socket.value.readyState <= 1) return socket.value
  socket.value = createChatSocket(WS_URL, {
    onToken(token) {
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') last.content += token
    },
    onDone() { isGenerating.value = false },
    onError(err) {
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant' && !last.content) last.content = err
      else messages.value.push({ role: 'assistant', content: err })
      isGenerating.value = false
    }
  })
  return socket.value
}
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
    uploadState.value = 'success'
    uploadStatus.value = `Indexed ${body.filename}: ${body.chunks_processed} chunks`
  } catch (e) { uploadState.value = 'error'; uploadStatus.value = e.message }
}
function onUpload(event) {
  handleFile(event.target.files?.[0])
  event.target.value = ''
}
function onDrop(event) {
  dragOver.value = false
  handleFile(event.dataTransfer?.files?.[0])
}
function pickSuggestion(text) {
  input.value = text
  nextTick(() => inputEl.value?.focus())
}
function send() {
  if (!canSend(input.value, isGenerating.value)) return
  const text = input.value.trim(); input.value = ''
  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '' })
  isGenerating.value = true
  const ws = ensureSocket()
  const payload = JSON.stringify({ message: text })
  if (ws.readyState === 1) ws.send(payload)
  else ws.addEventListener('open', () => ws.send(payload), { once: true })
}

// Keep the newest message in view while streaming.
watch(messages, () => nextTick(() => {
  const el = chatScroll.value
  if (el) el.scrollTop = el.scrollHeight
}), { deep: true })

// Decorate rendered code blocks with a language label + copy button (UI only).
const copySvg = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
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
  <div class="flex h-[100dvh] flex-col bg-[#f4f5fa] text-slate-800 md:flex-row">
    <!-- ============ Sidebar ============ -->
    <aside class="flex shrink-0 flex-col border-b border-slate-200 bg-white/85 backdrop-blur md:w-[320px] md:min-w-[320px] md:border-b-0 md:border-r">
      <!-- Brand -->
      <div class="flex items-center gap-3 px-5 pb-3 pt-5">
        <div class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 7-5 5 5 5M16 7l5 5-5 5"/></svg>
        </div>
        <div class="min-w-0 flex-1">
          <h1 class="text-[17px] font-bold leading-tight tracking-tight text-slate-900">DevAssist</h1>
          <p class="text-xs leading-tight text-slate-500">AI programming assistant</p>
        </div>
        <button type="button" class="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 md:hidden"
          :aria-expanded="sidebarOpen" aria-label="Toggle document panel" @click="sidebarOpen = !sidebarOpen">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ 'rotate-180': !sidebarOpen }" class="transition-transform"><path d="m6 9 6 6 6-6"/></svg>
        </button>
      </div>

      <div v-show="sidebarOpen" class="slim-scroll space-y-5 overflow-y-auto px-5 pb-5 md:!block">
        <p class="text-sm leading-6 text-slate-500">Ask programming questions and get clear, document-aware answers — grounded in files you upload.</p>

        <!-- Upload card -->
        <section class="rounded-2xl border border-slate-200 bg-slate-50/70 p-4 shadow-card" aria-labelledby="upload-heading">
          <h2 id="upload-heading" class="text-sm font-semibold text-slate-800">Documents</h2>
          <p class="mt-0.5 text-xs leading-5 text-slate-500">Add context so answers can cite your own material.</p>

          <div class="relative mt-3 rounded-xl border-2 border-dashed transition-colors"
            :class="dragOver ? 'border-indigo-400 bg-indigo-50' : 'border-slate-300 bg-white hover:border-indigo-300 hover:bg-indigo-50/50'"
            @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false" @drop.prevent="onDrop">
            <input data-testid="file-input" type="file" accept=".txt,.md,.pdf"
              class="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              aria-label="Upload a document (TXT, Markdown or PDF, up to 5 MB)" @change="onUpload" />
            <div class="pointer-events-none flex flex-col items-center px-4 py-6 text-center">
              <div class="grid h-10 w-10 place-items-center rounded-full bg-indigo-50 text-indigo-500" aria-hidden="true">
                <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3M12 3v11m0-11L7.5 7.5M12 3l4.5 4.5"/></svg>
              </div>
              <p class="mt-2.5 text-sm font-medium text-slate-700">Drag &amp; drop your file here</p>
              <p class="mt-0.5 text-xs text-slate-400">or click to browse your computer</p>
            </div>
          </div>

          <div class="mt-3 flex items-center gap-1.5" aria-label="Supported formats: PDF, TXT, Markdown. Maximum size 5 megabytes.">
            <span class="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide text-slate-500">PDF</span>
            <span class="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide text-slate-500">TXT</span>
            <span class="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide text-slate-500">MD</span>
            <span class="ml-auto text-[11px] font-medium text-slate-400">Max 5 MB</span>
          </div>

          <!-- Upload status (idle / uploading / success / error) -->
          <div v-if="uploadStatus" data-testid="upload-status" role="status" aria-live="polite"
            class="mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] leading-5 transition-colors" :class="statusClasses">
            <svg v-if="uploadState === 'uploading'" class="mt-0.5 shrink-0 animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
            <svg v-else-if="uploadState === 'success'" class="mt-0.5 shrink-0" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.2 2.4 2.4 4.6-5"/></svg>
            <svg v-else-if="uploadState === 'error'" class="mt-0.5 shrink-0" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V13m0 3.4v.4"/></svg>
            <span>{{ uploadStatus }}</span>
          </div>
          <div v-if="uploadState === 'uploading'" class="mt-2" aria-hidden="true">
            <div class="h-1 overflow-hidden rounded-full bg-indigo-100"><div class="h-full w-full animate-pulse rounded-full bg-indigo-400"></div></div>
            <p class="mt-1.5 text-[11px] text-indigo-500">Processing — chunking &amp; indexing this document for search…</p>
          </div>

          <!-- Indexed documents -->
          <div v-if="uploaded.length" class="mt-4">
            <h3 class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Indexed documents</h3>
            <ul class="mt-2 space-y-2">
              <li v-for="f in uploaded" :key="f.filename + f.chunks_processed"
                class="flex items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm">
                <span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-500" aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h6l4 4v14H7z"/><path d="M13 3v4h4"/></svg>
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-[13px] font-medium text-slate-700">{{ f.filename }}</span>
                  <span class="block text-[11px] text-slate-400">{{ f.chunks_processed }} chunks indexed</span>
                </span>
                <span class="inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-emerald-600">
                  <span class="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true"></span>Ready
                </span>
              </li>
            </ul>
          </div>
        </section>

        <p class="text-[11px] leading-5 text-slate-400">Programming questions only. When documents are indexed, answers are grounded in their content.</p>
      </div>
    </aside>

    <!-- ============ Chat ============ -->
    <main class="flex min-h-0 min-w-0 flex-1 flex-col">
      <div ref="chatScroll" class="slim-scroll flex-1 overflow-y-auto">
        <div class="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
          <!-- Empty state -->
          <div v-if="!messages.length" class="animate-fade-up flex flex-col items-center pt-8 text-center sm:pt-14">
            <div class="grid h-14 w-14 place-items-center rounded-2xl bg-indigo-600 text-white shadow-soft" aria-hidden="true">
              <svg width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 7-5 5 5 5M16 7l5 5-5 5"/></svg>
            </div>
            <h2 class="mt-5 text-[28px] font-bold tracking-tight text-slate-900">DevAssist</h2>
            <p class="mt-1.5 max-w-md text-[15px] leading-6 text-slate-500">Your AI programming assistant with document-aware answers.</p>
            <p class="mt-3 text-xs font-medium uppercase tracking-wider text-slate-400">Code help <span aria-hidden="true">·</span> Debugging <span aria-hidden="true">·</span> Document Q&amp;A</p>
            <div class="mt-8 grid w-full max-w-xl gap-2.5 sm:grid-cols-2" role="group" aria-label="Example prompts">
              <button v-for="s in suggestions" :key="s" type="button"
                class="group flex items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-600 shadow-sm transition hover:border-indigo-300 hover:text-indigo-700 hover:shadow-card"
                :aria-label="`Use example prompt: ${s}`" @click="pickSuggestion(s)">
                <svg class="shrink-0 text-indigo-400 transition group-hover:text-indigo-500" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z"/></svg>
                <span>{{ s }}</span>
              </button>
            </div>
            <p class="mt-7 max-w-md text-xs leading-5 text-slate-400">Tip: upload a document in the sidebar, then try <span class="font-medium text-slate-500">“Explain this document.”</span></p>
          </div>

          <!-- Messages -->
          <div v-else class="space-y-6 pb-2">
            <div v-for="(m, i) in messages" :key="i" class="animate-fade-up">
              <div v-if="m.role === 'user'" class="flex justify-end">
                <div class="max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-[15px] leading-7 text-white shadow-sm sm:max-w-[78%]"><span class="sr-only">You said:</span>{{ m.content }}</div>
              </div>
              <div v-else class="flex gap-3">
                <div class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-indigo-100 text-indigo-600" aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 7-5 5 5 5M16 7l5 5-5 5"/></svg>
                </div>
                <div class="min-w-0 flex-1 pt-0.5">
                  <p class="mb-1.5 text-xs font-semibold text-slate-500">DevAssist</p>
                  <div class="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-card">
                    <div v-if="m.content" class="markdown-body" v-enhance v-html="renderMarkdown(m.content)"></div>
                    <div v-else class="typing-dots flex items-center gap-1.5 py-2.5" role="status" aria-label="DevAssist is generating a response">
                      <span></span><span></span><span></span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Composer -->
      <div class="shrink-0 border-t border-slate-200/80 bg-[#f4f5fa]/85 px-4 py-4 backdrop-blur sm:px-6">
        <form class="mx-auto w-full max-w-3xl" @submit.prevent="send">
          <div class="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-soft transition focus-within:border-indigo-400 focus-within:ring-4 focus-within:ring-indigo-100">
            <textarea ref="inputEl" v-model="input" data-testid="chat-input" rows="2"
              placeholder="Ask a programming question… (code welcome)" aria-label="Message DevAssist"
              class="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 font-mono text-[13.5px] leading-6 text-slate-800 outline-none placeholder:font-sans placeholder:text-slate-400"
              @keydown.enter.exact.prevent="send"></textarea>
            <button data-testid="send-button" type="submit" :disabled="!canSend(input, isGenerating)"
              class="inline-flex shrink-0 items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none"
              :aria-label="isGenerating ? 'Generating response, please wait' : 'Send message'">
              <svg v-if="isGenerating" class="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
              <span>{{ isGenerating ? 'Generating…' : 'Send' }}</span>
              <svg v-if="!isGenerating" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12h15m0 0-6-6m6 6-6 6"/></svg>
            </button>
          </div>
          <div class="mt-2 flex items-center justify-between px-1 text-[11px] text-slate-400">
            <span>Enter to send · Shift + Enter for a new line</span>
            <span class="hidden sm:inline">Programming questions only</span>
          </div>
        </form>
      </div>
    </main>
  </div>
</template>
