/**
 * Spec: web-chat-ui-polish, O4 (AC1, AC2). The safe markdown subset for assistant answers.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

afterEach(cleanup)
import { MessageResponse } from './message-response'

function renderAnswer(markdown: string) {
  return render(<MessageResponse>{markdown}</MessageResponse>)
}

describe('markdown becomes elements (AC1)', () => {
  it('renders bold, ordered lists and keeps the citation markers as plain text', () => {
    const { container } = renderAnswer('**Agents** matter:\n\n1. LangGraph [1]\n2. CrewAI [2]')
    expect(container.querySelector('strong')?.textContent).toBe('Agents')
    const items = container.querySelectorAll('ol > li')
    expect(items).toHaveLength(2)
    expect(items[0].textContent).toBe('LangGraph [1]')
    expect(items[1].textContent).toBe('CrewAI [2]')
    expect(container.textContent).not.toContain('**')
  })

  it('renders bulleted lists, inline code and fenced code blocks', () => {
    const { container } = renderAnswer('- one\n- two\n\nUse `build()` now.\n\n```\nconst a = 1\n```')
    expect(container.querySelectorAll('ul > li')).toHaveLength(2)
    expect(container.querySelector('p code')?.textContent).toBe('build()')
    expect(container.querySelector('pre > code')?.textContent).toBe('const a = 1\n')
  })

  it('does not render tables (no GFM): the source stays visible as text', () => {
    const { container } = renderAnswer('| a | b |\n|---|---|\n| 1 | 2 |')
    expect(container.querySelector('table')).toBeNull()
    expect(container.textContent).toContain('| a | b |')
  })
})

describe('markdown is safe (AC2)', () => {
  it.each([
    ['a script tag', '<script>alert(1)</script>', 'script'],
    ['an img tag with onerror', '<img src=x onerror=alert(1)>', 'img'],
    ['a markdown image', '![t](https://e.x/p.png)', 'img'],
    ['an iframe', "<iframe src='https://e.x'></iframe>", 'iframe'],
  ])('renders %s as no element', (_name, markdown, tag) => {
    const { container } = renderAnswer(markdown)
    expect(container.querySelector(tag)).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
  })

  it('shows raw HTML as inert text', () => {
    const { container } = renderAnswer('<b>hi</b>')
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toContain('<b>hi</b>')
  })

  it.each([
    ['javascript:', 'javascript:alert(1)'],
    ['data:', 'data:text/html,hi'],
    ['vbscript:', 'vbscript:msgbox(1)'],
    ['mailto:', 'mailto:a@b.c'],
    ['a relative path', '/relative'],
    ['a fragment', '#x'],
    ['a protocol-relative URL', '//e.x/p'],
  ])('gives a %s link no href', (_name, url) => {
    const { container } = renderAnswer(`[label](${url})`)
    expect(container.querySelector('a[href]')).toBeNull()
    expect(container.textContent).toContain('label')
  })

  it.each(['https://example.test/a', 'http://example.test/b'])('opens %s in a new tab safely', (url) => {
    renderAnswer(`[label](${url})`)
    const link = screen.getByRole('link', { name: 'label' })
    expect(link).toHaveAttribute('href', url)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
