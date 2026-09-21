/**
 * Spec: web-feed-ui
 * Covers: T1, T2, T3 (audit.md Test Coverage) / Guarantee 13, 14 / AD-3
 * (contract.md)
 *
 * This is the TypeScript mirror of
 * `tests/test_feed_api_contract.py::test_schema_artifact_matches_models`:
 * `docs/api/feed-api.v1.schema.json` is the source of truth, and
 * `features/feed/types.generated.ts` is generated output that must never
 * drift from it, by construction rather than by review.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generate } from "../../scripts/generate-api-types.mjs";
import { REQUIRED_STRING_FIELDS } from "./client";

const here = dirname(fileURLToPath(import.meta.url));
const GENERATED_PATH = join(here, "types.generated.ts");
// apps/web/features/feed -> repo root is four levels up.
const SCHEMA_PATH = join(
  here,
  "../../../../docs/api/feed-api.v1.schema.json",
);

interface JsonSchemaObject {
  properties: Record<string, unknown>;
  required: string[];
}

interface FeedApiSchema extends JsonSchemaObject {
  $defs: { CardOut: JsonSchemaObject };
}

function readSchema(): FeedApiSchema {
  return JSON.parse(readFileSync(SCHEMA_PATH, "utf-8")) as FeedApiSchema;
}

/**
 * A small, deliberate text-based extractor: TS field names in a generated
 * `json-schema-to-typescript` interface aren't reflectable at runtime, so
 * this parses the committed source text for top-level `name?: type` members
 * of a named interface, rather than trying to introspect types.
 */
function extractInterfaceFieldNames(
  source: string,
  interfaceName: string,
): string[] {
  const match = source.match(
    new RegExp(`interface\\s+${interfaceName}\\s*\\{([\\s\\S]*?)\\n\\}`),
  );
  if (!match) return [];
  return match[1]
    .split("\n")
    .map((line) => line.trim())
    .map((line) => /^([A-Za-z0-9_]+)\??:/.exec(line))
    .filter((fieldMatch): fieldMatch is RegExpExecArray => fieldMatch !== null)
    .map((fieldMatch) => fieldMatch[1]);
}

describe("types.generated.ts contract parity", () => {
  it("T1: regenerating from the schema reproduces the committed file exactly", async () => {
    const regenerated = await generate();
    const committed = readFileSync(GENERATED_PATH, "utf-8");
    expect(regenerated).toBe(committed);
  });

  it("T2: CardOut/FeedResponse field-name sets equal the artifact's properties keys", () => {
    const schema = readSchema();
    const source = readFileSync(GENERATED_PATH, "utf-8");

    const cardOutFields = extractInterfaceFieldNames(source, "CardOut").sort();
    const feedResponseFields = extractInterfaceFieldNames(
      source,
      "FeedResponse",
    ).sort();

    const expectedCardOutFields = Object.keys(
      schema.$defs.CardOut.properties,
    ).sort();
    const expectedFeedResponseFields = Object.keys(schema.properties).sort();

    expect(cardOutFields).toEqual(expectedCardOutFields);
    expect(feedResponseFields).toEqual(expectedFeedResponseFields);
  });

  it("T3: REQUIRED_STRING_FIELDS equals $defs.CardOut.required minus relevance", () => {
    const schema = readSchema();
    const expected = schema.$defs.CardOut.required
      .filter((field) => field !== "relevance")
      .slice()
      .sort();

    expect([...REQUIRED_STRING_FIELDS].sort()).toEqual(expected);
  });
});
