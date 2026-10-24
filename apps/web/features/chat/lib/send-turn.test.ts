/**
 * Spec: web-chat-ui, O5 (AC2, AC5). `sendTurn` is the browser side of one turn: a same-origin
 * `POST /api/chat`, a client deadline, and the mapping of the response to a result.
 *
 * Interface the tests fix (from `./send-turn`):
 *   sendTurn({ question, history, signal? })
 *     -> Promise<{ ok: true; answer; sources } | { ok: false; code }>
 * `code` is one of: invalid_request, busy, timeout, upstream_failure, unavailable, internal_error.
 * Anything the route could not have said (a network failure, an unreadable body, an unknown
 * code) maps to upstream_failure for a failed transport and internal_error for an unknown code.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sendTurn } from "./send-turn";

const SOURCE = {
  n: 1, title: "A title", url: "https://example.com/a", source: "Example",
  published: null, score: 0.5,
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const history = [{ role: "user" as const, text: "q1" }, { role: "assistant" as const, text: "a1" }];

describe("sendTurn", () => {
  it("POSTs {question, history} as JSON to the same-origin /api/chat", async () => {
    fetchMock.mockResolvedValue(json({ answer: "a", sources: [] }));
    await sendTurn({ question: "Second?", history });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("content-type")).toMatch(/^application\/json/);
    expect(JSON.parse(init.body as string)).toEqual({ question: "Second?", history });
  });

  it("maps a 200 body to the answer and its sources", async () => {
    fetchMock.mockResolvedValue(json({ answer: "Hello [1]", sources: [SOURCE] }));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({
      ok: true,
      answer: "Hello [1]",
      sources: [SOURCE],
    });
  });

  it("maps a 200 with an empty sources list", async () => {
    fetchMock.mockResolvedValue(json({ answer: "No sources.", sources: [] }));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({
      ok: true,
      answer: "No sources.",
      sources: [],
    });
  });

  it.each([
    [400, "invalid_request"],
    [429, "busy"],
    [504, "timeout"],
    [502, "upstream_failure"],
    [503, "unavailable"],
    [500, "internal_error"],
  ])("passes the route's %i %s through as that code", async (status, code) => {
    fetchMock.mockResolvedValue(json({ error: code }, status));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({ ok: false, code });
  });

  it("treats an error body with an unknown code as internal_error", async () => {
    fetchMock.mockResolvedValue(json({ error: "something_else" }, 418));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({ ok: false, code: "internal_error" });
  });

  it("treats a 200 with the wrong shape or a non-JSON body as upstream_failure", async () => {
    fetchMock.mockResolvedValue(json({ answer: 5 }));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({ ok: false, code: "upstream_failure" });
    fetchMock.mockResolvedValue(new Response("<html>oops</html>", { status: 200 }));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({ ok: false, code: "upstream_failure" });
  });

  it("maps a network failure to upstream_failure and an abort (the client deadline) to timeout", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({ ok: false, code: "upstream_failure" });
    fetchMock.mockRejectedValue(new DOMException("aborted", "AbortError"));
    expect(await sendTurn({ question: "q", history: [] })).toEqual({ ok: false, code: "timeout" });
  });

  it("passes an abort signal to fetch and makes one request per call (no retry)", async () => {
    fetchMock.mockResolvedValue(json({ error: "busy" }, 429));
    await sendTurn({ question: "q", history: [] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});
