/**
 * Spec: web-chat-ui, O7 (AC6, AC7). Architecture guards for the `features/chat` slice, the
 * chat counterpart of `features/feed/conventions.test.ts`: layout, one public barrel, no deep
 * imports from outside, WEB-1 for chat (no "use client" module reaches the barrel or `api/`),
 * `import type` only from `components/` and `lib/` into `api/`, and the credential env names read
 * only inside `api/`. `.sort(` / `.reverse(` under `features/` is already guarded by the feed
 * suite (T31), which walks all of `features/`.
 *
 * The pure checkers take (path, source) so each guard is also shown to fire on a violation.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, posix, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = join(here, "../..");
const CHAT_DIR = join(WEB_ROOT, "features/chat");
const CHAT_REL = "features/chat";

const SKIP_DIRS = new Set([
  "node_modules", ".next", ".git", "test-results", "playwright-report",
  "blob-report", "specs", ".sdd", ".claude", "__baseline__", ".tmp", "e2e",
]);

function walk(dir: string, skip: (full: string) => boolean = () => false): string[] {
  let results: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (skip(full)) continue;
    if (statSync(full).isDirectory()) results = results.concat(walk(full, skip));
    else if (/\.(ts|tsx|mts|mjs)$/.test(entry)) results.push(full);
  }
  return results;
}

const isTestFile = (file: string) => /\.test\.tsx?$/.test(file);

function isUseClientModule(source: string): boolean {
  const first = source.split("\n").find((line) => line.trim().length > 0);
  return first !== undefined && /^["']use client["'];?$/.test(first.trim());
}

interface ImportRef { specifier: string; typeOnly: boolean }

function extractImports(source: string): ImportRef[] {
  const refs: ImportRef[] = [];
  const re =
    /\b(import\s+type|import|export)\s+(?:[^'";]*?\s+from\s+)?["']([^"']+)["']|\bimport\(\s*["']([^"']+)["']\s*\)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(source)) !== null) {
    refs.push({ specifier: match[2] ?? match[3], typeOnly: /^import\s+type$/.test(match[1] ?? "") });
  }
  return refs;
}

function resolveInternal(fromFile: string, specifier: string): string | null {
  let abs: string;
  if (specifier.startsWith("@/")) abs = join(WEB_ROOT, specifier.slice(2));
  else if (specifier.startsWith(".")) abs = resolve(dirname(fromFile), specifier);
  else return null;
  return relative(WEB_ROOT, abs).split(sep).join(posix.sep).replace(/\/$/, "").replace(/\.(ts|tsx|mts|mjs)$/, "");
}

const isBarrel = (rel: string) => rel === CHAT_REL || rel === `${CHAT_REL}/index`;
const isApi = (rel: string) => rel === `${CHAT_REL}/api` || rel.startsWith(`${CHAT_REL}/api/`);
const isChatSubfolder = (rel: string) =>
  rel.startsWith(`${CHAT_REL}/`) && rel.slice(CHAT_REL.length + 1).includes("/");

function violations(
  file: string,
  source: string,
  match: (rel: string, ref: ImportRef) => boolean,
  message: string,
): string[] {
  return extractImports(source)
    .filter((ref) => {
      const rel = resolveInternal(file, ref.specifier);
      return rel !== null && match(rel, ref);
    })
    .map((ref) => `${file} ${message} ${ref.specifier}`);
}

const deepImports = (f: string, s: string) => violations(f, s, (rel) => isChatSubfolder(rel), "deep-imports");
const barrelSelfImports = (f: string, s: string) => violations(f, s, (rel) => isBarrel(rel), "imports the chat barrel via");
const clientImports = (f: string, s: string) =>
  isUseClientModule(s) ? violations(f, s, (rel) => isBarrel(rel) || isApi(rel), '"use client" imports') : [];
const valueImportsOfApi = (f: string, s: string) =>
  violations(f, s, (rel, ref) => isApi(rel) && !ref.typeOnly, 'value-imports (use "import type")');

const CREDENTIAL_ENV = /CHAT_API_(?:BASE_URL|ACCESS_KEY_ID|SECRET_ACCESS_KEY)/;
const credentialEnvReads = (file: string, source: string) =>
  CREDENTIAL_ENV.test(source) ? [`${file} reads a CHAT_API_* variable outside features/chat/api/`] : [];

const read = (file: string) => readFileSync(file, "utf-8");
const chatSource = walk(CHAT_DIR).filter((f) => !isTestFile(f));
const outsideChat = walk(WEB_ROOT, (full) => full === CHAT_DIR);
const FAKE_OUTSIDE = join(WEB_ROOT, "app/fake.tsx");
const FAKE_COMPONENT = join(CHAT_DIR, "components/x.tsx");

describe("web-chat-ui: layout and public entry point", () => {
  it("the feature root holds only index.ts, conventions.test.ts and api/ components/ lib/", () => {
    expect(readdirSync(CHAT_DIR).sort()).toEqual(["api", "components", "conventions.test.ts", "index.ts", "lib"]);
  });

  it("the barrel exports exactly ChatWidget and handleChatRequest", async () => {
    const barrelPath = "./index"; // variable specifier: a missing index.ts fails this case only
    const barrel = await import(/* @vite-ignore */ barrelPath);
    expect(Object.keys(barrel).sort()).toEqual(["ChatWidget", "handleChatRequest"]);
  });

  it("nothing outside features/chat imports a path inside a chat sub-folder", () => {
    expect(outsideChat.flatMap((f) => deepImports(f, read(f)))).toEqual([]);
  });

  it("no module inside features/chat imports the feature's own index", () => {
    const files = chatSource.filter((f) => f !== join(CHAT_DIR, "index.ts"));
    expect(files.flatMap((f) => barrelSelfImports(f, read(f)))).toEqual([]);
  });

  it("the feed page mounts the widget from the chat barrel", () => {
    expect(read(join(WEB_ROOT, "app/page.tsx"))).toMatch(/from\s+["']@\/features\/chat["']/);
  });
});

describe("web-chat-ui: the key and the backend stay on the server (WEB-1 extended)", () => {
  it('no "use client" module imports the chat barrel or anything under features/chat/api/', () => {
    const files = [...chatSource, ...outsideChat.filter((f) => !isTestFile(f))];
    expect(files.flatMap((f) => clientImports(f, read(f)))).toEqual([]);
  });

  it("components/ and lib/ import from api/ only with `import type`", () => {
    const files = chatSource.filter((f) => /\/(components|lib)\//.test(f));
    expect(files.flatMap((f) => valueImportsOfApi(f, read(f)))).toEqual([]);
  });

  it("the CHAT_API_* credential variables are named only inside features/chat/api/", () => {
    const files = walk(WEB_ROOT, (full) => full === join(CHAT_DIR, "api")).filter((f) => !isTestFile(f));
    expect(files.flatMap((f) => credentialEnvReads(f, read(f)))).toEqual([]);
  });
});

describe("web-chat-ui: the guards fire on violations", () => {
  const client = (body: string) => `"use client"\n${body}\n`;

  it("deep-import and barrel-self-import", () => {
    expect(deepImports(FAKE_OUTSIDE, "import { x } from '@/features/chat/api/backend'")).toHaveLength(1);
    expect(deepImports(FAKE_OUTSIDE, "import { ChatWidget } from '@/features/chat'")).toEqual([]);
    expect(barrelSelfImports(FAKE_COMPONENT, "import { a } from '..'")).toHaveLength(1);
    expect(barrelSelfImports(FAKE_COMPONENT, "import { a } from '../lib/history'")).toEqual([]);
  });

  it('"use client" barrel/api import and value import of api/', () => {
    expect(clientImports(FAKE_COMPONENT, client("import { a } from '@/features/chat'"))).toHaveLength(1);
    expect(clientImports(FAKE_COMPONENT, client("import { a } from '../api/backend'"))).toHaveLength(1);
    expect(clientImports(FAKE_COMPONENT, client("import { a } from '../lib/history'"))).toEqual([]);
    expect(clientImports(FAKE_COMPONENT, "import { a } from '../api/backend'")).toEqual([]);
    expect(valueImportsOfApi(FAKE_COMPONENT, "import { a } from '../api/types'")).toHaveLength(1);
    expect(valueImportsOfApi(FAKE_COMPONENT, "import type { A } from '../api/types'")).toEqual([]);
  });

  it("credential env names", () => {
    expect(credentialEnvReads(FAKE_OUTSIDE, "process.env.CHAT_API_SECRET_ACCESS_KEY")).toHaveLength(1);
    expect(credentialEnvReads(FAKE_OUTSIDE, "const x = 1")).toEqual([]);
  });
});
