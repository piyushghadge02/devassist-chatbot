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
