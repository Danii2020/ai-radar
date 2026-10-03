import { FeedView, loadFeedState, parseFeedSearchParams } from '@/features/feed'

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const { tag, cursor } = parseFeedSearchParams(await searchParams)
  const state = await loadFeedState({ tag, cursor })
  return <FeedView state={state} tag={tag} cursor={cursor} />
}
