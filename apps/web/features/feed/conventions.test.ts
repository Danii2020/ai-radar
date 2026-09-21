/**
 * Spec: web-feed-ui
 * Covers: T29, T30, T31 (audit.md Test Coverage) / Guarantee 1, 4, 17 / AD-4
 * (contract.md) -- source-level guards for cross-cutting rules that no
 * single unit test can enforce: no client-side talking to `feed-api`, no
 * leaked infra literal, and API order is never re-sorted.
 *
 * Plain Node `fs` reads, no rendering, no network.
 *
 * NOTE: until Phase 2/3 land real files under apps/web/features/ and
 * apps/web/app/, this scan finds few or zero application files, so these
 * assertions trivially hold today. That is expected: unlike the other seven
 * spec test files (which redly fail on a missing module import), these are
 * directory-scan tests with nothing yet to violate the rule.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
// apps/web/features/feed -> repo root is four levels up.
const REPO_ROOT = join(here, "../../../..");
const FEATURES_DIR = join(REPO_ROOT, "apps/web/features");
const APP_DIR = join(REPO_ROOT, "apps/web/app");

function walkTsFiles(dir: string): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return [];
  }

  let results: string[] = [];
  for (const entry of entries) {
    if (entry === "node_modules") continue;
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      results = results.concat(walkTsFiles(full));
    } else if (
      /\.(ts|tsx)$/.test(entry) &&
      !entry.endsWith(".test.ts") &&
      !entry.endsWith(".test.tsx")
    ) {
      results.push(full);
    }
  }
  return results;
}

function extractImportSpecifiers(source: string): string[] {
  const specifiers: string[] = [];
  const importRegex = /import\s+(?:[^'"]*?\s+from\s+)?["']([^"']+)["']/g;
  let match: RegExpExecArray | null;
  while ((match = importRegex.exec(source)) !== null) {
    specifiers.push(match[1]);
  }
  return specifiers;
}

function isForbiddenClientImport(specifier: string): boolean {
  return /\/(client|load-feed)$/.test(specifier) || /^(client|load-feed)$/.test(specifier);
}

function isUseClientModule(source: string): boolean {
  const firstStatement = source
    .split("\n")
    .find((line) => line.trim().length > 0);
  if (firstStatement === undefined) return false;
  return /^["']use client["'];?$/.test(firstStatement.trim());
}

const applicationFiles = [...walkTsFiles(FEATURES_DIR), ...walkTsFiles(APP_DIR)];

describe("cross-cutting conventions", () => {
  it("T29: no NEXT_PUBLIC_ or execute-api literal anywhere in application code", () => {
    for (const file of applicationFiles) {
      const source = readFileSync(file, "utf-8");
      expect(source, `${file} contains a forbidden NEXT_PUBLIC_ literal`).not.toMatch(
        /NEXT_PUBLIC_/,
      );
      expect(source, `${file} contains a forbidden execute-api literal`).not.toMatch(
        /execute-api/,
      );
    }
  });

  it('T30: no "use client" module imports client.ts or load-feed.ts', () => {
    for (const file of applicationFiles) {
      const source = readFileSync(file, "utf-8");
      if (!isUseClientModule(source)) continue;

      const forbidden = extractImportSpecifiers(source).filter(
        isForbiddenClientImport,
      );
      expect(
        forbidden,
        `${file} is a "use client" module but imports: ${forbidden.join(", ")}`,
      ).toEqual([]);
    }
  });

  it("T31: no .sort( or .reverse( anywhere under features/feed", () => {
    const featureFiles = walkTsFiles(FEATURES_DIR);
    for (const file of featureFiles) {
      const source = readFileSync(file, "utf-8");
      expect(source, `${file} contains .sort(`).not.toContain(".sort(");
      expect(source, `${file} contains .reverse(`).not.toContain(".reverse(");
    }
  });
});
