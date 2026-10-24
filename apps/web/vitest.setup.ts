import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; `use-stick-to-bottom` needs one. Scroll behavior is tested in Playwright.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
