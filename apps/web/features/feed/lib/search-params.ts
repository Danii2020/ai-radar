export type FeedSearchParams = { [key: string]: string | string[] | undefined }

// Normalizes the raw Next.js searchParams. The tag is passed through untrimmed
// (only whitespace-only is rejected); the cursor is opaque and byte-identical.
export function parseFeedSearchParams(params: FeedSearchParams): {
  tag: string | undefined
  cursor: string | undefined
} {
  const tag = typeof params.tag === 'string' && params.tag.trim() ? params.tag : undefined
  const cursor = typeof params.cursor === 'string' && params.cursor ? params.cursor : undefined
  return { tag, cursor }
}
