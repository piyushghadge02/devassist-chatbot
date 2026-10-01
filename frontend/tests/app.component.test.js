import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../src/App.vue'

class FakeWS {
  constructor(url) { this.url = url; this.readyState = 0; FakeWS.instance = this }
  addEventListener(ev, fn) { if (ev === 'open') queueMicrotask(fn) }
  send() {
    queueMicrotask(() => {
      for (const t of ['Use this:\n\n```python\n', 'print(42)\n', '```\n'])
        this.onmessage?.({ data: JSON.stringify({ status: 'streaming', token: t }) })
      this.onmessage?.({ data: JSON.stringify({ status: 'done' }) })
    })
  }
}
global.WebSocket = FakeWS
global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ filename: 'guide.txt', chunks_processed: 5 }) }))

describe('redesigned App.vue (DOM behavior)', () => {
  it('renders brand, empty state and 4 example prompts', async () => {
    const w = mount(App)
    expect(w.text()).toContain('DevAssist')
    expect(w.text()).toContain('Your developer workspace is ready.')
    for (const s of ['Explain this architecture', 'Analyze the uploaded documents',
                     'Find requirements in the documents', 'Suggest an implementation approach'])
      expect(w.text()).toContain(s)
    expect(w.find('[data-testid="file-input"]').exists()).toBe(true)
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeDefined()
  })
  it('example prompt populates the input only (does not send)', async () => {
    const w = mount(App)
    const btn = w.findAll('button').find(b => b.text().includes('Suggest an implementation approach'))
    await btn.trigger('click')
    expect(w.find('[data-testid="chat-input"]').element.value).toBe('Suggest an implementation approach')
    expect(FakeWS.instance).toBeUndefined()
  })
  it('streams a markdown answer and decorates the code block (lang label + copy button)', async () => {
    const w = mount(App)
    await w.find('[data-testid="chat-input"]').setValue('Explain this Python code')
    expect(w.find('[data-testid="send-button"]').attributes('disabled')).toBeUndefined()
    await w.find('form').trigger('submit')
    await flushPromises(); await new Promise(r => setTimeout(r, 30)); await flushPromises()
    const html = w.html()
    expect(html).toContain('code-block')
    expect(html).toContain('language-python')
    expect(html).toContain('hljs')
    expect(html).toContain('Copy')
    expect(w.find('[data-testid="send-button"]').text()).toContain('Send')
  })
  it('upload flow shows success status and a Ready document row', async () => {
    const w = mount(App)
    const input = w.find('[data-testid="file-input"]')
    const file = new File(['hello world'], 'guide.txt', { type: 'text/plain' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('Indexed guide.txt: 5 chunks')
    expect(w.text()).toContain('Ready')
    expect(w.text()).toContain('5 chunks indexed')
  })
  it('upload validation error is shown in the status area', async () => {
    const w = mount(App)
    const input = w.find('[data-testid="file-input"]')
    const file = new File(['x'], 'bad.exe', { type: 'application/octet-stream' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(w.find('[data-testid="upload-status"]').text()).toContain('Unsupported file type')
  })
})
