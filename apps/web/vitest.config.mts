import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // Phase 1 has no test files yet (they land in Phase 4); an empty suite
    // must still be a green gate.
    passWithNoTests: true,
  },
  resolve: {
    alias: {
      // Mirrors tsconfig.json's "@/*" path — no extra resolver dependency.
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
});
