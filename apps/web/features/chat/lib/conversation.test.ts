/**
 * Spec: web-chat-ui, O5 (AC2, AC3, AC5). The conversation reducer, pure and client-side.
 *
 * Interface the tests fix (from `./conversation`):
 *   initialConversation: { messages: [], pending: null, error: null }
 *   conversationReducer(state, action) with actions
 *     { type: "asked", question } | { type: "answered", answer, sources } | { type: "failed", code }
 *   selectHistory(state): { role, text }[]   (completed turns only, what is sent as `history`)
 * `messages` holds completed turns only; `pending` is the in-flight question or null.
 */
import { describe, expect, it } from "vitest";
import {
  conversationReducer,
  initialConversation,
  selectHistory,
} from "./conversation";

const SOURCES = [
  { n: 1, title: "T", url: "https://example.com/a", source: "Ex", published: "2026-10-20", score: 0.9 },
];

type State = typeof initialConversation;
const run = (state: State, ...actions: Parameters<typeof conversationReducer>[1][]) =>
  actions.reduce(conversationReducer, state);

describe("conversationReducer", () => {
  it("starts empty: no messages, nothing pending, no error, no history", () => {
    expect(initialConversation.messages).toEqual([]);
    expect(initialConversation.pending).toBeNull();
    expect(initialConversation.error).toBeNull();
    expect(selectHistory(initialConversation)).toEqual([]);
  });

  it("asking marks the question as in flight and clears a previous error", () => {
    const failed = run(initialConversation, { type: "asked", question: "q1" }, { type: "failed", code: "busy" });
    const asked = run(failed, { type: "asked", question: "q1" });
    expect(asked.pending).toBe("q1");
    expect(asked.error).toBeNull();
  });

  it("an answer adds exactly one user/assistant pair and ends the pending state", () => {
    const state = run(
      initialConversation,
      { type: "asked", question: "q1" },
      { type: "answered", answer: "a1 [1]", sources: SOURCES },
    );
    expect(state.pending).toBeNull();
    expect(state.error).toBeNull();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[0]).toMatchObject({ role: "user", text: "q1" });
    expect(state.messages[1]).toMatchObject({ role: "assistant", text: "a1 [1]", sources: SOURCES });
  });

  it("history grows by one pair per success and carries no sources", () => {
    const state = run(
      initialConversation,
      { type: "asked", question: "q1" },
      { type: "answered", answer: "a1", sources: SOURCES },
      { type: "asked", question: "q2" },
      { type: "answered", answer: "a2", sources: [] },
    );
    expect(selectHistory(state)).toEqual([
      { role: "user", text: "q1" },
      { role: "assistant", text: "a1" },
      { role: "user", text: "q2" },
      { role: "assistant", text: "a2" },
    ]);
  });

  it.each(["invalid_request", "busy", "timeout", "upstream_failure", "unavailable", "internal_error"] as const)(
    "a %s failure keeps the conversation, leaves history unchanged and records the code",
    (code) => {
      const before = run(
        initialConversation,
        { type: "asked", question: "q1" },
        { type: "answered", answer: "a1", sources: [] },
      );
      const after = run(before, { type: "asked", question: "q2" }, { type: "failed", code });
      expect(after.error).toBe(code);
      expect(after.pending).toBeNull();
      expect(after.messages).toEqual(before.messages);
      expect(selectHistory(after)).toEqual(selectHistory(before));
    },
  );

  it("a retry after a failure that succeeds adds the pair once and clears the error", () => {
    const state = run(
      initialConversation,
      { type: "asked", question: "q1" },
      { type: "failed", code: "timeout" },
      { type: "asked", question: "q1" },
      { type: "answered", answer: "a1", sources: [] },
    );
    expect(state.error).toBeNull();
    expect(selectHistory(state)).toEqual([
      { role: "user", text: "q1" },
      { role: "assistant", text: "a1" },
    ]);
  });

  it("does not mutate the previous state", () => {
    const before = run(initialConversation, { type: "asked", question: "q1" });
    const snapshot = structuredClone(before);
    conversationReducer(before, { type: "answered", answer: "a1", sources: [] });
    expect(before).toEqual(snapshot);
  });
});
