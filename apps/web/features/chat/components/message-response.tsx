import Markdown from 'react-markdown'
import type { Components } from 'react-markdown'
import styles from './chat.module.css'

// ADR 0038: a small markdown subset. Raw HTML stays inert text (no raw-HTML plugin), images are not in
// the allow-list, and only http(s) URLs survive.
const ALLOWED_ELEMENTS = [
  'p',
  'strong',
  'em',
  'ol',
  'ul',
  'li',
  'a',
  'code',
  'pre',
  'blockquote',
  'br',
  'hr',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
]

function webUrlOnly(url: string): string {
  try {
    const { protocol } = new URL(url)
    return protocol === 'http:' || protocol === 'https:' ? url : ''
  } catch {
    return ''
  }
}

const COMPONENTS: Components = {
  a({ href, children }) {
    if (!href) return <span className={styles.wrap}>{children}</span>
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={styles.markdownLink}>
        {children}
      </a>
    )
  },
}

export function MessageResponse({ children }: { children: string }) {
  return (
    <div className={styles.response}>
      <Markdown allowedElements={ALLOWED_ELEMENTS} unwrapDisallowed urlTransform={webUrlOnly} components={COMPONENTS}>
        {children}
      </Markdown>
    </div>
  )
}
