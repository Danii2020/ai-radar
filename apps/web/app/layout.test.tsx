/**
 * Spec: web-chat-response-cache, O6 (AC14). Vercel Web Analytics is rendered by the root layout
 * only on Vercel (`VERCEL` set), so local, unit and e2e runs never load a Vercel script. The
 * package is mocked: this proves the wiring and the gate, not the package.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@vercel/analytics/next", () => ({ Analytics: () => <i data-analytics="on" /> }));

import RootLayout from "./layout";

const render = () => renderToStaticMarkup(<RootLayout><main>page</main></RootLayout>);

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("root layout analytics gate (AC14)", () => {
  it("renders Analytics when running on Vercel", () => {
    vi.stubEnv("VERCEL", "1");
    expect(render()).toContain('data-analytics="on"');
  });

  it("renders no Analytics off Vercel", () => {
    vi.stubEnv("VERCEL", undefined);
    const html = render();
    expect(html).not.toContain("data-analytics");
    expect(html).toContain("<main>page</main>");
  });
});
