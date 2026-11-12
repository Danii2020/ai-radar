/** The swipe rule: at least SWIPE_MIN_DX px of horizontal travel and |dx| >= SWIPE_RATIO * |dy|. */
export const SWIPE_MIN_DX = 40
export const SWIPE_RATIO = 2

export type Swipe = 'left' | 'right' | 'none'

/** Classify total travel (dx positive = rightward, dy positive = downward). Both bounds are inclusive. */
export function classifySwipe(dx: number, dy: number): Swipe {
  const ax = Math.abs(dx)
  if (ax < SWIPE_MIN_DX || ax < SWIPE_RATIO * Math.abs(dy)) return 'none'
  return dx < 0 ? 'left' : 'right'
}
