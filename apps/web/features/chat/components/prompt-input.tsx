import type { KeyboardEvent, ReactNode, Ref } from 'react'
import styles from './chat.module.css'

export function PromptInput({ children }: { children: ReactNode }) {
  return <div className={styles.composer}>{children}</div>
}

interface TextareaProps {
  inputRef: Ref<HTMLTextAreaElement>
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
}

export function PromptInputTextarea({ inputRef, value, onChange, onSubmit }: TextareaProps) {
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSubmit()
    }
  }
  return (
    <textarea
      ref={inputRef}
      className={styles.input}
      aria-label="Your question"
      rows={2}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={onKeyDown}
    />
  )
}

export function PromptInputSubmit({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" className={styles.send} aria-label="Send" disabled={disabled} onClick={onClick}>
      <svg
        viewBox="0 0 24 24"
        width="20"
        height="20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 19V5" />
        <path d="m5 12 7-7 7 7" />
      </svg>
    </button>
  )
}
