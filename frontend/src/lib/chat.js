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
export function canSend(text, isGenerating) {
  return Boolean(text && text.trim().length > 0) && !isGenerating
}
export const RATE_LIMIT_MESSAGE = 'Traffic is high. Please wait 10 seconds before asking again.'
export function validateUpload(file) {
  const allowed = ['.txt', '.md', '.pdf']
  const name = (file?.name || '').toLowerCase()
  const ext = name.slice(name.lastIndexOf('.'))
  if (!allowed.includes(ext)) return `Unsupported file type. Allowed: .txt, .md, .pdf`
  if (file.size > 5 * 1024 * 1024) return 'File too large. Maximum size is 5MB.'
  if (file.size === 0) return 'Empty file.'
  return null
}
export function createChatSocket(url, { onToken, onDone, onError }) {
  const ws = new WebSocket(url)
  ws.onmessage = (ev) => {
    let data; try { data = JSON.parse(ev.data) } catch { return }
    if (data.status === 'streaming') onToken?.(data.token || '')
    else if (data.status === 'done') onDone?.()
    else if (data.status === 'error') onError?.(data.error || RATE_LIMIT_MESSAGE)
  }
  return ws
}
