/**
 * Spec: web-chat-ui, O2 (AC5, AC6). `callChatBackend` signs one request with SigV4 and makes
 * exactly one `fetch`. The real key is never used: every credential here is an obvious fake.
 *
 * Interface the tests fix (from `./backend`):
 *   callChatBackend({ baseUrl, accessKeyId, secretAccessKey, question, history, timeoutMs? })
 *     -> Promise<{ ok: true; data: { answer; sources } } | { ok: false; outcome }>
 *   outcome is one of: invalid_request (400), busy (429), timeout (504 or abort),
 *   upstream_failure (502, unreadable or mis-shaped 200, network error),
 *   backend_forbidden (403), backend_error (any other non-2xx).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { callChatBackend } from "./backend";

const KEY_ID = "FAKE-TEST-KEY-ID-0001";
const SECRET = "fake-secret-value-do-not-use-0001";
const BASE_URL = "https://chat-api.fake.invalid";

const SOURCE = {
  n: 1, title: "A title", url: "https://example.com/a", source: "Example",
  published: "2026-10-20", score: 0.8123,
};
const OK_BODY = { answer: "Hello [1]", sources: [SOURCE] };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function call(overrides: Record<string, unknown> = {}) {
  return callChatBackend({
    baseUrl: BASE_URL,
    accessKeyId: KEY_ID,
    secretAccessKey: SECRET,
    question: "What is new?",
    history: [],
    ...overrides,
  } as Parameters<typeof callChatBackend>[0]);
}

/** The request `fetch` was called with, whether passed as a Request or as (url, init). */
function sentRequest(): Request {
  const [input, init] = fetchMock.mock.calls[0] as [Request | string | URL, RequestInit?];
  return input instanceof Request ? input : new Request(input, init);
}

describe("callChatBackend: the signed request", () => {
  it("POSTs JSON {question, history} to {base}/v1/chat", async () => {
    fetchMock.mockResolvedValue(json(OK_BODY));
    const history = [{ role: "user", text: "q1" }, { role: "assistant", text: "a1" }];
    await call({ question: "Second?", history });

    const req = sentRequest();
    expect(req.method).toBe("POST");
    expect(req.url).toBe(`${BASE_URL}/v1/chat`);
    expect(req.headers.get("content-type")).toMatch(/^application\/json/);
    expect(await req.json()).toEqual({ question: "Second?", history });
  });

  it("signs with SigV4 for us-east-1 / execute-api and names only the key id", async () => {
    fetchMock.mockResolvedValue(json(OK_BODY));
    await call();

    const req = sentRequest();
    const auth = req.headers.get("authorization") ?? "";
    expect(auth).toMatch(/^AWS4-HMAC-SHA256 /);
    expect(auth).toContain(`Credential=${KEY_ID}/`);
    expect(auth).toMatch(/Credential=[^/]+\/\d{8}\/us-east-1\/execute-api\/aws4_request/);
    expect(auth).toMatch(/Signature=[0-9a-f]{64}/);
    expect(req.headers.get("x-amz-date")).toMatch(/^\d{8}T\d{6}Z$/);
  });

  it("never puts the secret in any header, the URL or the body", async () => {
    fetchMock.mockResolvedValue(json(OK_BODY));
    await call();

    const req = sentRequest();
    const everything = [
      req.url,
      await req.clone().text(),
      ...Array.from(req.headers.entries()).flat(),
    ].join("\n");
    expect(everything).not.toContain(SECRET);
  });
});

describe("callChatBackend: results", () => {
  it("returns the answer and sources of a well-formed 200", async () => {
    fetchMock.mockResolvedValue(json(OK_BODY));
    expect(await call()).toEqual({ ok: true, data: OK_BODY });
  });

  it("accepts an empty sources list and a null published date", async () => {
    const body = { answer: "No context.", sources: [{ ...SOURCE, published: null }] };
    fetchMock.mockResolvedValue(json(body));
    expect(await call()).toEqual({ ok: true, data: body });
    fetchMock.mockResolvedValue(json({ answer: "None.", sources: [] }));
    expect(await call()).toEqual({ ok: true, data: { answer: "None.", sources: [] } });
  });

  it.each([
    [400, "invalid_request"],
    [429, "busy"],
    [504, "timeout"],
    [502, "upstream_failure"],
    [403, "backend_forbidden"],
    [500, "backend_error"],
    [503, "backend_error"],
  ])("maps backend status %i to outcome %s", async (status, outcome) => {
    fetchMock.mockResolvedValue(json({ error: "x", detail: "backend detail" }, status));
    expect(await call()).toEqual({ ok: false, outcome });
  });

  it.each([
    ["a non-JSON body", () => new Response("<<not json", { status: 200 })],
    ["a missing answer", () => json({ sources: [] })],
    ["sources that is not a list", () => json({ answer: "a", sources: "none" })],
    ["a source without a url", () => json({ answer: "a", sources: [{ ...SOURCE, url: undefined }] })],
    ["a source whose n is not a number", () => json({ answer: "a", sources: [{ ...SOURCE, n: "1" }] })],
  ])("treats a 200 with %s as an upstream failure", async (_name, make) => {
    fetchMock.mockResolvedValue(make());
    expect(await call()).toEqual({ ok: false, outcome: "upstream_failure" });
  });

  it("reports a network error as an upstream failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect(await call()).toEqual({ ok: false, outcome: "upstream_failure" });
  });
});

describe("callChatBackend: exactly one attempt, with a deadline", () => {
  it.each([
    ["429", () => Promise.resolve(json({ error: "throttled" }, 429))],
    ["502", () => Promise.resolve(json({ error: "upstream_failure" }, 502))],
    ["504", () => Promise.resolve(json({ error: "upstream_timeout" }, 504))],
    ["a network error", () => Promise.reject(new TypeError("fetch failed"))],
    ["an abort", () => Promise.reject(new DOMException("aborted", "AbortError"))],
  ])("calls fetch once on %s (a retry would run the agent twice)", async (_name, reply) => {
    fetchMock.mockImplementation(reply);
    await call();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts a call that outlives timeoutMs and reports a timeout", async () => {
    fetchMock.mockImplementation(
      (input: Request | string | URL, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          const signals = [init?.signal, input instanceof Request ? input.signal : undefined];
          for (const signal of signals) {
            signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            );
          }
        }),
    );
    expect(await call({ timeoutMs: 25 })).toEqual({ ok: false, outcome: "timeout" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
