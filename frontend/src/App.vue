<script setup>
import { ref } from 'vue'
import { renderMarkdown, canSend, validateUpload, createChatSocket, RATE_LIMIT_MESSAGE } from './lib/chat.js'

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/chat'
const messages = ref([]) // session only — refresh clears history (SRS 3.1, acceptable for MVP)
const input = ref('')
const isGenerating = ref(false)
const uploaded = ref([])
const uploadStatus = ref('')
const socket = ref(null)

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
async function onUpload(event) {
  const file = event.target.files?.[0]; if (!file) return
  const err = validateUpload(file)
  if (err) { uploadStatus.value = err; return }
  uploadStatus.value = `Uploading ${file.name}…`
  const form = new FormData(); form.append('file', file)
  try {
    const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
    const body = await res.json()
    if (!res.ok) throw new Error(body.detail || 'Upload failed')
    uploaded.value.push(body)
    uploadStatus.value = `Indexed ${body.filename}: ${body.chunks_processed} chunks`
  } catch (e) { uploadStatus.value = e.message }
  event.target.value = ''
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
</script>
<template>
  <div class="flex h-screen bg-slate-950 text-slate-100">
    <aside class="w-80 shrink-0 border-r border-slate-800 p-4 space-y-4">
      <h1 class="text-xl font-bold">DevAssist</h1>
      <p class="text-sm text-slate-400">Programming-only assistant with document RAG.</p>
      <label class="block">
        <span class="text-sm font-medium">Upload document (.txt, .md, .pdf, max 5MB)</span>
        <input data-testid="file-input" type="file" accept=".txt,.md,.pdf" class="mt-2 block w-full text-sm" @change="onUpload" />
      </label>
      <p data-testid="upload-status" class="text-sm text-emerald-400">{{ uploadStatus }}</p>
      <ul class="text-sm space-y-1">
        <li v-for="f in uploaded" :key="f.filename + f.chunks_processed">📄 {{ f.filename }} — {{ f.chunks_processed }} chunks</li>
      </ul>
    </aside>
    <main class="flex flex-1 flex-col">
      <div class="flex-1 overflow-y-auto p-6 space-y-4">
        <div v-for="(m, i) in messages" :key="i" :class="m.role === 'user' ? 'text-right' : 'text-left'">
          <div v-if="m.role === 'user'" class="inline-block rounded bg-indigo-600 px-4 py-2">{{ m.content }}</div>
          <div v-else class="prose prose-invert max-w-none rounded bg-slate-800 px-4 py-2" v-html="renderMarkdown(m.content)"></div>
        </div>
        <p v-if="!messages.length" class="text-slate-400">Ask a programming question, e.g. “How do I reverse a list in Python?”</p>
      </div>
      <form class="flex gap-2 border-t border-slate-800 p-4" @submit.prevent="send">
        <textarea v-model="input" data-testid="chat-input" rows="2" placeholder="Ask a programming question… (code welcome)"
          class="flex-1 rounded bg-slate-800 p-3" @keydown.enter.exact.prevent="send"></textarea>
        <button data-testid="send-button" type="submit" :disabled="!canSend(input, isGenerating)"
          class="rounded bg-indigo-500 px-5 disabled:opacity-40">{{ isGenerating ? 'Generating…' : 'Send' }}</button>
      </form>
    </main>
  </div>
</template>
