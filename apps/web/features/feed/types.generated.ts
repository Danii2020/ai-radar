/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT.
 * Source: docs/api/feed-api.v1.schema.json (feed-api, CARD_SCHEMA_VERSION "v1")
 * Regenerate with: npm run generate:types
 */

export type CardId = string;
export type Title = string;
export type Url = string;
export type Source = string;
export type Summary = string;
export type Tags = string[];
export type Type = string;
export type Relevance = number;
export type Published = string;
export type Takeaways = string[];
export type CreatedAt = string;
export type UpdatedAt = string;
export type Cards = CardOut[];
export type NextCursor = string | null;

/**
 * One page of the feed. `next_cursor` is opaque: pass it back verbatim as
 * `?cursor=`. It is `None` — and ONLY None — when the feed is exhausted.
 */
export interface FeedResponse {
  cards: Cards;
  next_cursor?: NextCursor;
}
/**
 * One curated card, as returned by `GET /v1/cards`.
 *
 * Field-for-field parity with the DynamoDB item written by
 * `curation.dynamo.DynamoCardStore.upsert` (see
 * specs/dynamodb-card-store/contract.md "Item schema"), minus the internal
 * index keys `gsi_pk`/`gsi_sk` and the Phase-3-reserved `embedding`.
 */
export interface CardOut {
  card_id: CardId;
  title: Title;
  url: Url;
  source: Source;
  summary: Summary;
  tags?: Tags;
  type: Type;
  relevance: Relevance;
  published: Published;
  takeaways?: Takeaways;
  created_at: CreatedAt;
  updated_at: UpdatedAt;
}
