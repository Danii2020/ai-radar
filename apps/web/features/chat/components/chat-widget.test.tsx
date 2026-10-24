/**
 * Spec: web-chat-ui, O6 (AC1, AC2, AC3, AC4, AC5). Component tests for `ChatWidget` with a
 * stubbed global `fetch` standing in for the same-origin `/api/chat` route.
 *
 * Interface the tests fix: `ChatWidget` (named export of `./chat-widget`, no props); the launcher
 * has `data-testid="chat-launcher"` (the Sources control also carries `aria-expanded`); the panel has role "dialog"; the input is the only
 * textbox; the send control is a button named /send/i; while a turn is in flight an element
 * with role "status" is shown; errors and input-validation messages use role "alert" and a
 * failure's alert holds a button named /retry|try again/i.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWidget } from "./chat-widget";

const SOURCES = [
  { n: 1, title: "Agents in production", url: "https://example.com/one", source: "Example News", published: "2026-10-20", score: 0.91 },
  { n: 2, title: "A second look", url: "https://example.org/two", source: "Other Wire", published: null, score: 0.8 },
];

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const toggle = () => screen.getByTestId("chat-launcher");
const open = () => fireEvent.click(toggle());
const input = () => screen.getByRole("textbox") as HTMLTextAreaElement | HTMLInputElement;
const sendButton = () => screen.getByRole("button", { name: /send/i });

function type(text: string) {
  fireEvent.change(input(), { target: { value: text } });
}
function ask(question: string) {
  type(question);
  fireEvent.click(sendButton());
}
const requestBody = (callIndex: number) =>
  JSON.parse((fetchMock.mock.calls[callIndex][1] as RequestInit).body as string);

describe("open and close (AC1)", () => {
  it("is closed on first render: a toggle, no dialog, aria-expanded false", () => {
    render(<ChatWidget />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("clicking the toggle opens a labelled dialog with an input and a send control", () => {
    render(<ChatWidget />);
    open();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleName();
    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(toggle().getAttribute("aria-controls")).toBe(dialog.id);
    expect(dialog.id).not.toBe("");
    expect(within(dialog).getByRole("textbox")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("the toggle's accessible name reflects open or closed", () => {
    render(<ChatWidget />);
    expect(toggle()).toHaveAccessibleName(/open/i);
    open();
    expect(toggle()).toHaveAccessibleName(/close/i);
  });

  it("a second click closes the panel", () => {
    render(<ChatWidget />);
    open();
    fireEvent.click(toggle());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("Escape closes the panel and focus returns to the toggle", async () => {
    render(<ChatWidget />);
    open();
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(toggle()).toHaveFocus());
  });

  it("opening moves focus to the input", async () => {
    render(<ChatWidget />);
    open();
    await waitFor(() => expect(input()).toHaveFocus());
  });

  it("closing with the toggle returns focus to it", async () => {
    render(<ChatWidget />);
    open();
    fireEvent.click(toggle());
    await waitFor(() => expect(toggle()).toHaveFocus());
  });
});

describe("asking and answering (AC2)", () => {
  it("shows the user's message and a status while in flight, then the answer without the status", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<ChatWidget />);
    open();
    ask("What is new in agent frameworks?");

    expect(screen.getByText("What is new in agent frameworks?")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();

    await act(async () => resolve(json({ answer: "Frameworks changed [1].", sources: SOURCES })));
    expect(await screen.findByText(/Frameworks changed/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders each source as a numbered link to its url with title and source name", async () => {
    fetchMock.mockResolvedValue(json({ answer: "See [1] and [2].", sources: SOURCES }));
    render(<ChatWidget />);
    open();
    ask("q");
    await screen.findByText(/See \[1\] and \[2\]/);

    fireEvent.click(screen.getByRole("button", { name: /sources \(2\)/i }));
    const links = within(screen.getByRole("dialog")).getAllByRole("link");
    expect(links).toHaveLength(2);
    SOURCES.forEach((source, i) => {
      expect(links[i]).toHaveAttribute("href", source.url);
      expect(links[i]).toHaveAttribute("target", "_blank");
      expect(links[i]).toHaveAttribute("rel", "noopener noreferrer");
      expect(links[i].textContent).toContain(`[${source.n}]`);
      expect(links[i].textContent).toContain(source.title);
      expect(links[i].textContent).toContain(source.source);
    });
  });

  it("an empty sources list renders the answer with no source links", async () => {
    fetchMock.mockResolvedValue(json({ answer: "I have nothing on that.", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("q");
    await screen.findByText(/nothing on that/);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sources/i })).not.toBeInTheDocument();
  });

  it("clears the input after a question is sent", async () => {
    fetchMock.mockResolvedValue(json({ answer: "ok", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("q");
    await screen.findByText("ok");
    expect(input().value).toBe("");
  });
});

describe("multi-turn history (AC3)", () => {
  it("resends the completed turns with each question and never sends sources", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ answer: "first answer", sources: SOURCES }))
      .mockResolvedValueOnce(json({ answer: "second answer", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("first question");
    await screen.findByText("first answer");
    ask("second question");
    await screen.findByText("second answer");

    expect(requestBody(0)).toEqual({ question: "first question", history: [] });
    expect(requestBody(1)).toEqual({
      question: "second question",
      history: [
        { role: "user", text: "first question" },
        { role: "assistant", text: "first answer" },
      ],
    });
  });

  it("a failed turn adds nothing to the history: the next question resends the same one", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ answer: "first answer", sources: [] }))
      .mockResolvedValueOnce(json({ error: "busy" }, 429))
      .mockResolvedValueOnce(json({ answer: "third answer", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("first question");
    await screen.findByText("first answer");
    ask("second question");
    await screen.findByRole("alert");
    ask("third question");
    await screen.findByText("third answer");

    const expectedHistory = [
      { role: "user", text: "first question" },
      { role: "assistant", text: "first answer" },
    ];
    expect(requestBody(1).history).toEqual(expectedHistory);
    expect(requestBody(2).history).toEqual(expectedHistory);
  });
});

describe("question limits (AC4)", () => {
  it("a 1001-character question is blocked with a message and no request", () => {
    render(<ChatWidget />);
    open();
    ask("q".repeat(1001));
    expect(screen.getByRole("alert")).toHaveTextContent(/1000|too long|shorter/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a blank question is blocked with a message and no request", () => {
    render(<ChatWidget />);
    open();
    ask("    ");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a question of exactly 1000 characters is sent", async () => {
    fetchMock.mockResolvedValue(json({ answer: "ok", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("q".repeat(1000));
    await screen.findByText("ok");
    expect(requestBody(0).question).toHaveLength(1000);
  });
});

describe("failure states (AC5)", () => {
  const CODES: [string, number][] = [
    ["invalid_request", 400],
    ["busy", 429],
    ["timeout", 504],
    ["upstream_failure", 502],
    ["unavailable", 503],
    ["internal_error", 500],
  ];

  async function alertTextFor(code: string, status: number) {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(json({ error: code }, status));
    const { unmount } = render(<ChatWidget />);
    open();
    ask("a question that fails");
    const alert = await screen.findByRole("alert");
    const text = alert.textContent ?? "";
    unmount();
    return text;
  }

  it("each code has its own generic copy that leaks no status, URL, header or trace", async () => {
    const texts: string[] = [];
    for (const [code, status] of CODES) {
      const text = await alertTextFor(code, status);
      expect(text.trim().length).toBeGreaterThan(0);
      expect(text).not.toMatch(/\b(400|403|429|500|502|503|504)\b/);
      expect(text).not.toMatch(/https?:|execute-api|\/api\/|authorization|stack|traceback|undefined|\{/i);
      if (code.includes("_")) expect(text).not.toContain(code);
      texts.push(text);
    }
    expect(new Set(texts).size).toBe(CODES.length);
  });

  it("a throttled turn says the service is busy", async () => {
    expect(await alertTextFor("busy", 429)).toMatch(/busy/i);
  });

  it("keeps the conversation and the typed question after an error", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ answer: "first answer", sources: [] }))
      .mockResolvedValueOnce(json({ error: "timeout" }, 504));
    render(<ChatWidget />);
    open();
    ask("first question");
    await screen.findByText("first answer");
    ask("second question");
    await screen.findByRole("alert");

    expect(screen.getByText("first question")).toBeInTheDocument();
    expect(screen.getByText("first answer")).toBeInTheDocument();
    expect(input().value).toBe("second question");
  });

  it("retry resends the same question with the same history and shows the answer", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ answer: "first answer", sources: [] }))
      .mockResolvedValueOnce(json({ error: "upstream_failure" }, 502))
      .mockResolvedValueOnce(json({ answer: "recovered answer", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("first question");
    await screen.findByText("first answer");
    ask("second question");
    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: /retry|try again/i }));

    await screen.findByText("recovered answer");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(requestBody(2)).toEqual(requestBody(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a transport failure (fetch rejects) shows a failure state, not a crash", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<ChatWidget />);
    open();
    ask("q");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(input().value).toBe("q");
  });
});

describe("console (AC7)", () => {
  it("writes nothing to the browser console through open, answer and error", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => {}),
    );
    fetchMock
      .mockResolvedValueOnce(json({ answer: "an answer", sources: SOURCES }))
      .mockResolvedValueOnce(json({ error: "busy" }, 429));
    render(<ChatWidget />);
    open();
    ask("one");
    await screen.findByText("an answer");
    ask("two");
    await screen.findByRole("alert");
    fireEvent.keyDown(input(), { key: "Escape" });
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});

describe("sources are collapsible (AC6)", () => {
  it("shows Sources (n) collapsed with no links, expands on click and collapses again", async () => {
    fetchMock.mockResolvedValue(json({ answer: "See [1] and [2].", sources: SOURCES }));
    render(<ChatWidget />);
    open();
    ask("q");
    const control = await screen.findByRole("button", { name: /sources \(2\)/i });
    expect(control).toHaveAttribute("aria-expanded", "false");
    expect(within(screen.getByRole("dialog")).queryByRole("link")).not.toBeInTheDocument();

    fireEvent.click(control);
    expect(control).toHaveAttribute("aria-expanded", "true");
    expect(within(screen.getByRole("dialog")).getAllByRole("link")).toHaveLength(2);

    fireEvent.click(control);
    expect(control).toHaveAttribute("aria-expanded", "false");
    expect(within(screen.getByRole("dialog")).queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("markdown only for assistant answers (AC1)", () => {
  it("keeps a user's **hi** literal and renders the assistant's **bold** as strong", async () => {
    fetchMock.mockResolvedValue(json({ answer: "**Agents** matter:\n\n1. A [1]\n2. B [2]", sources: [] }));
    render(<ChatWidget />);
    open();
    ask("**hi**");
    await screen.findByText("Agents");
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("**hi**")).toBeInTheDocument();
    expect(dialog.querySelector("strong")?.textContent).toBe("Agents");
    expect(dialog.querySelectorAll("ol > li")).toHaveLength(2);
    expect(dialog.textContent).toContain("A [1]");
  });
});

describe("loader (AC7)", () => {
  it("shows an announced status with text 'Thinking' (not the old text) until the answer arrives", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<ChatWidget />);
    open();
    ask("q");
    expect(screen.getByRole("status")).toHaveTextContent(/thinking/i);
    expect(screen.queryByText("Thinking...")).not.toBeInTheDocument();
    await act(async () => resolve(json({ answer: "done", sources: [] })));
    await screen.findByText("done");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("is gone after an error too", async () => {
    fetchMock.mockResolvedValue(json({ error: "busy" }, 429));
    render(<ChatWidget />);
    open();
    ask("q");
    await screen.findByRole("alert");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("composer (AC8)", () => {
  it("is named 'Your question'; Shift+Enter inserts a newline and sends nothing; Enter sends", async () => {
    fetchMock.mockResolvedValue(json({ answer: "ok", sources: [] }));
    render(<ChatWidget />);
    open();
    expect(screen.getByRole("textbox", { name: "Your question" })).toBeInTheDocument();
    type("a");
    fireEvent.keyDown(input(), { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(input().value).toBe("a");
    fireEvent.keyDown(input(), { key: "Enter" });
    await screen.findByText("ok");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("disables Send while a turn is pending", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<ChatWidget />);
    open();
    ask("q");
    expect(sendButton()).toBeDisabled();
    await act(async () => resolve(json({ answer: "done", sources: [] })));
    await screen.findByText("done");
    expect(sendButton()).toBeEnabled();
  });
});

describe("empty state and suggestions (AC9)", () => {
  it("shows a greeting and 3 suggestions on an empty conversation, and no Jump to latest", () => {
    render(<ChatWidget />);
    open();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/I can answer questions about the AI news cards/)).toBeInTheDocument();
    expect(within(dialog).getAllByRole("button").filter((b) => b.textContent?.endsWith("?"))).toHaveLength(3);
    expect(within(dialog).queryByRole("button", { name: /jump to latest/i })).not.toBeInTheDocument();
  });

  it("pressing a suggestion sends it once with empty history, and the empty state goes away", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<ChatWidget />);
    open();
    const suggestion = screen.getByRole("button", { name: /latest research on AI agents/ });
    fireEvent.click(suggestion);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestBody(0)).toEqual({ question: "What is the latest research on AI agents?", history: [] });
    expect(screen.getByText("What is the latest research on AI agents?")).toBeInTheDocument();
    expect(screen.queryByText(/I can answer questions about the AI news cards/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();

    await act(async () => resolve(json({ answer: "an answer", sources: [] })));
    await screen.findByText("an answer");
    expect(screen.queryByText(/I can answer questions about the AI news cards/)).not.toBeInTheDocument();
  });

  it("a failed suggestion shows the normal error state and keeps the question for retry", async () => {
    fetchMock.mockResolvedValue(json({ error: "busy" }, 429));
    render(<ChatWidget />);
    open();
    fireEvent.click(screen.getByRole("button", { name: /latest research on AI agents/ }));
    await screen.findByRole("alert");
    expect(input().value).toBe("What is the latest research on AI agents?");
  });
});

describe("header Close (AC5)", () => {
  it("closes the panel and returns focus to the launcher", async () => {
    render(<ChatWidget />);
    open();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close chat" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(toggle()).toHaveFocus());
  });
});
