import { ChatWidget } from '@/features/chat'
import { FeedView, loadFeedState, parseFeedSearchParams } from '@/features/feed'

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const { tag, cursor, direction } = parseFeedSearchParams(await searchParams)
  const state = await loadFeedState({ tag, cursor, direction })
  return (
    <>
      <FeedView state={state} tag={tag} cursor={cursor} direction={direction} />
      <ChatWidget />
    </>
  )
}
