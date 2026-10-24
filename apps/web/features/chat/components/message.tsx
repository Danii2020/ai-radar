import type { ReactNode } from 'react'
import styles from './chat.module.css'

export function Message({ from, children }: { from: 'user' | 'assistant'; children: ReactNode }) {
  return <div className={from === 'user' ? styles.userMessage : styles.assistantMessage}>{children}</div>
}

export function MessageContent({ children }: { children: ReactNode }) {
  return <div className={styles.messageContent}>{children}</div>
}
