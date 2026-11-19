/**
 * Spec: web-chat-ui, O3 (AC3, AC4, AC5, AC6). `handleChatRequest(request: Request):
 * Promise<Response>` is the whole logic of `POST /api/chat`: size check, parse, validate, trim,
 * read env, one backend call, map to a fixed error code, log one text-free line.
 *
 * The backend is a stubbed global `fetch`. All credentials are obvious fakes. The signing
 * itself is checked in backend.test.ts; here it only has to produce a request.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { handleChatRequest } from "./handle-chat-request";

const KEY_ID = "FAKE-TEST-KEY-ID-0001";
const SECRET = "fake-secret-value-do-not-use-0001";
const BASE_URL = "https://chat-api.fake.invalid";
const QUESTION = "zq-question-marker: what is new in agent frameworks?";
const ANSWER = "zq-answer-marker: here is the answer [1]";
const HISTORY_TEXT = "zq-history-marker";
const BACKEND_DETAIL = "zq-backend-detail-marker";

const SOURCE = {
  n: 1, title: "A title", url: "https://example.com/a", source: "Example",
  published: "2026-10-20", score: 0.8123,
};
const OK_BODY = { answer: ANSWER, sources: [SOURCE] };

const backendJson = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
let logged: string[];

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(backendJson(OK_BODY));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("CHAT_API_BASE_URL", BASE_URL);
  vi.stubEnv("CHAT_API_ACCESS_KEY_ID", KEY_ID);
  vi.stubEnv("CHAT_API_SECRET_ACCESS_KEY", SECRET);
  // Visitor limiter (web-chat-visitor-rate-limit): these cases share one visitor and send far more
  // than the default burst, so they run with limits out of reach. Limiter behaviour is in
  // rate-limit.test.ts.
  vi.stubEnv("CHAT_RATE_LIMIT_BURST", "1000000");
  vi.stubEnv("CHAT_RATE_LIMIT_DAILY", "1000000");
  vi.stubEnv("CHAT_RATE_LIMIT_GLOBAL_DAILY", "1000000");
  // Response cache (web-chat-response-cache): off for the existing cases, which resend one question and
  // count backend calls. The cache cases are in their own describe at the end of this file.
  vi.stubEnv("CHAT_CACHE_TTL_S", "0");
  logged = [];
  for (const method of ["log", "info", "warn", "error"] as const) {
    vi.spyOn(console, method).mockImplementation((...args: unknown[]) => {
      logged.push(args.map(String).join(" "));
    });
  }
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

type Item = { role: "user" | "assistant"; text: string };
function turns(count: number, firstIndex = 1): Item[] {
  const items: Item[] = [];
  for (let i = firstIndex; i < firstIndex + count; i++) {
    items.push({ role: "user", text: `question ${i}` });
    items.push({ role: "assistant", text: `answer ${i}` });
  }
  return items;
}

function post(body: unknown): Request {
  return new Request("http://localhost/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function backendPayload(callIndex = 0) {
  const [input, init] = fetchMock.mock.calls[callIndex] as [Request | string | URL, RequestInit?];
  const req = input instanceof Request ? input : new Request(input, init);
  return { url: req.url, method: req.method, body: await req.json() };
}

describe("success", () => {
  it("returns 200 with exactly {answer, sources} and calls POST {base}/v1/chat once", async () => {
    const res = await handleChatRequest(
      post({ question: QUESTION, history: turns(1) }),
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ answer: ANSWER, sources: [SOURCE] });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const sent = await backendPayload();
    expect(sent.method).toBe("POST");
    expect(sent.url).toBe(`${BASE_URL}/v1/chat`);
    expect(sent.body).toEqual({ question: QUESTION, history: turns(1) });
  });

  it("accepts a missing history as an empty one", async () => {
    const res = await handleChatRequest(post({ question: QUESTION }));
    expect(res.status).toBe(200);
    expect((await backendPayload()).body).toEqual({ question: QUESTION, history: [] });
  });

  it("reads the environment on every request, not at import time", async () => {
    await handleChatRequest(post({ question: QUESTION, history: [] }));
    vi.stubEnv("CHAT_API_BASE_URL", "https://other-chat-api.fake.invalid");
    fetchMock.mockResolvedValue(backendJson(OK_BODY));
    await handleChatRequest(post({ question: QUESTION, history: [] }));
    expect((await backendPayload(0)).url).toBe(`${BASE_URL}/v1/chat`);
    expect((await backendPayload(1)).url).toBe("https://other-chat-api.fake.invalid/v1/chat");
  });
});

describe("history trimming (AC3)", () => {
  it("12 completed turns -> turns 3 to 12 and the question are forwarded", async () => {
    await handleChatRequest(post({ question: QUESTION, history: turns(12) }));
    expect((await backendPayload()).body).toEqual({
      question: QUESTION,
      history: turns(10, 3),
    });
  });

  it("a 20-item history is forwarded unchanged", async () => {
    await handleChatRequest(post({ question: QUESTION, history: turns(10) }));
    expect((await backendPayload()).body.history).toEqual(turns(10));
  });

  it("cuts an item over 4000 characters to 4000", async () => {
    const history: Item[] = [
      { role: "user", text: "u".repeat(5000) },
      { role: "assistant", text: "short answer" },
    ];
    await handleChatRequest(post({ question: QUESTION, history }));
    const forwarded = (await backendPayload()).body.history as Item[];
    expect(forwarded.map((item) => item.text.length)).toEqual([4000, 12]);
  });
});

async function expectRejectedLocally(request: Request) {
  const res = await handleChatRequest(request);
  expect(res.status).toBe(400);
  expect(await res.json()).toEqual({ error: "invalid_request" });
  expect(fetchMock).not.toHaveBeenCalled();
}

describe("local validation: 400 and the backend is never called (AC3, AC4)", () => {
  it.each([
    ["a blank question", { question: "   ", history: [] }],
    ["an empty question", { question: "", history: [] }],
    ["a 1001-character question", { question: "q".repeat(1001), history: [] }],
    ["a missing question", { history: [] }],
    ["a non-string question", { question: 42, history: [] }],
    ["a history that is not a list", { question: "ok?", history: "nope" }],
    ["a history that starts with assistant", {
      question: "ok?",
      history: [{ role: "assistant", text: "a" }, { role: "user", text: "q" }],
    }],
    ["a history that does not alternate", {
      question: "ok?",
      history: [
        { role: "user", text: "q1" }, { role: "user", text: "q2" },
        { role: "assistant", text: "a1" }, { role: "assistant", text: "a2" },
      ],
    }],
    ["a history of odd length ending with user", {
      question: "ok?",
      history: [...turns(1), { role: "user", text: "dangling" }],
    }],
    ["a history item with a bad role", {
      question: "ok?",
      history: [{ role: "system", text: "q" }, { role: "assistant", text: "a" }],
    }],
  ])("%s", async (_name, body) => {
    await expectRejectedLocally(post(body));
  });

  it("accepts a question of exactly 1000 characters", async () => {
    const res = await handleChatRequest(post({ question: "q".repeat(1000), history: [] }));
    expect(res.status).toBe(200);
  });

  it("rejects a missing body, a non-JSON body and a JSON body that is not an object", async () => {
    await expectRejectedLocally(new Request("http://localhost/api/chat", { method: "POST" }));
    await expectRejectedLocally(post("<<not json"));
    await expectRejectedLocally(post("[1,2,3]"));
    await expectRejectedLocally(post("null"));
  });

  it("rejects a body over 524,288 bytes even when the question itself is fine", async () => {
    const padded = JSON.stringify({ question: "ok?", history: [], pad: "x".repeat(524_288) });
    expect(new TextEncoder().encode(padded).length).toBeGreaterThan(524_288);
    await expectRejectedLocally(post(padded));
  });
});

describe("missing server configuration: 503 unavailable, backend never called", () => {
  it.each([
    "CHAT_API_BASE_URL",
    "CHAT_API_ACCESS_KEY_ID",
    "CHAT_API_SECRET_ACCESS_KEY",
  ])("%s unset or blank", async (name) => {
    for (const value of [undefined, "", "   "]) {
      if (value === undefined) vi.stubEnv(name, undefined as unknown as string);
      else vi.stubEnv(name, value);
      const res = await handleChatRequest(post({ question: QUESTION, history: [] }));
      expect(res.status).toBe(503);
      expect(await res.json()).toEqual({ error: "unavailable" });
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

interface Failure {
  name: string;
  arrange: () => void;
  status: number;
  code: string;
}

const FAILURES: Failure[] = [
  { name: "backend 400", arrange: () => fetchMock.mockResolvedValue(backendJson({ error: "invalid_request", detail: BACKEND_DETAIL }, 400)), status: 400, code: "invalid_request" },
  { name: "backend 429", arrange: () => fetchMock.mockResolvedValue(backendJson({ error: "throttled", detail: BACKEND_DETAIL }, 429)), status: 429, code: "busy" },
  { name: "backend 504", arrange: () => fetchMock.mockResolvedValue(backendJson({ error: "upstream_timeout", detail: BACKEND_DETAIL }, 504)), status: 504, code: "timeout" },
  { name: "the route's own deadline (abort)", arrange: () => fetchMock.mockRejectedValue(new DOMException("aborted", "AbortError")), status: 504, code: "timeout" },
  { name: "backend 502", arrange: () => fetchMock.mockResolvedValue(backendJson({ error: "upstream_failure", detail: BACKEND_DETAIL }, 502)), status: 502, code: "upstream_failure" },
  { name: "a 200 that is not JSON", arrange: () => fetchMock.mockResolvedValue(new Response("<<not json", { status: 200 })), status: 502, code: "upstream_failure" },
  { name: "a 200 with the wrong shape", arrange: () => fetchMock.mockResolvedValue(backendJson({ answer: 5, sources: null })), status: 502, code: "upstream_failure" },
  { name: "a network error", arrange: () => fetchMock.mockRejectedValue(new TypeError(`fetch failed ${BASE_URL}`)), status: 502, code: "upstream_failure" },
  { name: "backend 403 (rotated or wrong key)", arrange: () => fetchMock.mockResolvedValue(backendJson({ message: BACKEND_DETAIL }, 403)), status: 503, code: "unavailable" },
  { name: "backend 500", arrange: () => fetchMock.mockResolvedValue(backendJson({ error: "internal_error", detail: BACKEND_DETAIL }, 500)), status: 503, code: "unavailable" },
  { name: "backend 503", arrange: () => fetchMock.mockResolvedValue(backendJson({ message: BACKEND_DETAIL }, 503)), status: 503, code: "unavailable" },
];

describe("error mapping table (AC5)", () => {
  it.each(FAILURES)("$name -> $status $code, one backend call, nothing leaked", async (failure) => {
    failure.arrange();
    const res = await handleChatRequest(
      post({ question: QUESTION, history: [{ role: "user", text: HISTORY_TEXT }, { role: "assistant", text: HISTORY_TEXT }] }),
    );
    expect(res.status).toBe(failure.status);
    const text = await res.text();
    expect(JSON.parse(text)).toEqual({ error: failure.code });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    for (const secretish of [KEY_ID, SECRET, "fake.invalid", BACKEND_DETAIL, QUESTION]) {
      expect(text).not.toContain(secretish);
    }
  });

  it("an unexpected throw -> 500 internal_error, backend not called", async () => {
    const hostile = new Proxy({}, {
      get() {
        throw new Error(`boom ${SECRET}`);
      },
    }) as unknown as Request;
    const res = await handleChatRequest(hostile);
    expect(res.status).toBe(500);
    const text = await res.text();
    expect(JSON.parse(text)).toEqual({ error: "internal_error" });
    expect(text).not.toContain(SECRET);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("logging: one structured line, never any text or credential (AC5, AC6)", () => {
  const FORBIDDEN = [QUESTION, ANSWER, HISTORY_TEXT, KEY_ID, SECRET, "fake.invalid", BACKEND_DETAIL];

  it.each(FAILURES)("$name writes exactly one JSON line with outcome and duration_ms", async (failure) => {
    failure.arrange();
    await handleChatRequest(
      post({ question: QUESTION, history: [{ role: "user", text: HISTORY_TEXT }, { role: "assistant", text: HISTORY_TEXT }] }),
    );
    expect(logged).toHaveLength(1);
    const line = JSON.parse(logged[0]);
    expect(typeof line.outcome).toBe("string");
    expect(line.outcome.length).toBeGreaterThan(0);
    expect(typeof line.duration_ms).toBe("number");
    for (const text of FORBIDDEN) expect(logged[0]).not.toContain(text);
  });

  it("a locally rejected request and a missing configuration also log one clean line", async () => {
    await handleChatRequest(post({ question: "q".repeat(1001), history: [] }));
    vi.stubEnv("CHAT_API_SECRET_ACCESS_KEY", "");
    await handleChatRequest(post({ question: QUESTION, history: [] }));
    expect(logged).toHaveLength(2);
    for (const line of logged) {
      expect(typeof JSON.parse(line).outcome).toBe("string");
      for (const text of FORBIDDEN) expect(line).not.toContain(text);
    }
  });

  it("a successful turn logs nothing that holds the question, answer, history or credentials", async () => {
    await handleChatRequest(
      post({ question: QUESTION, history: [{ role: "user", text: HISTORY_TEXT }, { role: "assistant", text: HISTORY_TEXT }] }),
    );
    for (const line of logged) {
      for (const text of FORBIDDEN) expect(line).not.toContain(text);
    }
  });
});

// ------------------------------------------------ web-chat-response-cache, AC1 to AC10
describe("response cache", () => {
  const STORE_URL = "https://store.fake.invalid";
  const STORE_TOKEN = "fake-store-token-do-not-use-0001";
  const SALT = "fake-salt-0123456789-abcdefghijklmnop-0001";
  let n = 0;
  /** A question no other test uses, so the module-level in-process cache never carries over. */
  const fresh = (label = "q") => `zq-cache-${label}-${++n}: what is new in agent frameworks?`;
  const ask = (question: string, history: unknown[] = []) => handleChatRequest(post({ question, history }));
  const lines = () => logged.map((l) => JSON.parse(l) as Record<string, unknown>);
  const backendCalls = () => fetchMock.mock.calls.filter(([input]) => String(input instanceof Request ? input.url : input).startsWith(BASE_URL));

  beforeEach(() => {
    vi.stubEnv("CHAT_CACHE_TTL_S", "3600");
    // a new Response per call: a body can be read once
    fetchMock.mockImplementation(async () => backendJson(OK_BODY));
  });

  it("AC1/AC10: the same first-turn question is answered from the cache with an identical response and no backend call", async () => {
    const q = fresh();
    const live = await ask(q);
    const hit = await ask(q);
    expect(backendCalls()).toHaveLength(1);
    expect(hit.status).toBe(live.status);
    expect(await hit.text()).toBe(await live.text());
    expect(Object.fromEntries(hit.headers)).toEqual(Object.fromEntries(live.headers));
    expect(lines().map((l) => l.cache)).toEqual(["miss", "hit"]);
  });

  it("AC2: trivially different spellings share an entry, different wording does not", async () => {
    const q = fresh("spell");
    await ask(q);
    await ask(`  ${q.toUpperCase().replace(/ /g, "   ")}  `);
    expect(backendCalls()).toHaveLength(1);
    await ask(q.replace("?", ""));
    expect(backendCalls()).toHaveLength(2);
  });

  it("AC3: a request with a history never reads or writes the cache", async () => {
    const q = fresh("history");
    await ask(q, turns(1));
    await ask(q, turns(1));
    expect(backendCalls()).toHaveLength(2);
    expect(lines().map((l) => l.cache)).toEqual(["skip", "skip"]);
    await ask(q); // nothing was stored by the two history turns
    expect(backendCalls()).toHaveLength(3);
    expect(lines()[2].cache).toBe("miss");
  });

  it.each([
    [400, "invalid_request"], [429, "busy"], [502, "upstream_failure"], [504, "timeout"],
    [403, "backend_forbidden"], [500, "backend_error"],
  ])("AC4: a backend %i is never stored", async (status) => {
    const q = fresh(`err${status}`);
    fetchMock.mockResolvedValueOnce(backendJson({ error: "x" }, status));
    expect((await ask(q)).status).not.toBe(200);
    expect((await ask(q)).status).toBe(200);
    expect(backendCalls()).toHaveLength(2);
  });

  it("AC4: an entry expires after CHAT_CACHE_TTL_S and a live call refreshes it", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(Date.UTC(2026, 10, 18));
      vi.stubEnv("CHAT_CACHE_TTL_S", "100");
      const q = fresh("ttl");
      await ask(q);
      vi.setSystemTime(Date.UTC(2026, 10, 18) + 99_000);
      await ask(q);
      expect(backendCalls()).toHaveLength(1);
      vi.setSystemTime(Date.UTC(2026, 10, 18) + 100_000);
      await ask(q);
      expect(backendCalls()).toHaveLength(2);
      await ask(q);
      expect(backendCalls()).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("AC9: the log line carries only the cache field in addition, and it is absent when the cache is off", async () => {
    const q = fresh("log");
    await ask(q);
    await ask(q);
    await ask(q, turns(1));
    vi.stubEnv("CHAT_CACHE_TTL_S", "0");
    await ask(q);
    const all = lines();
    expect(all.map((l) => l.cache)).toEqual(["miss", "hit", "skip", undefined]);
    for (const line of all) {
      expect(line.outcome).toBe("ok");
      expect(Object.keys(line).filter((k) => k !== "cache").sort()).toEqual(["duration_ms", "event", "outcome"]);
    }
  });

  it("AC7: an invalid setting bypasses the cache, answers live, and names the variable but not the value", async () => {
    vi.stubEnv("CHAT_CACHE_TTL_S", "zq-bad-value");
    const q = fresh("invalid");
    expect((await ask(q)).status).toBe(200);
    expect((await ask(q)).status).toBe(200);
    expect(backendCalls()).toHaveLength(2);
    for (const line of logged) {
      expect(JSON.parse(line)).toMatchObject({ outcome: "ok", cache: "error", variable: "CHAT_CACHE_TTL_S" });
      expect(line).not.toContain("zq-bad-value");
    }
  });

  describe("with the Upstash store", () => {
    let commands: unknown[][];
    let storeReply: (command: unknown[]) => Response | Promise<Response>;
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    beforeEach(() => {
      vi.stubEnv("CHAT_RATE_LIMIT_STORE", "upstash");
      vi.stubEnv("KV_REST_API_URL", STORE_URL);
      vi.stubEnv("KV_REST_API_TOKEN", STORE_TOKEN);
      vi.stubEnv("CHAT_RATE_LIMIT_SALT", SALT);
      commands = [];
      storeReply = (c) => (c[0] === "GET" ? json({ result: null }) : c[0] === "SET" ? json({ result: "OK" }) : json({ result: 0 }));
      fetchMock.mockImplementation(async (input: unknown, init?: RequestInit) => {
        const url = String(input instanceof Request ? input.url : input);
        if (url.startsWith(STORE_URL)) {
          const command = JSON.parse(String(init?.body)) as unknown[];
          commands.push(command);
          return storeReply(command);
        }
        return backendJson(OK_BODY);
      });
    });
    const names = () => commands.map((c) => c[0]);

    it("AC6: validation, missing configuration and an invalid limiter setting make no cache call", async () => {
      await handleChatRequest(post("{"));
      await handleChatRequest(post({ question: "", history: [] }));
      vi.stubEnv("CHAT_API_SECRET_ACCESS_KEY", "");
      await ask(fresh("noconf"));
      vi.stubEnv("CHAT_API_SECRET_ACCESS_KEY", SECRET);
      vi.stubEnv("CHAT_RATE_LIMIT_BURST", "abc");
      expect((await ask(fresh("badlimit"))).status).toBe(503);
      expect(commands).toHaveLength(0);
    });

    it("AC6: a limiter store failure still answers 503 on a hit and on a miss, with no backend call", async () => {
      const q = fresh("limfail");
      storeReply = (c) => (c[0] === "GET" ? json({ result: JSON.stringify(OK_BODY) }) : json({ error: "down" }, 500));
      expect((await ask(q)).status).toBe(503); // hit, burst check fails
      storeReply = (c) => (c[0] === "GET" ? json({ result: null }) : json({ error: "down" }, 500));
      const miss = await ask(q);
      expect(miss.status).toBe(503);
      expect(await miss.json()).toEqual({ error: "unavailable" });
      expect(backendCalls()).toHaveLength(0);
    });

    it.each([
      ["a read that throws", (c: unknown[]) => { if (c[0] === "GET") throw new TypeError("fetch failed"); return json({ result: c[0] === "SET" ? "OK" : 0 }); }, "error"],
      ["a read with a non-success status", (c: unknown[]) => (c[0] === "GET" ? json({ error: "x" }, 500) : json({ result: c[0] === "SET" ? "OK" : 0 })), "error"],
      ["a stored value that is not a chat response", (c: unknown[]) => (c[0] === "GET" ? json({ result: "{\"answer\":1}" }) : json({ result: c[0] === "SET" ? "OK" : 0 })), "error"],
      ["a write that fails", (c: unknown[]) => (c[0] === "SET" ? json({ error: "x" }, 500) : json({ result: c[0] === "GET" ? null : 0 })), "error"],
    ])("AC7: %s is a miss: the visitor gets the live answer and the log says cache error", async (_name, reply, cache) => {
      storeReply = reply as typeof storeReply;
      const res = await ask(fresh("fail"));
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual(OK_BODY);
      expect(backendCalls()).toHaveLength(1);
      expect(lines().at(-1)).toMatchObject({ outcome: "ok", cache });
    });

    it("AC8: no question, answer or digest reaches a log line or a store key", async () => {
      const q = `${QUESTION} ${++n}`;
      await ask(q);
      const keys = commands.filter((c) => c[0] === "GET" || c[0] === "SET").map((c) => String(c[1]));
      expect(keys.length).toBeGreaterThan(0);
      for (const key of keys) {
        expect(key).toMatch(/^chat-cache:\{v1\}:[0-9a-f]{64}$/);
        expect(key).not.toContain("zq-question-marker");
        for (const line of logged) expect(line).not.toContain(key.slice("chat-cache:{v1}:".length));
      }
      for (const line of logged) {
        expect(line).not.toContain("zq-question-marker");
        expect(line).not.toContain(ANSWER);
      }
    });

    it("AC4: a hit makes one read and the burst check, a miss one read, the full check and one write with an expiry", async () => {
      const q = fresh("shape");
      await ask(q);
      expect(names()).toEqual(["GET", "EVAL", "SET"]);
      const set = commands[2];
      expect(set.slice(3)).toEqual(["EX", "3600"]);
      expect(JSON.parse(String(set[2]))).toEqual(OK_BODY);
    });
  });
});
