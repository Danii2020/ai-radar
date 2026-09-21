// Mirror of export_api_schema.py: one script, one committed artifact, one drift test.
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compileFromFile } from 'json-schema-to-typescript'

const here = dirname(fileURLToPath(import.meta.url))            // apps/web/scripts
const SCHEMA = join(here, '../../../docs/api/feed-api.v1.schema.json')
const OUT = join(here, '../features/feed/types.generated.ts')

export const BANNER = `/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT.
 * Source: docs/api/feed-api.v1.schema.json (feed-api, CARD_SCHEMA_VERSION "v1")
 * Regenerate with: npm run generate:types
 */`

export async function generate() {
  // additionalProperties defaults to TRUE and would inject `[k: string]: unknown`
  // index signatures, making the types accept fields the API never returns.
  return compileFromFile(SCHEMA, { additionalProperties: false, bannerComment: BANNER })
}

if (import.meta.url === `file://${process.argv[1]}`) {
  writeFileSync(OUT, await generate())
}
