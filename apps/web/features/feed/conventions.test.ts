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

// ---------------------------------------------------------------------------
// feed-structure-refactor (AC1, AC2, AC3): layout, single public entry point,
// and WEB-1 across the new api/ components/ lib/ split. The pure checkers take
// (path, source) so each guard is also shown to fire on a violating source.
// ---------------------------------------------------------------------------
import { posix, relative, resolve, sep } from "node:path";

const WEB_ROOT = join(REPO_ROOT, "apps/web");
const FEED_DIR = join(FEATURES_DIR, "feed");
const FEED_REL = "features/feed";

const OUTSIDE_SKIP_DIRS = new Set([
  "node_modules", ".next", ".git", "test-results", "playwright-report",
  "blob-report", "specs", ".sdd", ".claude", "__baseline__", ".tmp",
]);

function walkSourceFiles(dir: string, skip: (full: string) => boolean): string[] {
  let results: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (OUTSIDE_SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (skip(full)) continue;
    if (statSync(full).isDirectory()) {
      results = results.concat(walkSourceFiles(full, skip));
    } else if (/\.(ts|tsx|mts|mjs)$/.test(entry)) {
      results.push(full);
    }
  }
  return results;
}

interface ImportRef {
  specifier: string;
  typeOnly: boolean;
}

function extractImports(source: string): ImportRef[] {
  const refs: ImportRef[] = [];
  const re =
    /\b(import\s+type|import|export)\s+(?:[^'";]*?\s+from\s+)?["']([^"']+)["']|\bimport\(\s*["']([^"']+)["']\s*\)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source)) !== null) {
    refs.push({
      specifier: match[2] ?? match[3],
      typeOnly: /^import\s+type$/.test(match[1] ?? ""),
    });
  }
  return refs;
}

/** Repo-relative-to-apps/web posix path a specifier points at, or null for a
 *  bare package. Handles `@/x`, relative paths and `..` (the barrel). */
function resolveInternal(fromFile: string, specifier: string): string | null {
  let abs: string;
  if (specifier.startsWith("@/")) abs = join(WEB_ROOT, specifier.slice(2));
  else if (specifier.startsWith(".")) abs = resolve(dirname(fromFile), specifier);
  else return null;
  return relative(WEB_ROOT, abs)
    .split(sep)
    .join(posix.sep)
    .replace(/\/$/, "")
    .replace(/\.(ts|tsx|mts|mjs)$/, "");
}

const isBarrel = (rel: string) => rel === FEED_REL || rel === `${FEED_REL}/index`;
const isApi = (rel: string) => rel === `${FEED_REL}/api` || rel.startsWith(`${FEED_REL}/api/`);
const isFeedSubfolder = (rel: string) =>
  rel.startsWith(`${FEED_REL}/`) && rel.slice(FEED_REL.length + 1).includes("/");

function deepImportViolations(file: string, source: string): string[] {
  return extractImports(source)
    .filter(({ specifier }) => {
      const rel = resolveInternal(file, specifier);
      return rel !== null && isFeedSubfolder(rel);
    })
    .map(({ specifier }) => `${file} deep-imports ${specifier}`);
}

function barrelSelfImportViolations(file: string, source: string): string[] {
  return extractImports(source)
    .filter(({ specifier }) => {
      const rel = resolveInternal(file, specifier);
      return rel !== null && isBarrel(rel);
    })
    .map(({ specifier }) => `${file} imports the feature barrel via ${specifier}`);
}

function clientImportViolations(file: string, source: string): string[] {
  if (!isUseClientModule(source)) return [];
  return extractImports(source)
    .filter(({ specifier }) => {
      const rel = resolveInternal(file, specifier);
      return rel !== null && (isBarrel(rel) || isApi(rel));
    })
    .map(({ specifier }) => `${file} is "use client" but imports ${specifier}`);
}

function valueImportOfApiViolations(file: string, source: string): string[] {
  return extractImports(source)
    .filter(({ specifier, typeOnly }) => {
      const rel = resolveInternal(file, specifier);
      return rel !== null && isApi(rel) && !typeOnly;
    })
    .map(({ specifier }) => `${file} value-imports ${specifier} (use "import type")`);
}

const FEED_SOURCE_FILES = walkTsFiles(FEED_DIR).filter((f) => f !== join(FEED_DIR, "index.ts"));
const OUTSIDE_FILES = walkSourceFiles(WEB_ROOT, (full) => full === FEED_DIR);
const FAKE = join(WEB_ROOT, "app/fake.tsx");

describe("feed-structure-refactor: layout and public entry point", () => {
  it("AC1: the feature root holds only index.ts, conventions.test.ts and api/ components/ lib/", () => {
    expect(readdirSync(FEED_DIR).sort()).toEqual([
      "api",
      "components",
      "conventions.test.ts",
      "index.ts",
      "lib",
    ]);
  });

  it("AC2: the barrel exports exactly FeedView, loadFeedState and parseFeedSearchParams", async () => {
    // Variable specifier: the barrel is resolved when this case runs, so a missing
    // index.ts fails this case only, not the whole file.
    const barrelPath = "./index";
    const barrel = await import(/* @vite-ignore */ barrelPath);
    expect(Object.keys(barrel).sort()).toEqual([
      "FeedView",
      "loadFeedState",
      "parseFeedSearchParams",
    ]);
  });

  it("AC2: nothing outside features/feed imports a path inside a feature sub-folder", () => {
    const violations = OUTSIDE_FILES.flatMap((file) =>
      deepImportViolations(file, readFileSync(file, "utf-8")),
    );
    expect(violations).toEqual([]);
  });

  it("AC2: no module inside features/feed imports the feature's own index", () => {
    const violations = FEED_SOURCE_FILES.flatMap((file) =>
      barrelSelfImportViolations(file, readFileSync(file, "utf-8")),
    );
    expect(violations).toEqual([]);
  });

  it("AC2 guard: flags alias, relative and aliased-barrel-subpath forms from outside, names the file", () => {
    expect(deepImportViolations(FAKE, "import { feedHref } from '@/features/feed/lib/href'")).toEqual([
      `${FAKE} deep-imports @/features/feed/lib/href`,
    ]);
    expect(deepImportViolations(FAKE, 'import x from "../features/feed/api/client"')).toHaveLength(1);
    expect(deepImportViolations(FAKE, "import { FeedView } from '@/features/feed'")).toEqual([]);
    expect(deepImportViolations(FAKE, "import { FeedView } from '../features/feed'")).toEqual([]);
    expect(deepImportViolations(FAKE, "import next from 'next/link'")).toEqual([]);
  });

  it("AC2 guard: flags a barrel import from inside the feature, including via '..'", () => {
    const inner = join(FEED_DIR, "components/x.tsx");
    expect(barrelSelfImportViolations(inner, "import { loadFeedState } from '..'")).toHaveLength(1);
    expect(barrelSelfImportViolations(inner, "import { a } from '@/features/feed'")).toHaveLength(1);
    expect(barrelSelfImportViolations(inner, "import { a } from '../lib/href'")).toEqual([]);
  });
});

describe("feed-structure-refactor: WEB-1 across api/ components/ lib/", () => {
  it('AC3: no "use client" module imports the barrel or anything under features/feed/api/', () => {
    const files = [...walkTsFiles(FEATURES_DIR), ...walkTsFiles(APP_DIR)];
    const violations = files.flatMap((file) =>
      clientImportViolations(file, readFileSync(file, "utf-8")),
    );
    expect(violations).toEqual([]);
  });

  it("AC3: components/ and lib/ import from api/ only with `import type`", () => {
    const files = [...walkTsFiles(join(FEED_DIR, "components")), ...walkTsFiles(join(FEED_DIR, "lib"))];
    const violations = files.flatMap((file) =>
      valueImportOfApiViolations(file, readFileSync(file, "utf-8")),
    );
    expect(violations).toEqual([]);
  });

  it('AC3 guard: flags a "use client" barrel/api import (incl. "..") and a value import of api/', () => {
    const comp = join(FEED_DIR, "components/x.tsx");
    const client = (body: string) => `"use client"\n${body}\n`;
    expect(clientImportViolations(comp, client("import { loadFeedState } from '..'"))).toHaveLength(1);
    expect(clientImportViolations(comp, client("import { a } from '@/features/feed'"))).toHaveLength(1);
    expect(clientImportViolations(comp, client("import { a } from '../api/load-feed-state'"))).toHaveLength(1);
    expect(clientImportViolations(comp, client("import { a } from '../lib/href'"))).toEqual([]);
    // Not a client module: the same import is fine here.
    expect(clientImportViolations(comp, "import { a } from '../api/client'")).toEqual([]);

    expect(valueImportOfApiViolations(comp, "import { FeedApiError } from '../api/client'")).toHaveLength(1);
    expect(valueImportOfApiViolations(comp, "import { type A } from '../api/client'")).toHaveLength(1);
    expect(valueImportOfApiViolations(comp, "import type { FeedErrorCode } from '../api/client'")).toEqual([]);
  });
});
