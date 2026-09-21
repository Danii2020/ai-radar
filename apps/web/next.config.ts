import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Next 16's `next dev`/`next build` auto-generate AGENTS.md/CLAUDE.md for
  // AI coding agents unless disabled. The scaffold step already used
  // `--no-agents-md` to opt out; this stops the regeneration these files
  // are otherwise silently re-created with (unrelated to this spec, not in
  // the File Change Map).
  agentRules: false,
};

export default nextConfig;
