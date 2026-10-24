import { useEffect, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { StickToBottom, useStickToBottomContext } from 'use-stick-to-bottom'
import styles from './chat.module.css'

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

function subscribeReducedMotion(onChange: () => void) {
  if (typeof window.matchMedia !== 'function') return () => {}
  const query = window.matchMedia(REDUCED_MOTION)
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}

function prefersReducedMotion() {
  return typeof window.matchMedia === 'function' && window.matchMedia(REDUCED_MOTION).matches
}

/** The scroll region: keeps the newest message in view unless the reader scrolled away. */
export function Conversation({ children }: { children: ReactNode }) {
  const reduced = useSyncExternalStore(subscribeReducedMotion, prefersReducedMotion, () => false)
  const animation = reduced ? 'instant' : 'smooth'
  return (
    <StickToBottom className={styles.conversation} initial="instant" resize={animation}>
      {children}
    </StickToBottom>
  )
}

export function ConversationContent({ children }: { children: ReactNode }) {
  return (
    <StickToBottom.Content scrollClassName={styles.scroll} className={styles.messages} aria-live="polite">
      {children}
    </StickToBottom.Content>
  )
}

/** Sending a question always re-locks the view to the bottom, even if the reader had scrolled up. */
export function ConversationAutoScroll({ when }: { when: boolean }) {
  const { scrollToBottom } = useStickToBottomContext()
  useEffect(() => {
    if (when) void scrollToBottom()
  }, [when, scrollToBottom])
  return null
}

export function ConversationScrollButton() {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext()
  if (isAtBottom) return null
  return (
    <button type="button" className={styles.jump} onClick={() => void scrollToBottom()}>
      Jump to latest
    </button>
  )
}
