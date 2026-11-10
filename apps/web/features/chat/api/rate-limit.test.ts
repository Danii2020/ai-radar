// @vitest-environment node
/**
 * Spec: web-chat-visitor-rate-limit, O1 to O4 (AC1 to AC11, AC13). The per-visitor and global
 * limit inside `handleChatRequest(request: Request): Promise<Response>`, observed only through
 * the handler: status, body, headers, console lines, and the calls made to a stubbed global
 * `fetch` (routed by URL to a fake Upstash REST store and a fake chat backend).
 *
 * Contract the tests fix (execution-plan.md, binding constraints):
 *   - visitor = first present of x-vercel-forwarded-for / x-real-ip / x-forwarded-for;
 *   - 429 {"error":"rate_limited"} + Retry-After; store failure or bad config -> 503 unavailable;
 *   - the Upstash store gets ONE `POST <REST URL>` per check, body = JSON array
 *     ["EVAL", script, numkeys, ...keys, ...args], `Authorization: Bearer <token>`; the reply
 *     `{"result": 0}` means admitted and `{"result": n}` with n in 1..7 means limited
 *     (bitmask 1 burst, 2 daily, 4 global). Anything else is a store failure.
 *
 * Every test loads a fresh copy of the handler module, so the in-process store starts empty.
 * Time is driven with a faked Date only (timers stay real). Fake credentials only; no test
 * reaches the network.
 */
import { createHmac } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const BASE_URL = "https://chat-api.fake.invalid";
const STORE_URL = "https://store.fake.invalid";
const TOKEN = "fake-store-token-do-not-use-0001";
const SALT = "fake-salt-0123456789-abcdefghijklmnop-0001";
const SALT_2 = "other-fake-salt-9876543210-zyxwvutsrqpo";
const ANSWER = { answer: "an answer [1]", sources: [] };
const DAY = Date.UTC(2026, 10, 5); // a multiple of 86,400 s, so also of every window below

const ALL_ENV = [
  "CHAT_RATE_LIMIT_BURST", "CHAT_RATE_LIMIT_BURST_WINDOW_S", "CHAT_RATE_LIMIT_DAILY",
  "CHAT_RATE_LIMIT_GLOBAL_DAILY", "CHAT_RATE_LIMIT_SALT", "CHAT_RATE_LIMIT_STORE",
  "KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "VERCEL",
];
const UPSTASH_ENV = {
  CHAT_RATE_LIMIT_STORE: "upstash", KV_REST_API_URL: STORE_URL, KV_REST_API_TOKEN: TOKEN,
  CHAT_RATE_LIMIT_SALT: SALT,
};

type Handler = (request: Request) => Promise<Response>;
let handle: Handler;
let fetchMock: ReturnType<typeof vi.fn>;
let storeReply: () => Response | Promise<Response>;
let logs: { method: string; text: string }[];

function env(values: Record<string, string | undefined>) {
  for (const [name, value] of Object.entries(values)) vi.stubEnv(name, value);
}
const at = (ms: number) => vi.setSystemTime(DAY + ms);
const SEC = 1000;
const NOON = 12 * 3600 * SEC;

const urlOf = (input: unknown): string => (input instanceof Request ? input.url : String(input));
const storeCalls = () => fetchMock.mock.calls.filter(([input]) => urlOf(input).startsWith(STORE_URL));
const backendCalls = () => fetchMock.mock.calls.filter(([input]) => urlOf(input).startsWith(BASE_URL));

beforeEach(async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  at(NOON);
  fetchMock = vi.fn(async (input: unknown) => {
    if (urlOf(input).startsWith(STORE_URL)) return storeReply();
    return new Response(JSON.stringify(ANSWER), { status: 200, headers: { "content-type": "application/json" } });
  });
  storeReply = () => new Response(JSON.stringify({ result: 0 }), { status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  for (const name of ALL_ENV) vi.stubEnv(name, undefined);
  env({
    CHAT_API_BASE_URL: BASE_URL, CHAT_API_ACCESS_KEY_ID: "FAKE-TEST-KEY-ID-0001",
    CHAT_API_SECRET_ACCESS_KEY: "fake-secret-value-do-not-use-0001",
  });
  logs = [];
  for (const method of ["log", "info", "warn", "error"] as const) {
    vi.spyOn(console, method).mockImplementation((...args: unknown[]) => {
      logs.push({ method, text: args.map(String).join(" ") });
    });
  }
  vi.resetModules();
  handle = (await import("./handle-chat-request")).handleChatRequest;
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

function req(headers: Record<string, string> = {}, body: unknown = { question: "what is new?", history: [] }) {
  return new Request("http://localhost/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}
const ask = (ip: string, body?: unknown) => handle(req({ "x-forwarded-for": ip }, body));
const status = async (ip: string) => (await ask(ip)).status;
const lastLine = () => JSON.parse(logs[logs.length - 1].text);

async function expectLimited(res: Response) {
  expect(res.status).toBe(429);
  expect(await res.text()).toBe('{"error":"rate_limited"}');
}

// ---------------------------------------------------------------- AC1
describe("burst limit per visitor (AC1)", () => {
  it("6 valid requests in one window: 5 answers, then 429 rate_limited; the backend is called 5 times", async () => {
    const results: number[] = [];
    for (let i = 0; i < 5; i++) results.push(await status("203.0.113.10"));
    expect(results).toEqual([200, 200, 200, 200, 200]);
    await expectLimited(await ask("203.0.113.10"));
    expect(backendCalls()).toHaveLength(5);
  });

  it("the first request of the next window is admitted; the boundary is a multiple of the window", async () => {
    at(NOON + 59_999);
    for (let i = 0; i < 5; i++) expect(await status("203.0.113.11")).toBe(200);
    expect(await status("203.0.113.11")).toBe(429);
    at(NOON + 60_000);
    expect(await status("203.0.113.11")).toBe(200);
  });

  it("requests at t = k*W - 1 ms and k*W fall in different windows (custom W)", async () => {
    env({ CHAT_RATE_LIMIT_BURST: "1", CHAT_RATE_LIMIT_BURST_WINDOW_S: "10" });
    at(NOON + 9_999);
    expect(await status("203.0.113.12")).toBe(200);
    at(NOON + 10_000);
    expect(await status("203.0.113.12")).toBe(200);
    expect(await status("203.0.113.12")).toBe(429);
  });

  it("CHAT_RATE_LIMIT_BURST overrides the default of 5", async () => {
    env({ CHAT_RATE_LIMIT_BURST: "2" });
    expect([await status("203.0.113.13"), await status("203.0.113.13"), await status("203.0.113.13")]).toEqual([200, 200, 429]);
  });

  it("the Upstash store reports the burst limit as exhausted: 429 rate_limited from one store call, no backend call", async () => {
    env(UPSTASH_ENV);
    storeReply = () => new Response(JSON.stringify({ result: 1 }), { status: 200 });
    await expectLimited(await ask("203.0.113.14"));
    expect(storeCalls()).toHaveLength(1);
    expect(backendCalls()).toHaveLength(0);
    expect(lastLine()).toMatchObject({ outcome: "rate_limited", limit: "burst" });
  });
});

// ---------------------------------------------------------------- AC2
describe("daily cap per visitor (AC2)", () => {
  beforeEach(() => env({ CHAT_RATE_LIMIT_BURST: "1000" }));

  it("20 admitted turns, the 21st is 429 until 00:00 UTC, then admitted", async () => {
    for (let i = 0; i < 20; i++) expect(await status("203.0.113.20")).toBe(200);
    await expectLimited(await ask("203.0.113.20"));
    expect(lastLine()).toMatchObject({ outcome: "rate_limited", limit: "daily" });
    at(24 * 3600 * SEC - 1);
    expect(await status("203.0.113.20")).toBe(429);
    at(24 * 3600 * SEC);
    expect(await status("203.0.113.20")).toBe(200);
  });

  it("a request at 23:59:59 and one at 00:00:00 count in different days", async () => {
    at(24 * 3600 * SEC - 1000);
    for (let i = 0; i < 20; i++) expect(await status("203.0.113.21")).toBe(200);
    at(24 * 3600 * SEC);
    expect(await status("203.0.113.21")).toBe(200);
  });

  it("CHAT_RATE_LIMIT_DAILY overrides the default of 20", async () => {
    env({ CHAT_RATE_LIMIT_DAILY: "3" });
    const out = [];
    for (let i = 0; i < 4; i++) out.push(await status("203.0.113.22"));
    expect(out).toEqual([200, 200, 200, 429]);
  });
});

// ---------------------------------------------------------------- AC3
describe("global daily ceiling (AC3)", () => {
  it("ceiling 3: three visitors admitted once each, a fourth is 429 (limit global); admitted the next UTC day", async () => {
    env({ CHAT_RATE_LIMIT_GLOBAL_DAILY: "3" });
    for (const ip of ["198.51.100.1", "198.51.100.2", "198.51.100.3"]) expect(await status(ip)).toBe(200);
    await expectLimited(await ask("198.51.100.4"));
    expect(lastLine()).toMatchObject({ outcome: "rate_limited", limit: "global" });
    at(24 * 3600 * SEC);
    expect(await status("198.51.100.4")).toBe(200);
  });

  it("the default ceiling is 50: the 51st turn across 51 visitors is 429", async () => {
    for (let i = 1; i <= 50; i++) expect(await status(`198.51.100.${i}`)).toBe(200);
    expect(await status("198.51.101.1")).toBe(429);
    expect(backendCalls()).toHaveLength(50);
  });
});

// ---------------------------------------------------------------- AC4
describe("isolation and free rejections (AC4)", () => {
  it("A at the limit does not change B; A's 50 further rejections leave B admitted", async () => {
    for (let i = 0; i < 5; i++) await ask("192.0.2.1");
    expect(await status("192.0.2.1")).toBe(429);
    expect(await status("192.0.2.2")).toBe(200);
    for (let i = 0; i < 50; i++) expect(await status("192.0.2.1")).toBe(429);
    expect(await status("192.0.2.2")).toBe(200);
  });

  it("rejections do not count toward the global ceiling (ceiling 7)", async () => {
    env({ CHAT_RATE_LIMIT_GLOBAL_DAILY: "7" });
    for (let i = 0; i < 5; i++) expect(await status("192.0.2.1")).toBe(200);
    expect(await status("192.0.2.2")).toBe(200); // 6 admitted
    for (let i = 0; i < 50; i++) expect(await status("192.0.2.1")).toBe(429); // burst-limited
    expect(await status("192.0.2.2")).toBe(200); // 7th admitted: rejections were free
    await expectLimited(await ask("192.0.2.2"));
    expect(lastLine()).toMatchObject({ limit: "global" });
  });

  it("invalid bodies, invalid questions and missing configuration use up no allowance", async () => {
    for (let i = 0; i < 4; i++) {
      expect((await ask("192.0.2.3", "<<not json")).status).toBe(400);
      expect((await ask("192.0.2.3", { question: "   ", history: [] })).status).toBe(400);
      expect((await ask("192.0.2.3", { question: "q".repeat(1001), history: [] })).status).toBe(400);
    }
    vi.stubEnv("CHAT_API_BASE_URL", "");
    for (let i = 0; i < 4; i++) expect((await ask("192.0.2.3")).status).toBe(503);
    vi.stubEnv("CHAT_API_BASE_URL", BASE_URL);
    for (let i = 0; i < 5; i++) expect(await status("192.0.2.3")).toBe(200);
    expect(await status("192.0.2.3")).toBe(429);
  });

  it("a turn whose backend call fails (502) still counts", async () => {
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ error: "upstream_failure" }), { status: 502 }));
    for (let i = 0; i < 5; i++) expect(await status("192.0.2.4")).toBe(502);
    await expectLimited(await ask("192.0.2.4"));
    expect(backendCalls()).toHaveLength(5);
  });

  it("a backend 429 still maps to busy, with no Retry-After", async () => {
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ error: "throttled" }), { status: 429 }));
    const res = await ask("192.0.2.5");
    expect(res.status).toBe(429);
    expect(await res.text()).toBe('{"error":"busy"}');
    expect(res.headers.get("retry-after")).toBeNull();
  });

  it("a rejected check ends there: one store call, no second call, no backend call", async () => {
    env(UPSTASH_ENV);
    storeReply = () => new Response(JSON.stringify({ result: 2 }), { status: 200 });
    await expectLimited(await ask("192.0.2.6"));
    expect(storeCalls()).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------- AC5
describe("the check sits after validation and config, before the one backend call (AC5)", () => {
  beforeEach(() => env(UPSTASH_ENV));

  it("an invalid request makes 0 store calls", async () => {
    expect((await ask("192.0.2.7", { question: "", history: [] })).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("missing CHAT_API_* configuration makes 0 store calls", async () => {
    vi.stubEnv("CHAT_API_ACCESS_KEY_ID", "");
    expect((await ask("192.0.2.8")).status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an admitted request makes exactly one store call, then exactly one backend call", async () => {
    expect(await status("192.0.2.9")).toBe(200);
    expect(storeCalls()).toHaveLength(1);
    expect(backendCalls()).toHaveLength(1);
    const order = fetchMock.mock.calls.map(([input]) => urlOf(input).startsWith(STORE_URL));
    expect(order).toEqual([true, false]);
  });

  it("a limited request: one store call, none to the backend", async () => {
    storeReply = () => new Response(JSON.stringify({ result: 4 }), { status: 200 });
    await expectLimited(await ask("192.0.2.9"));
    expect(storeCalls()).toHaveLength(1);
    expect(backendCalls()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------- AC6
describe("limited response contract (AC6)", () => {
  async function limited(ip = "192.0.2.30") {
    for (let i = 0; i < 5; i++) await ask(ip);
    return ask(ip);
  }

  it("429, exact body, existing headers, and Retry-After = whole seconds to the burst window end", async () => {
    at(NOON + 10_400);
    const res = await limited();
    expect(res.status).toBe(429);
    expect(await res.text()).toBe('{"error":"rate_limited"}');
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("retry-after")).toMatch(/^[1-9][0-9]*$/);
    expect(res.headers.get("retry-after")).toBe("50");
  });

  it("is 1 when 0.2 s remain in the window", async () => {
    at(NOON + 59_800);
    expect((await limited()).headers.get("retry-after")).toBe("1");
  });

  it("the daily cap's Retry-After is the time to the next 00:00 UTC", async () => {
    env({ CHAT_RATE_LIMIT_BURST: "1000", CHAT_RATE_LIMIT_DAILY: "2" });
    at(NOON + 10_400);
    await ask("192.0.2.31");
    await ask("192.0.2.31");
    const res = await ask("192.0.2.31");
    expect(res.headers.get("retry-after")).toBe(String(Math.ceil((12 * 3600 * SEC - 10_400) / SEC)));
  });

  it("the global ceiling's Retry-After is the time to the next 00:00 UTC", async () => {
    env({ CHAT_RATE_LIMIT_GLOBAL_DAILY: "1" });
    at(NOON + 10_400);
    await ask("192.0.2.32");
    const res = await ask("192.0.2.33");
    await expectLimited(res);
    expect(res.headers.get("retry-after")).toBe(String(Math.ceil((12 * 3600 * SEC - 10_400) / SEC)));
  });

  it("with burst and daily both exhausted, Retry-After is the later reset and the log names daily", async () => {
    env({ CHAT_RATE_LIMIT_DAILY: "5" });
    at(NOON + 10_400);
    const res = await limited("192.0.2.34");
    expect(res.headers.get("retry-after")).toBe(String(Math.ceil((12 * 3600 * SEC - 10_400) / SEC)));
    expect(lastLine()).toMatchObject({ limit: "daily" });
  });

  it("with global, daily and burst all exhausted, the log names global", async () => {
    env({ CHAT_RATE_LIMIT_DAILY: "5", CHAT_RATE_LIMIT_GLOBAL_DAILY: "5" });
    await limited("192.0.2.35");
    expect(lastLine()).toMatchObject({ limit: "global" });
  });

  it("the body is identical whichever limit fired", async () => {
    const bodies = new Set<string>();
    bodies.add(await (await limited("192.0.2.36")).text()); // burst
    env({ CHAT_RATE_LIMIT_BURST: "1000", CHAT_RATE_LIMIT_DAILY: "1" });
    await ask("192.0.2.37");
    bodies.add(await (await ask("192.0.2.37")).text()); // daily
    env({ CHAT_RATE_LIMIT_DAILY: "1000", CHAT_RATE_LIMIT_GLOBAL_DAILY: "1" });
    bodies.add(await (await ask("192.0.2.38")).text()); // global
    expect([...bodies]).toEqual(['{"error":"rate_limited"}']);
  });

  it("503 unavailable replies carry no Retry-After", async () => {
    env({ CHAT_RATE_LIMIT_DAILY: "abc" });
    const res = await ask("192.0.2.39");
    expect(res.status).toBe(503);
    expect(res.headers.get("retry-after")).toBeNull();
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.get("cache-control")).toBe("no-store");
  });
});

// ---------------------------------------------------------------- AC7
describe("visitor identity (AC7)", () => {
  /** True when a second request with headers B lands in the bucket headers A already used. */
  async function sameVisitor(a: Record<string, string>, b: Record<string, string>) {
    env({ CHAT_RATE_LIMIT_BURST: "1" });
    expect((await handle(req(a))).status).toBe(200);
    const second = (await handle(req(b))).status;
    expect([200, 429]).toContain(second);
    return second === 429;
  }

  it.each([
    ["x-vercel-forwarded-for beats x-real-ip and x-forwarded-for", { "x-vercel-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2", "x-forwarded-for": "3.3.3.3" }, { "x-vercel-forwarded-for": "1.1.1.1" }, true],
    ["x-real-ip beats x-forwarded-for", { "x-real-ip": "2.2.2.2", "x-forwarded-for": "3.3.3.3" }, { "x-real-ip": "2.2.2.2" }, true],
    ["a lower-precedence header does not identify the visitor when a higher one is present", { "x-vercel-forwarded-for": "1.1.1.1" }, { "x-forwarded-for": "1.1.1.1", "x-real-ip": "9.9.9.9" }, false],
    ["the first comma entry is used, trimmed", { "x-forwarded-for": " 203.0.113.5 , 10.0.0.1" }, { "x-forwarded-for": "203.0.113.5" }, true],
    ["an IPv4 address is used whole", { "x-forwarded-for": "203.0.113.5" }, { "x-forwarded-for": "203.0.113.6" }, false],
    ["two addresses in one IPv6 /64 share a bucket", { "x-forwarded-for": "2001:db8:1:2::a" }, { "x-forwarded-for": "2001:db8:1:2::b" }, true],
    ["a different /64 does not", { "x-forwarded-for": "2001:db8:1:2::a" }, { "x-forwarded-for": "2001:db8:1:3::a" }, false],
    ["compressed and expanded forms of one /64 agree (case-insensitive)", { "x-forwarded-for": "2001:db8:1:2::b" }, { "x-forwarded-for": "2001:0DB8:0001:0002:0:0:0:ffff" }, true],
    ["an IPv4-mapped IPv6 address counts as that IPv4", { "x-forwarded-for": "203.0.113.5" }, { "x-forwarded-for": "::ffff:203.0.113.5" }, true],
    ["a cookie does not change the visitor", { "x-forwarded-for": "203.0.113.5", cookie: "a=1" }, { "x-forwarded-for": "203.0.113.5", cookie: "a=2" }, true],
  ])("%s", async (_name, a, b, expected) => {
    expect(await sameVisitor(a, b)).toBe(expected);
  });

  it.each([
    ["garbage", { "x-forwarded-for": "garbage" }],
    ["an empty value", { "x-forwarded-for": "" }],
    ["an IPv6 zone id", { "x-forwarded-for": "fe80::1%eth0" }],
    ["an out-of-range IPv4", { "x-forwarded-for": "999.1.1.1" }],
  ])("%s falls in the shared unknown bucket with a request that has no header at all", async (_name, headers) => {
    expect(await sameVisitor({}, headers)).toBe(true);
  });

  it("the unknown bucket is not any real address", async () => {
    expect(await sameVisitor({}, { "x-forwarded-for": "203.0.113.5" })).toBe(false);
  });

  it("an unknown visitor differing only in a cookie shares the unknown bucket", async () => {
    expect(await sameVisitor({ cookie: "sid=1" }, { cookie: "sid=2" })).toBe(true);
  });

  it("a body field does not change the visitor", async () => {
    env({ CHAT_RATE_LIMIT_BURST: "1" });
    const h = { "x-forwarded-for": "203.0.113.5" };
    expect((await handle(req(h, { question: "q?", history: [], visitor: "a" }))).status).toBe(200);
    expect((await handle(req(h, { question: "q?", history: [], visitor: "b" }))).status).toBe(429);
  });
});

// ---------------------------------------------------------------- AC8
describe("nothing identifying is kept or logged (AC8)", () => {
  const IP = "203.0.113.77";
  const MARKER = "zq-marker";
  const digest = (salt: string) => createHmac("sha256", salt).update(IP).digest("hex");

  async function storeText(i = 0) {
    expect(storeCalls().length).toBeGreaterThan(i); // red until the limiter calls the store
    const [input, init] = storeCalls()[i] as [unknown, RequestInit | undefined];
    const r = input instanceof Request ? input : new Request(String(input), init);
    return { url: r.url, headers: [...r.headers.entries()].join("\n"), body: await r.text() };
  }

  async function runVariant(variant: "admitted" | "limited" | "failure" | "config") {
    env(UPSTASH_ENV);
    if (variant === "limited") storeReply = () => new Response('{"result":1}', { status: 200 });
    if (variant === "failure") storeReply = () => { throw new TypeError(`connect ECONNREFUSED ${STORE_URL}`); };
    if (variant === "config") vi.stubEnv("CHAT_RATE_LIMIT_SALT", "too-short");
    const res = await ask(IP, { question: `${MARKER}: anything`, history: [] });
    return { res, text: await res.text() };
  }

  it.each(["admitted", "limited", "failure", "config"] as const)(
    "%s: no IP, digest, salt, token, store URL or question in any console line or response body",
    async (variant) => {
      const { text } = await runVariant(variant);
      const consoleText = logs.map((l) => l.text).join("\n");
      for (const secret of [IP, MARKER, SALT, TOKEN, STORE_URL, "store.fake.invalid", digest(SALT)]) {
        expect(consoleText).not.toContain(secret);
        expect(text).not.toContain(secret);
      }
    },
  );

  it("the store receives the digest (64 hex, HMAC-SHA-256 of the visitor key with the salt) and never the IP or the question", async () => {
    await runVariant("admitted");
    const sent = await storeText();
    expect(new URL(sent.url).href).toBe(new URL(STORE_URL).href);
    for (const part of [sent.url, sent.headers, sent.body]) {
      expect(part).not.toContain(IP);
      expect(part).not.toContain(MARKER);
    }
    expect(sent.headers).toContain(`Bearer ${TOKEN}`);
    expect(sent.body).toMatch(/[0-9a-f]{64}/);
    expect(sent.body).toContain(digest(SALT));
  });

  it("changing CHAT_RATE_LIMIT_SALT changes the digest the store sees", async () => {
    await runVariant("admitted");
    vi.stubEnv("CHAT_RATE_LIMIT_SALT", SALT_2);
    await ask(IP);
    const [first, second] = [await storeText(0), await storeText(1)];
    expect(first.body).toContain(digest(SALT));
    expect(second.body).toContain(digest(SALT_2));
    expect(second.body).not.toContain(digest(SALT));
  });

  it("sends one EVAL as a JSON array whose expiries are at most 2 windows (burst) and 48 h (daily, global)", async () => {
    await runVariant("admitted");
    const command = JSON.parse((await storeText()).body) as unknown[];
    expect(command[0]).toBe("EVAL");
    expect(String(command[1])).toMatch(/expire/i);
    const numbers = command.slice(3).map((v) => Number(v)).filter((n) => Number.isFinite(n));
    expect(numbers.every((n) => n <= 172_800)).toBe(true);
    expect(numbers.some((n) => n >= 60 && n <= 120)).toBe(true);
    expect(numbers.some((n) => n >= 86_400 && n <= 172_800)).toBe(true);
  });

  it("a custom burst window shortens the burst expiry to at most 2 windows", async () => {
    env({ CHAT_RATE_LIMIT_BURST_WINDOW_S: "10" });
    await runVariant("admitted");
    const command = JSON.parse((await storeText()).body) as unknown[];
    const numbers = command.slice(3).map((v) => Number(v)).filter((n) => Number.isFinite(n));
    expect(numbers.some((n) => n >= 10 && n <= 20)).toBe(true);
  });
});

// ---------------------------------------------------------------- AC9
describe("fail closed (AC9)", () => {
  beforeEach(() => env(UPSTASH_ENV));

  const FAILURES: [string, () => Response | Promise<Response>][] = [
    ["fetch rejects (connection refused)", () => { throw new TypeError("fetch failed: connect ECONNREFUSED"); }],
    ["a 500 status", () => new Response("oops", { status: 500 })],
    ["a 200 with a non-JSON body", () => new Response("<<not json", { status: 200 })],
    ["a 200 with an error object", () => new Response('{"error":"ERR something"}', { status: 200 })],
    ["a 200 with a string result", () => new Response('{"result":"x"}', { status: 200 })],
    ["a 200 with an out-of-range integer", () => new Response('{"result":99}', { status: 200 })],
    ["a 200 with a negative integer", () => new Response('{"result":-1}', { status: 200 })],
    ["a 200 with no result", () => new Response("{}", { status: 200 })],
  ];

  it.each(FAILURES)("%s -> 503 unavailable, no backend call, one store call, one limiter_unavailable line", async (_name, reply) => {
    storeReply = reply;
    const res = await ask("192.0.2.50");
    expect(res.status).toBe(503);
    expect(await res.text()).toBe('{"error":"unavailable"}');
    expect(backendCalls()).toHaveLength(0);
    expect(storeCalls()).toHaveLength(1);
    expect(logs).toHaveLength(1);
    expect(lastLine()).toMatchObject({ event: "chat_request", outcome: "limiter_unavailable" });
    expect(logs[0].method).toBe("error");
  });

  it("no reply within 1 second -> 503 unavailable via the abort signal", async () => {
    fetchMock.mockImplementation(async (input: unknown, init?: RequestInit) => {
      if (!urlOf(input).startsWith(STORE_URL)) return new Response(JSON.stringify(ANSWER), { status: 200 });
      const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
      return new Promise<Response>((_resolve, reject) => {
        if (!signal) return; // no signal passed: this test then times out, which is the failure
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    });
    vi.useRealTimers();
    const started = Date.now();
    const res = await ask("192.0.2.51");
    const elapsed = Date.now() - started;
    expect(res.status).toBe(503);
    expect(await res.text()).toBe('{"error":"unavailable"}');
    expect(elapsed).toBeGreaterThanOrEqual(900);
    expect(elapsed).toBeLessThan(2500);
    expect(backendCalls()).toHaveLength(0);
    expect(lastLine()).toMatchObject({ outcome: "limiter_unavailable" });
  }, 8000);
});

// ---------------------------------------------------------------- AC10
describe("configuration is checked per request and fails safe (AC10)", () => {
  async function expectInvalid(variable: string, value?: string) {
    const res = await ask("192.0.2.60");
    expect(res.status).toBe(503);
    expect(await res.text()).toBe('{"error":"unavailable"}');
    expect(backendCalls()).toHaveLength(0);
    expect(storeCalls()).toHaveLength(0);
    expect(logs).toHaveLength(1);
    expect(lastLine()).toMatchObject({ event: "chat_request", outcome: "limiter_config_invalid", variable });
    expect(logs[0].method).toBe("error");
    if (value) {
      // duration_ms is a number and may hold any digits; every other field must not hold the value
      const rest: Record<string, unknown> = { ...lastLine() };
      delete rest.duration_ms;
      expect(JSON.stringify(rest)).not.toContain(value);
    }
  }

  const LIMITS: [string, string][] = [
    ["CHAT_RATE_LIMIT_BURST", "1000001"],
    ["CHAT_RATE_LIMIT_BURST_WINDOW_S", "86401"],
    ["CHAT_RATE_LIMIT_DAILY", "1000001"],
    ["CHAT_RATE_LIMIT_GLOBAL_DAILY", "1000001"],
  ];

  describe.each(LIMITS)("%s", (name, aboveMax) => {
    it.each(["abc", "-1", "0", "1.5", "1e3", aboveMax])("%s -> limiter_config_invalid naming the variable, never the value", async (value) => {
      env({ [name]: value });
      await expectInvalid(name, value);
    });

    it("blank or whitespace uses the default", async () => {
      env({ [name]: "   " });
      expect(await status("192.0.2.61")).toBe(200);
      env({ [name]: "" });
      expect(await status("192.0.2.61")).toBe(200);
    });
  });

  it("the largest allowed values are accepted (and surrounding whitespace is trimmed)", async () => {
    env({ CHAT_RATE_LIMIT_BURST: " 1000000 ", CHAT_RATE_LIMIT_BURST_WINDOW_S: "86400", CHAT_RATE_LIMIT_DAILY: "1000000", CHAT_RATE_LIMIT_GLOBAL_DAILY: "1000000" });
    expect(await status("192.0.2.62")).toBe(200);
  });

  it("when several are invalid, the first in table order is named", async () => {
    env({ CHAT_RATE_LIMIT_GLOBAL_DAILY: "x", CHAT_RATE_LIMIT_DAILY: "y", CHAT_RATE_LIMIT_BURST: "z" });
    await expectInvalid("CHAT_RATE_LIMIT_BURST", "z");
  });

  it("CHAT_RATE_LIMIT_STORE other than memory or upstash is invalid", async () => {
    env({ CHAT_RATE_LIMIT_STORE: "redis" });
    await expectInvalid("CHAT_RATE_LIMIT_STORE", "redis");
  });

  it("the memory store is refused on Vercel", async () => {
    env({ CHAT_RATE_LIMIT_STORE: "memory", VERCEL: "1" });
    await expectInvalid("CHAT_RATE_LIMIT_STORE");
  });

  it.each([
    ["no REST URL", { KV_REST_API_URL: undefined }, "KV_REST_API_URL"],
    ["an unparseable REST URL", { KV_REST_API_URL: "not a url" }, "KV_REST_API_URL"],
    ["no REST token", { KV_REST_API_TOKEN: undefined }, "KV_REST_API_TOKEN"],
    ["a blank REST token", { KV_REST_API_TOKEN: "  " }, "KV_REST_API_TOKEN"],
    ["no salt", { CHAT_RATE_LIMIT_SALT: undefined }, "CHAT_RATE_LIMIT_SALT"],
  ])("upstash with %s -> names %s", async (_name, override, variable) => {
    env({ ...UPSTASH_ENV, ...override });
    await expectInvalid(variable);
  });

  it("a salt shorter than 32 characters is invalid, even for the memory store", async () => {
    env({ CHAT_RATE_LIMIT_SALT: "x".repeat(31) });
    await expectInvalid("CHAT_RATE_LIMIT_SALT", "x".repeat(31));
    env({ CHAT_RATE_LIMIT_SALT: "x".repeat(32) });
    logs.length = 0;
    expect(await status("192.0.2.63")).toBe(200);
  });

  it("a short salt is named before an invalid store (table order)", async () => {
    env({ CHAT_RATE_LIMIT_SALT: "too-short", CHAT_RATE_LIMIT_STORE: "redis" });
    await expectInvalid("CHAT_RATE_LIMIT_SALT", "too-short");
  });

  it("a missing salt is named before a missing REST URL and token (table order)", async () => {
    env({ ...UPSTASH_ENV, CHAT_RATE_LIMIT_SALT: undefined, KV_REST_API_URL: undefined, KV_REST_API_TOKEN: undefined });
    await expectInvalid("CHAT_RATE_LIMIT_SALT");
  });

  it("the store defaults to upstash on Vercel (and fails closed without its settings)", async () => {
    env({ VERCEL: "1", CHAT_RATE_LIMIT_SALT: SALT });
    await expectInvalid("KV_REST_API_URL");
  });

  it("the store defaults to upstash on Vercel when fully configured", async () => {
    env({ VERCEL: "1", KV_REST_API_URL: STORE_URL, KV_REST_API_TOKEN: TOKEN, CHAT_RATE_LIMIT_SALT: SALT });
    expect(await status("192.0.2.64")).toBe(200);
    expect(storeCalls()).toHaveLength(1);
  });

  it("the store defaults to upstash when a REST URL is set, even off Vercel", async () => {
    env({ KV_REST_API_URL: STORE_URL, KV_REST_API_TOKEN: TOKEN, CHAT_RATE_LIMIT_SALT: SALT });
    expect(await status("192.0.2.65")).toBe(200);
    expect(storeCalls()).toHaveLength(1);
  });

  it("reads the UPSTASH_REDIS_REST_* names too", async () => {
    env({ UPSTASH_REDIS_REST_URL: STORE_URL, UPSTASH_REDIS_REST_TOKEN: TOKEN, CHAT_RATE_LIMIT_SALT: SALT });
    expect(await status("192.0.2.66")).toBe(200);
    expect(storeCalls()).toHaveLength(1);
    expect(String(storeCalls()[0][0])).toContain(STORE_URL);
  });

  it("the settings are read on every request", async () => {
    env({ CHAT_RATE_LIMIT_DAILY: "5" });
    expect(await status("192.0.2.67")).toBe(200);
    env({ CHAT_RATE_LIMIT_DAILY: "abc" });
    expect(await status("192.0.2.67")).toBe(503);
    env({ CHAT_RATE_LIMIT_DAILY: "5" });
    expect(await status("192.0.2.67")).toBe(200);
  });
});

// ---------------------------------------------------------------- AC11
describe("one text-free log line per request (AC11)", () => {
  const KEYS = ["duration_ms", "event", "outcome"];

  it("an admitted turn: one console.info line with exactly event, outcome, duration_ms", async () => {
    await ask("192.0.2.70");
    expect(logs).toHaveLength(1);
    expect(logs[0].method).toBe("info");
    expect(Object.keys(lastLine()).sort()).toEqual(KEYS);
    expect(lastLine()).toMatchObject({ event: "chat_request", outcome: "ok" });
  });

  it.each([
    ["burst", {}, 5],
    ["daily", { CHAT_RATE_LIMIT_BURST: "1000", CHAT_RATE_LIMIT_DAILY: "2" }, 2],
    ["global", { CHAT_RATE_LIMIT_GLOBAL_DAILY: "1" }, 1],
  ])("a %s-limited request: one console.error line, plus only `limit`", async (limit, settings, admitted) => {
    env(settings);
    for (let i = 0; i < admitted; i++) await ask("192.0.2.71");
    logs.length = 0;
    await ask("192.0.2.71");
    expect(logs).toHaveLength(1);
    expect(logs[0].method).toBe("error");
    expect(Object.keys(lastLine()).sort()).toEqual([...KEYS, "limit"].sort());
    expect(lastLine()).toMatchObject({ event: "chat_request", outcome: "rate_limited", limit });
    expect(typeof lastLine().duration_ms).toBe("number");
  });

  it("a store failure: one console.error line, exactly event, outcome, duration_ms", async () => {
    env(UPSTASH_ENV);
    storeReply = () => new Response("oops", { status: 500 });
    await ask("192.0.2.72");
    expect(logs).toHaveLength(1);
    expect(logs[0].method).toBe("error");
    expect(Object.keys(lastLine()).sort()).toEqual(KEYS);
    expect(lastLine().outcome).toBe("limiter_unavailable");
  });

  it("an invalid limiter configuration: one console.error line, plus only `variable`", async () => {
    env({ CHAT_RATE_LIMIT_BURST: "abc" });
    await ask("192.0.2.73");
    expect(logs).toHaveLength(1);
    expect(logs[0].method).toBe("error");
    expect(Object.keys(lastLine()).sort()).toEqual([...KEYS, "variable"].sort());
    expect(lastLine()).toMatchObject({ outcome: "limiter_config_invalid", variable: "CHAT_RATE_LIMIT_BURST" });
  });
});

// ---------------------------------------------------------------- AC13
describe("no new service locally (AC13)", () => {
  it("off Vercel with nothing set, a turn uses the in-process store: the only fetch is the backend call", async () => {
    expect(await status("192.0.2.80")).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(urlOf(fetchMock.mock.calls[0][0])).toContain(BASE_URL);
    expect(logs.filter((l) => l.method === "error")).toHaveLength(0);
  });
});
