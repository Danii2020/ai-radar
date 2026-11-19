// @vitest-environment node
/**
 * Spec: web-chat-response-cache, O1 (AC2, AC4, AC7, AC8). The cache module on its own: question
 * normalization, the keyed digest, the `CHAT_CACHE_TTL_S` setting, and the two stores (in-process
 * and Upstash over REST with a stubbed `fetch`). The handler wiring is in handle-chat-request.test.ts.
 * Fake credentials only; nothing here reaches the network.
 */
import { createHmac } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RateLimitConfig } from "./rate-limit-config";
import { cacheKey, normalizeQuestion, readCache, readCacheSettings, writeCache } from "./response-cache";

const STORE_URL = "https://store.fake.invalid";
const TOKEN = "fake-store-token-do-not-use-0001";
const SALT = "fake-salt-0123456789-abcdefghijklmnop-0001";
const SALT_2 = "other-fake-salt-9876543210-zyxwvutsrqpo";
const SOURCE = { n: 1, title: "A", url: "https://example.com/a", source: "Ex", published: null, score: 0.5 };
const DATA = { answer: "zq-answer-marker [1]", sources: [SOURCE] };

const memoryConfig = (salt: string | null = SALT): RateLimitConfig => ({
  burst: 5, burstWindowS: 60, daily: 20, globalDaily: 50, store: "memory", salt, restUrl: null, restToken: null,
});
const upstashConfig = (): RateLimitConfig => ({
  ...memoryConfig(), store: "upstash", restUrl: STORE_URL, restToken: TOKEN,
});

beforeEach(() => {
  vi.stubEnv("CHAT_CACHE_TTL_S", undefined);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("normalization (AC2)", () => {
  it.each([
    ["  What is   MCP? ", "what is mcp?"],
    ["what is mcp?", "what is mcp?"],
    ["What\tis\nMCP?", "what is mcp?"],
    ["what is mcp", "what is mcp"],
    ["What is MCP ?", "what is mcp ?"],
  ])("%j -> %j", (input, expected) => {
    expect(normalizeQuestion(input)).toBe(expected);
  });
});

describe("key (AC2, AC8)", () => {
  it("equivalent spellings share a key, other wording or punctuation does not", () => {
    const k = (q: string) => cacheKey(q, memoryConfig());
    expect(k("  What is   MCP? ")).toBe(k("what is mcp?"));
    expect(k("what is mcp")).not.toBe(k("what is mcp?"));
    expect(k("what is mcp?")).not.toBe(k("what is acp?"));
  });

  it("is a prefixed hex digest that never contains the question", () => {
    const key = cacheKey("zq-question-marker what is mcp?", memoryConfig());
    expect(key).toMatch(/^chat-cache:\{v1\}:[0-9a-f]{64}$/);
    expect(key).not.toContain("zq-question-marker");
  });

  it("changes with the salt and is separated from a plain keyed digest of the same text", () => {
    const q = "what is mcp?";
    expect(cacheKey(q, memoryConfig(SALT))).not.toBe(cacheKey(q, memoryConfig(SALT_2)));
    const plain = createHmac("sha256", SALT).update(normalizeQuestion(q)).digest("hex");
    expect(cacheKey(q, memoryConfig(SALT))).not.toContain(plain);
  });

  it("works with no configured salt (a per-process salt) and is stable within the process", () => {
    expect(cacheKey("what is mcp?", memoryConfig(null))).toBe(cacheKey("what is mcp?", memoryConfig(null)));
  });
});

describe("CHAT_CACHE_TTL_S (AC4, AC7)", () => {
  it.each([
    [undefined, { kind: "on", ttlS: 21600 }],
    ["", { kind: "on", ttlS: 21600 }],
    ["0", { kind: "off" }],
    ["60", { kind: "on", ttlS: 60 }],
    ["3600", { kind: "on", ttlS: 3600 }],
    ["86400", { kind: "on", ttlS: 86400 }],
    ["59", { kind: "invalid", variable: "CHAT_CACHE_TTL_S" }],
    ["86401", { kind: "invalid", variable: "CHAT_CACHE_TTL_S" }],
    ["abc", { kind: "invalid", variable: "CHAT_CACHE_TTL_S" }],
    ["1.5", { kind: "invalid", variable: "CHAT_CACHE_TTL_S" }],
    ["-60", { kind: "invalid", variable: "CHAT_CACHE_TTL_S" }],
  ])("%j", (value, expected) => {
    vi.stubEnv("CHAT_CACHE_TTL_S", value);
    expect(readCacheSettings()).toEqual(expected);
  });
});

describe("in-process store (AC4)", () => {
  it("returns what was written and a miss for an unknown key", async () => {
    const key = cacheKey("in-process one", memoryConfig());
    expect(await readCache(key, memoryConfig())).toEqual({ kind: "miss" });
    expect(await writeCache(key, DATA, 3600, memoryConfig())).toBe(true);
    expect(await readCache(key, memoryConfig())).toEqual({ kind: "hit", data: DATA });
  });

  it("expires after the lifetime and a rewrite refreshes it", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(Date.UTC(2026, 10, 18));
    const key = cacheKey("in-process expiry", memoryConfig());
    await writeCache(key, DATA, 100, memoryConfig());
    vi.setSystemTime(Date.UTC(2026, 10, 18) + 99_000);
    expect((await readCache(key, memoryConfig())).kind).toBe("hit");
    vi.setSystemTime(Date.UTC(2026, 10, 18) + 100_000);
    expect(await readCache(key, memoryConfig())).toEqual({ kind: "miss" });
    await writeCache(key, DATA, 100, memoryConfig());
    expect((await readCache(key, memoryConfig())).kind).toBe("hit");
  });
});

describe("Upstash store (AC4, AC7, AC8)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  const reply = (body: unknown, status = 200) =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status });
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("writes one SET with the value and an expiry, authorised with the token", async () => {
    fetchMock.mockResolvedValue(reply({ result: "OK" }));
    const key = cacheKey("upstash write", upstashConfig());
    expect(await writeCache(key, DATA, 3600, upstashConfig())).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url).href).toBe(new URL(STORE_URL).href);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).authorization).toBe(`Bearer ${TOKEN}`);
    expect(JSON.parse(init.body as string)).toEqual(["SET", key, JSON.stringify(DATA), "EX", "3600"]);
  });

  it("reads one GET and returns a hit for a stored value", async () => {
    fetchMock.mockResolvedValue(reply({ result: JSON.stringify(DATA) }));
    const key = cacheKey("upstash read", upstashConfig());
    expect(await readCache(key, upstashConfig())).toEqual({ kind: "hit", data: DATA });
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual(["GET", key]);
  });

  it("returns a miss for a null result", async () => {
    fetchMock.mockResolvedValue(reply({ result: null }));
    expect(await readCache("chat-cache:{v1}:x", upstashConfig())).toEqual({ kind: "miss" });
  });

  it.each([
    ["non-success status", () => reply({ error: "boom" }, 500)],
    ["not JSON", () => reply("<<not json")],
    ["error field", () => reply({ error: "WRONGTYPE" })],
    ["non-string result", () => reply({ result: 7 })],
    ["result that is not JSON", () => reply({ result: "plain text" })],
    ["result that is not a chat response", () => reply({ result: JSON.stringify({ answer: 1 }) })],
  ])("a read with a %s is an error", async (_name, makeReply) => {
    fetchMock.mockImplementation(async () => makeReply());
    expect(await readCache("chat-cache:{v1}:x", upstashConfig())).toEqual({ kind: "error" });
  });

  it("a read whose request throws is an error, and a write that fails returns false", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect(await readCache("chat-cache:{v1}:x", upstashConfig())).toEqual({ kind: "error" });
    expect(await writeCache("chat-cache:{v1}:x", DATA, 3600, upstashConfig())).toBe(false);
  });

  it("a write answered with an error or a non-OK result returns false", async () => {
    fetchMock.mockResolvedValueOnce(reply({ error: "ERR" }, 400));
    expect(await writeCache("chat-cache:{v1}:x", DATA, 3600, upstashConfig())).toBe(false);
    fetchMock.mockResolvedValueOnce(reply({ result: null }));
    expect(await writeCache("chat-cache:{v1}:x", DATA, 3600, upstashConfig())).toBe(false);
  });

  it("gives up after one second, for a read and for a write", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const read = readCache("chat-cache:{v1}:x", upstashConfig());
    await vi.advanceTimersByTimeAsync(1000);
    expect(await read).toEqual({ kind: "error" });
    const write = writeCache("chat-cache:{v1}:x", DATA, 3600, upstashConfig());
    await vi.advanceTimersByTimeAsync(1000);
    expect(await write).toBe(false);
  });
});
