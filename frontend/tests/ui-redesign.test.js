// Behavioral regression tests for the dark-theme redesign.
// These assert DOM BEHAVIOR and preserved contracts (test IDs, streaming, upload,
// send gating, reset) — never specific colors or class names, so the visual layer
// can keep evolving.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../src/App.vue'

// A scriptable fake socket. `FakeWS.mode` decides what happens after send():
//   'stream'  -> tokens then done (default, mirrors a normal Groq response)
//   'pending' -> nothing (lets us observe the generating state)
//   'error'   -> a single error frame
class FakeWS {
  static last = null
  static mode = 'stream'
  constructor(url) { this.url = url; this.readyState = 0; FakeWS.last = this }
  addEventListener(ev, fn) { if (ev === 'open') queueMicrotask(fn) }
  emit(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  send() {
    queueMicrotask(() => {
      if (FakeWS.mode === 'pending') return
      if (FakeWS.mode === 'error') return this.emit({ status: 'error', error: 'Traffic is high. Please wait 10 seconds before asking again.' })
      for (const t of ['Use this:\n\n```python\n', 'print(42)\n', '```\n'])
        this.emit({ status: 'streaming', token: t })
      this.emit({ status: 'done' })
    })
  }
}
global.WebSocket = FakeWS
global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ filename: 'guide.txt', chunks_processed: 5 }) }))
global.navigator.clipboard = { writeText: vi.fn(async () => {}) }

afterEach(() => { FakeWS.mode = 'stream'; FakeWS.last = null })

async function mountApp() {
  const w = mount(App)
  await flushPromises()
  return w
}
async function sendMessage(w, text) {
  await w.find('[data-testid="chat-input"]').setValue(text)
  await w.find('form').trigger('submit')
  await flushPromises(); await new Promise(r => setTimeout(r, 30)); await flushPromises()
}

describe('required test IDs are preserved', () => {
  it('exposes file-input, chat-input, send-button, upload-status', async () => {
    const w = await mountApp()
    expect(w.find('[data-testid="file-input"]').exists()).toBe(true)
    expect(w.find('[data-testid="chat-input"]').exists()).toBe(true)
    expect(w.find('[data-testid="send-button"]').exists()).toBe(true)
  })
  it('upload-status appears only once an upload resolves or fails', async () => {
    const w = await mountApp()
    expect(w.find('[data-testid="upload-status"]').exists()).toBe(false)
    const file = new File(['hello world'], 'guide.txt', { type: 'text/plain' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').exists()).toBe(true)
  })
})

describe('send button gating (SRS 5.1)', () => {
  it('is disabled with empty input and enabled with text', async () => {
    const w = await mountApp()
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeDefined()
    await w.find('[data-testid="chat-input"]').setValue('   ')
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeDefined()
    await w.find('[data-testid="chat-input"]').setValue('hi')
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeUndefined()
  })
  it('exposes an accessible label that reflects generating state', async () => {
    FakeWS.mode = 'pending'
    const w = await mountApp()
    expect(w.find('[data-testid="send-button"]').attributes('aria-label')).toBe('Send message')
    await w.find('[data-testid="chat-input"]').setValue('x')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('[data-testid="send-button"]').attributes('aria-label')).toMatch(/Generating/)
  })
  it('disables send while a response is generating (SRS 5.1)', async () => {
    FakeWS.mode = 'pending'
    const w = await mountApp()
    await w.find('[data-testid="chat-input"]').setValue('x')
    await w.find('form').trigger('submit')
    await flushPromises()
    await w.find('[data-testid="chat-input"]').setValue('another question')
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeDefined()
  })
})

describe('streaming', () => {
  it('sends the user text, renders assistant markdown and re-enables send', async () => {
    const w = await mountApp()
    await sendMessage(w, 'Explain this Python code')
    expect(FakeWS.last.url).toContain('/ws/chat')
    expect(w.text()).toContain('Explain this Python code')
    const html = w.html()
    expect(html).toContain('language-python')
    expect(html).toContain('hljs')
    expect(html).toContain('Copy')
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeDefined() // input cleared
  })
  it('shows a streaming indicator before the first token', async () => {
    FakeWS.mode = 'pending'
    const w = await mountApp()
    await w.find('[data-testid="chat-input"]').setValue('hello')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.html()).toContain('typing-dots')
    expect(w.html()).toContain('DevAssist is thinking')
  })
  it('renders a rate-limit error frame as an assistant message', async () => {
    FakeWS.mode = 'error'
    const w = await mountApp()
    await w.find('[data-testid="chat-input"]').setValue('hi')
    await w.find('form').trigger('submit')
    await flushPromises(); await new Promise(r => setTimeout(r, 20)); await flushPromises()
    expect(w.text()).toContain('Traffic is high. Please wait 10 seconds before asking again.')
  })
})

describe('upload', () => {
  it('success shows indexed status and a Ready document row', async () => {
    const w = await mountApp()
    const file = new File(['hello world'], 'guide.txt', { type: 'text/plain' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('Indexed guide.txt: 5 chunks')
    expect(w.text()).toContain('Ready')
    expect(w.text()).toContain('5 chunks indexed')
  })
  it('rejects an unsupported extension without a request', async () => {
    const w = await mountApp()
    global.fetch.mockClear()
    const file = new File(['x'], 'bad.exe', { type: 'application/octet-stream' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('Unsupported file type')
    expect(global.fetch).not.toHaveBeenCalled()
  })
  it('rejects a file over 5MB without a request', async () => {
    const w = await mountApp()
    global.fetch.mockClear()
    const file = new File(['x'], 'big.txt', { type: 'text/plain' })
    Object.defineProperty(file, 'size', { value: 5 * 1024 * 1024 + 1 })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('5MB')
    expect(global.fetch).not.toHaveBeenCalled()
  })
  it('surfaces a server-side error detail in the status area', async () => {
    const w = await mountApp()
    global.fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'File too large. Maximum size is 5MB.' }) })
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('File too large. Maximum size is 5MB.')
  })
  it('still accepts drag-and-drop on the dropzone', async () => {
    const w = await mountApp()
    const file = new File(['hello'], 'dropped.md', { type: 'text/markdown' })
    const dropzone = w.find('[data-testid="file-input"]').element.parentElement
    expect(dropzone.className).toContain('border-dashed')
    await w.find('[data-testid="file-input"]').trigger('drop', { dataTransfer: { files: [file] } })
    await flushPromises()
    // the mocked backend responds with guide.txt; the point is that the drop reached /upload
    expect(global.fetch).toHaveBeenCalled()
    expect(w.text()).toContain('guide.txt')
  })
  it('highlights the dropzone on dragover and clears it on drop', async () => {
    const w = await mountApp()
    const input = w.find('[data-testid="file-input"]')
    const dropzone = input.element.parentElement
    const base = dropzone.className
    await input.trigger('dragover')
    expect(dropzone.className).not.toBe(base)
    expect(dropzone.className).toContain('border-signal')
    await input.trigger('drop', { dataTransfer: { files: [] } })
    expect(dropzone.className).toBe(base)
  })
})

describe('session behaviour', () => {
  it('new chat clears the conversation and is disabled when empty', async () => {
    const w = await mountApp()
    const newChat = w.findAll('button').find(b => b.text().includes('New chat'))
    expect(newChat.attributes('disabled')).toBeDefined()
    await sendMessage(w, 'hello there')
    expect(w.text()).toContain('hello there')
    await newChat.trigger('click')
    await flushPromises()
    expect(w.text()).not.toContain('hello there')
    expect(w.find('[data-testid="chat-input"]').element.value).toBe('')
  })
  it('Enter sends and Shift+Enter inserts a newline instead', async () => {
    const w = await mountApp()
    const ta = w.find('[data-testid="chat-input"]')
    await ta.setValue('line one')
    await ta.trigger('keydown', { key: 'Enter', shiftKey: true })
    await flushPromises()
    expect(w.text()).not.toContain('line one')
    await ta.setValue('line two')
    await ta.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w.text()).toContain('line two')
  })
  it('does not send when the message is whitespace only', async () => {
    const w = await mountApp()
    await w.find('[data-testid="chat-input"]').setValue('    ')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('[data-testid="chat-input"]').element.value).toBe('    ')
    expect(FakeWS.last).toBeFalsy()
    // the empty state is still showing, i.e. no conversation was appended
    expect(w.text()).toContain('Your developer workspace is ready.')
  })
})

// Regression: a backend that dies mid-turn used to leave isGenerating=true forever,
// locking the composer on "Generating response, please wait".
describe('socket drop recovery', () => {
  // Records every listener so a close/error can be fired at an exact moment.
  class DropWS {
    static last = null
    static tokensBeforeDrop = 0
    constructor(url) {
      this.url = url; this.readyState = 0; this.ls = {}; DropWS.last = this
    }
    addEventListener(ev, fn) {
      (this.ls[ev] ||= []).push(fn)
      // behave like a real socket: connecting resolves shortly after the listener attaches
      if (ev === 'open' && this.readyState === 0) {
        this.readyState = 1
        queueMicrotask(() => (this.ls.open || []).forEach(f => f()))
      }
    }
    fire(ev) { (this.ls[ev] || []).forEach(fn => fn()) }
    emit(obj) { this.onmessage?.({ data: JSON.stringify(obj) }) }
    send() {
      queueMicrotask(() => {
        for (let i = 0; i < DropWS.tokensBeforeDrop; i++) this.emit({ status: 'streaming', token: 'partial ' })
      })
    }
  }

  async function withDropWS(tokensBeforeDrop) {
    const prev = global.WebSocket
    DropWS.last = null; DropWS.tokensBeforeDrop = tokensBeforeDrop
    global.WebSocket = DropWS
    try {
      const w = await mountApp()
      await sendMessage(w, 'why is my backend down?')
      return { w, ws: DropWS.last }
    } finally { global.WebSocket = prev }
  }

  it('releases the generating lock and restores the draft when nothing streamed', async () => {
    const { w, ws } = await withDropWS(0)
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeDefined()
    ws.readyState = 3
    ws.fire('close')
    await flushPromises()
    // Send is usable again instead of stuck on "Generating..."
    expect(w.find('[data-testid="send-button"]').attributes('aria-label')).toBe('Send message')
    // the unsent draft is back so it can be retried
    expect(w.find('[data-testid="chat-input"]').element.value).toBe('why is my backend down?')
    // the empty assistant bubble is gone, the user message is kept
    expect(w.text()).toContain('why is my backend down?')
    expect(w.find('.typing-dots').exists()).toBe(false)
  })

  it('keeps a partially streamed answer when the socket drops', async () => {
    const { w, ws } = await withDropWS(2)
    ws.readyState = 3
    ws.fire('error')
    await flushPromises()
    expect(w.text()).toContain('partial partial')
    expect(w.find('[data-testid="send-button"]').attributes('aria-label')).toBe('Send message')
    // draft is not duplicated back into the composer after tokens arrived
    expect(w.find('[data-testid="chat-input"]').element.value).toBe('')
  })

  it('disables New chat while a response is streaming', async () => {
    const { w } = await withDropWS(0)
    const newChat = w.findAll('button').find(b => b.text().includes('New chat'))
    expect(newChat.attributes('disabled')).toBeDefined()
  })
})

describe('document removal', () => {
  async function uploadOk(w, name = 'guide.txt', chunks = 5) {
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'success', chunks_processed: chunks, filename: name }) })
    const file = new File(['hello world'], name, { type: 'text/plain' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
  }

  it('each document row has its own remove button', async () => {
    const w = await mountApp()
    expect(w.find('[data-testid="remove-doc"]').exists()).toBe(false)
    await uploadOk(w, 'guide.txt')
    await uploadOk(w, 'api.md')
    expect(w.findAll('[data-testid="remove-doc"]')).toHaveLength(2)
    expect(w.find('button[aria-label="Remove guide.txt from the index"]').exists()).toBe(true)
    expect(w.find('button[aria-label="Remove api.md from the index"]').exists()).toBe(true)
    // the old clear-all control is gone
    expect(w.find('[data-testid="clear-index"]').exists()).toBe(false)
  })

  it('remove deletes only that document and updates the stats', async () => {
    const w = await mountApp()
    await uploadOk(w, 'guide.txt', 5)
    await uploadOk(w, 'api.md', 3)
    expect(w.text()).toContain('2 files · 8 chunks')

    global.fetch.mockClear()
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'removed', filename: 'guide.txt', chunks_removed: 5 }) })
    await w.find('button[aria-label="Remove guide.txt from the index"]').trigger('click')
    await flushPromises()

    // calls the per-document endpoint, not the clear-all one
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/documents\/guide\.txt$/), { method: 'DELETE' }
    )
    // the row is gone (the status line still names the file it removed)
    const list = w.find('ul[aria-label="Indexed documents"]')
    expect(list.text()).not.toContain('guide.txt')
    expect(list.text()).toContain('api.md')
    expect(w.text()).toContain('1 file · 3 chunks')
    // only the surviving document keeps a remove button
    expect(w.findAll('[data-testid="remove-doc"]')).toHaveLength(1)
    expect(w.find('button[aria-label="Remove api.md from the index"]').exists()).toBe(true)
  })

  it('percent-encodes the filename in the request URL', async () => {
    const w = await mountApp()
    await uploadOk(w, 'my notes v1.md', 2)
    global.fetch.mockClear()
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'removed', chunks_removed: 2 }) })
    await w.find('[data-testid="remove-doc"]').trigger('click')
    await flushPromises()
    const url = global.fetch.mock.calls[0][0]
    expect(url).toContain('my%20notes%20v1.md')
    expect(url).not.toContain('my notes')
  })

  it('keeps the document listed and reports the error when removal fails', async () => {
    const w = await mountApp()
    await uploadOk(w, 'guide.txt')
    global.fetch.mockClear()
    global.fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Document is not in the index.' }) })
    await w.find('[data-testid="remove-doc"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('Document is not in the index')
    expect(w.text()).toContain('guide.txt')
    expect(w.findAll('[data-testid="remove-doc"]')).toHaveLength(1)
  })
})

describe('upload states', () => {
  it('never marks a failed upload as Ready', async () => {
    const w = await mountApp()
    global.fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Could not extract text: bad' }) })
    const file = new File(['x'], 'broken.pdf', { type: 'application/pdf' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    // failure copy is attributable to the file and no Ready row exists
    expect(w.find('[data-testid="upload-status"]').text()).toContain('broken.pdf')
    expect(w.text()).not.toContain('Ready')
    expect(w.find('[data-testid="clear-index"]').exists()).toBe(false)
  })
})

describe('accessibility hooks', () => {
  it('labels the upload status region as a live status', async () => {
    const w = await mountApp()
    const file = new File(['hello'], 'a.txt', { type: 'text/plain' })
    Object.defineProperty(w.find('[data-testid="file-input"]').element, 'files', { value: [file], configurable: true })
    await w.find('[data-testid="file-input"]').trigger('change')
    await flushPromises()
    const status = w.find('[data-testid="upload-status"]')
    expect(status.attributes('role')).toBe('status')
    expect(status.attributes('aria-live')).toBe('polite')
  })
  it('labels the composer and the example-prompt group', async () => {
    const w = await mountApp()
    expect(w.find('[data-testid="chat-input"]').attributes('aria-label')).toBe('Message DevAssist')
    expect(w.find('[aria-label="Upload a document (TXT, Markdown or PDF, up to 5 MB)"]').exists()).toBe(true)
    expect(w.find('[role="group"]').exists()).toBe(true)
  })
  it('decorates every code block with a labelled copy button', async () => {
    const w = await mountApp()
    await sendMessage(w, 'show code')
    const btn = w.findAll('button').find(b => b.attributes('aria-label') === 'Copy code to clipboard')
    expect(btn).toBeTruthy()
    expect(w.html()).toContain('code-block-lang')
  })
})