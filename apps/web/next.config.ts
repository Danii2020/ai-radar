import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Next 16's `next dev`/`next build` auto-generate AGENTS.md/CLAUDE.md for
  // AI coding agents unless disabled. The scaffold step already used
  // `--no-agents-md` to opt out; this stops the regeneration these files
  // are otherwise silently re-created with (unrelated to this spec, not in
  // the File Change Map).
  agentRules: false,
  // Dev only: Next blocks dev assets (including the client JS bundles) for any origin other than
  // localhost, so opening `next dev` from a phone over the LAN renders the HTML but never hydrates
  // (buttons look fine and do nothing). Private-range wildcards allow that without naming an address.
  allowedDevOrigins: ['192.168.*.*', '10.*.*.*'],
};

export default nextConfig;
