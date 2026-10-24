import type { Ref } from 'react'
import type { ChatErrorCode } from '../api/types'
import type { Message as ChatMessage } from '../lib/conversation'
import styles from './chat.module.css'
import { Conversation, ConversationAutoScroll, ConversationContent, ConversationScrollButton } from './conversation'
import { ConversationEmptyState } from './conversation-empty-state'
import { Loader } from './loader'
import { Message, MessageContent } from './message'
import { MessageResponse } from './message-response'
import { PromptInput, PromptInputSubmit, PromptInputTextarea } from './prompt-input'
import { Sources } from './sources'

// Local constant: the chat must not import `features/feed` internals.
const WORDMARK = 'AI RADAR'

const ERROR_COPY: Record<ChatErrorCode, string> = {
  invalid_request: 'That question could not be sent. Check it and try again.',
  busy: 'The assistant is busy right now. Try again shortly.',
  timeout: 'The assistant took too long to reply. Try again.',
  upstream_failure: 'The assistant could not be reached. Try again.',
  unavailable: 'Chat is unavailable at the moment. Try again later.',
  internal_error: 'Something went wrong on our side. Try again.',
}

interface Props {
  id: string
  messages: ChatMessage[]
  pending: string | null
  error: ChatErrorCode | null
  inputError: string | null
  draft: string
  inputRef: Ref<HTMLTextAreaElement>
  onDraftChange: (value: string) => void
  onSubmit: () => void
  onSuggest: (question: string) => void
  onRetry: () => void
  onClose: () => void
}

export function ChatPanel(props: Props) {
  const { id, messages, pending, error, inputError, draft, inputRef, onDraftChange, onSubmit, onSuggest, onRetry, onClose } =
    props

  return (
    <div id={id} role="dialog" aria-label="Chat about AI Radar" className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <span className={styles.wordmark}>{WORDMARK}</span>
          <span className={styles.subtitle}>Ask about the cards</span>
        </div>
        <button type="button" className={styles.close} aria-label="Close chat" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12" />
            <path d="M18 6L6 18" />
          </svg>
        </button>
      </div>
      <Conversation>
        <ConversationAutoScroll when={pending !== null} />
        <ConversationContent>
          {messages.length === 0 && pending === null ? <ConversationEmptyState onSuggest={onSuggest} /> : null}
          {messages.map((message, index) => (
            <Message key={index} from={message.role}>
              <MessageContent>
                {message.role === 'user' ? (
                  <p className={styles.text}>{message.text}</p>
                ) : (
                  <MessageResponse>{message.text}</MessageResponse>
                )}
              </MessageContent>
              {message.sources ? <Sources sources={message.sources} /> : null}
            </Message>
          ))}
          {pending !== null ? (
            <>
              <Message from="user">
                <MessageContent>
                  <p className={styles.text}>{pending}</p>
                </MessageContent>
              </Message>
              <Loader />
            </>
          ) : null}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
      {inputError ? (
        <p role="alert" className={styles.alert}>
          {inputError}
        </p>
      ) : error ? (
        <div role="alert" className={styles.alert}>
          <p className={styles.text}>{ERROR_COPY[error]}</p>
          <button type="button" className={styles.retry} onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : null}
      <PromptInput>
        <PromptInputTextarea inputRef={inputRef} value={draft} onChange={onDraftChange} onSubmit={onSubmit} />
        <PromptInputSubmit disabled={pending !== null} onClick={onSubmit} />
      </PromptInput>
    </div>
  )
}
