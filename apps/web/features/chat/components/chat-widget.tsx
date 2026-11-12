'use client'

import { useEffect, useId, useReducer, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import { conversationReducer, initialConversation, selectHistory } from '../lib/conversation'
import { QUESTION_MAX_CHARS } from '../lib/limits'
import { sendTurn } from '../lib/send-turn'
import { classifySwipe } from '../lib/swipe'
import { ChatPanel } from './chat-panel'
import styles from './chat.module.css'

const PHONE_QUERY = '(max-width: 640px)'
const CLICK_SUPPRESS_MS = 500

function isPhone() {
  return typeof window.matchMedia === 'function' && window.matchMedia(PHONE_QUERY).matches
}

// True when the gesture starts in a place that has its own horizontal behavior: text editing or a
// horizontally scrolling element (a code block).
function ownsHorizontalGesture(target: EventTarget | null, boundary: Element) {
  for (let el = target instanceof Element ? target : null; el && el !== boundary; el = el.parentElement) {
    if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) return true
    const overflowX = (el as HTMLElement).style?.overflowX || getComputedStyle(el).overflowX
    if ((overflowX === 'auto' || overflowX === 'scroll') && el.scrollWidth > el.clientWidth) return true
  }
  return false
}

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

  // Threshold swipes (touch or pen, phone only): left on the tab opens, right on the sheet closes.
  const gestureStart = useRef<{ x: number; y: number; target: EventTarget | null; type: string } | null>(null)
  const suppressClickUntil = useRef(0)

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    gestureStart.current = null
    if (event.pointerType === 'mouse' || !isPhone()) return
    gestureStart.current = { x: event.clientX, y: event.clientY, target: event.target, type: event.pointerType }
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const start = gestureStart.current
    gestureStart.current = null
    if (!start || event.pointerType !== start.type) return
    const swipe = classifySwipe(event.clientX - start.x, event.clientY - start.y)
    if (swipe === 'none') return
    const onTab = toggleRef.current?.contains(start.target as Node) ?? false
    if (!open && swipe === 'left' && onTab) {
      suppressClickUntil.current = Date.now() + CLICK_SUPPRESS_MS
      setOpen(true)
    } else if (open && swipe === 'right' && !onTab && !ownsHorizontalGesture(start.target, event.currentTarget)) {
      close()
    }
  }

  function onToggleClick() {
    if (Date.now() < suppressClickUntil.current) {
      suppressClickUntil.current = 0
      return
    }
    toggle()
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
    <div className={`${styles.widget} ${open ? styles.widgetOpen : ''}`} onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={() => {
        gestureStart.current = null
      }}
    >
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
        onClick={onToggleClick}
      >
        <span className={styles.toggleText}>{open ? 'Close' : 'Chat'}</span>
        <svg className={styles.toggleIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
    </div>
  )
}
