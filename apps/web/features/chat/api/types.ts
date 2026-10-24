export type ChatRole = 'user' | 'assistant'

export interface ChatTurn {
  role: ChatRole
  text: string
}

export interface ChatSource {
  n: number
  title: string
  url: string
  source: string
  published: string | null
  score: number
}

export interface ChatResponse {
  answer: string
  sources: ChatSource[]
}

/** The fixed set of codes the route returns to the browser. */
export type ChatErrorCode =
  | 'invalid_request'
  | 'busy'
  | 'timeout'
  | 'upstream_failure'
  | 'unavailable'
  | 'internal_error'

/** What the backend call can report (internal; mapped to a ChatErrorCode by the route). */
export type BackendOutcome =
  | 'invalid_request'
  | 'busy'
  | 'timeout'
  | 'upstream_failure'
  | 'backend_forbidden'
  | 'backend_error'
