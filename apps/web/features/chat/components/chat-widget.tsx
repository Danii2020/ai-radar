'use client'

import { useEffect, useId, useReducer, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { conversationReducer, initialConversation, selectHistory } from '../lib/conversation'
import { QUESTION_MAX_CHARS } from '../lib/limits'
import { sendTurn } from '../lib/send-turn'
import { ChatPanel } from './chat-panel'
import styles from './chat.module.css'

export function ChatWidget() {
  const panelId = useId()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [inputError, setInputError] = useState<string | null>(null)
  const [state, dispatch] = useReducer(conversationReducer, initialConversation)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const lastQuestion = useRef('')
  const inflight = useRef<AbortController | null>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => () => inflight.current?.abort(), [])

  // Focus returns to the launcher after the panel has unmounted: on a phone the launcher is
  // hidden while the sheet is open, so focusing it synchronously would do nothing.
  const returnFocus = useRef(false)
  useEffect(() => {
    if (!open && returnFocus.current) {
      returnFocus.current = false
      toggleRef.current?.focus()
    }
  }, [open])

  function close() {
    returnFocus.current = true
    setOpen(false)
  }

  function toggle() {
    if (open) close()
    else setOpen(true)
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && open) {
      event.stopPropagation()
      close()
    }
  }

  async function send(question: string) {
    lastQuestion.current = question
    dispatch({ type: 'asked', question })
    setDraft('')
    const controller = new AbortController()
    inflight.current = controller
    const result = await sendTurn({ question, history: selectHistory(state), signal: controller.signal })
    if (controller.signal.aborted && inflight.current !== controller) return
    if (result.ok) {
      dispatch({ type: 'answered', answer: result.answer, sources: result.sources })
    } else {
      setDraft(question)
      dispatch({ type: 'failed', code: result.code })
    }
  }

  function submit(text: string = draft) {
    if (state.pending !== null) return
    const question = text.trim()
    if (question === '') {
      setInputError('Type a question first.')
      return
    }
    if (question.length > QUESTION_MAX_CHARS) {
      setInputError(`That question is too long. Keep it under ${QUESTION_MAX_CHARS} characters.`)
      return
    }
    setInputError(null)
    void send(question)
  }

  function retry() {
    if (state.pending === null && lastQuestion.current !== '') void send(lastQuestion.current)
  }

  return (
    <div className={`${styles.widget} ${open ? styles.widgetOpen : ''}`} onKeyDown={onKeyDown}>
      {open ? (
        <ChatPanel
          id={panelId}
          messages={state.messages}
          pending={state.pending}
          error={state.error}
          inputError={inputError}
          draft={draft}
          inputRef={inputRef}
          onDraftChange={(value) => {
            setDraft(value)
            setInputError(null)
          }}
          onSubmit={() => submit()}
          onSuggest={(question) => submit(question)}
          onRetry={retry}
          onClose={close}
        />
      ) : null}
      <button
        ref={toggleRef}
        type="button"
        className={styles.toggle}
        data-testid="chat-launcher"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? 'Close chat' : 'Open chat'}
        onClick={toggle}
      >
        {open ? 'Close' : 'Chat'}
      </button>
    </div>
  )
}
