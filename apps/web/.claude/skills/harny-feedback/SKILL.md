---
name: harny-feedback
description: >-
  Points the caller at the single stack-to-command mapping (`src/feedback.ts`) that
  defines this project's computational feedback commands — lint and type-check, per
  supported stack — and hands back a short per-role procedure for using it. Invoked
  by harny-implement before marking any task done, alongside harny-standards, to
  consult and run the mapped commands for the config's resolved stack. Invoked by
  harny-audit to verify that the per-turn hook actually fired and was heeded, and that
  the generated CI workflow is green — never to re-run the mapped commands itself. Any
  finding is mapped onto harny-audit's existing CRITICAL/HIGH/MEDIUM/LOW severity
  buckets by reference, never restated. Also usable directly by a human who wants to
  know which computational feedback commands apply to a given stack, or where the
  generated hook and CI workflow templates live.
license: MIT
compatibility: >-
  Requires `src/feedback.ts` (the stack-to-command mapping) to exist. Full effect also
  requires the generated per-tool hook (from `templates/hooks/`) and the generated CI
  workflow (`templates/ci/harny-feedback.yml`) to be present in the target repo.
metadata:
  author: daniel
  version: "1.0"
  harny-role: shared
  harny-writes: none
---

# harny-feedback

This skill is a pointer plus a checklist, never a second copy of the commands. It
exists so `harny-implement` and `harny-audit` both check the same computational
feedback (lint, type-check) against the same single mapping, instead of each
re-deriving "what does this stack's toolchain look like" separately and reaching
different conclusions — the same discipline `harny-standards` already established for
coding conventions.

## When to use this

- Invoked by `harny-implement` before marking any task done, alongside its existing
  `harny-standards` call.
- Invoked by `harny-audit` as a verification step: confirming the hook ran and its
  findings were heeded, and that the CI gate is green — not re-running the mapped
  tools from scratch.
- Invocable directly by a human, or any other role, who wants to know which
  computational feedback commands apply to a given `config.stack`, or where the
  canonical hook/CI templates live.

## Inputs

- **Required**: `src/feedback.ts` — the single stack-to-command mapping
  (`STACK_PROFILES`, `resolveStackProfile`, `STACK_PROFILE_IDS`). This is the ONLY
  place a feedback command string is written; never re-literal a command here or
  anywhere else.
- **Optional, for full effect**: the generated per-tool hook config (one of
  `.claude/settings.json`, `.cursor/hooks.json`, `.kiro/hooks/*.json`,
  `.github/hooks/*.json`, `hooks.json`), the shared runner
  (`.sdd/feedback/run-feedback.mjs`), and the generated CI workflow
  (`.github/workflows/harny-feedback.yml`) — all derived from `templates/hooks/` and
  `templates/ci/harny-feedback.yml`.

## Steps

1. Resolve the project's stack via `resolveStackProfile(config.stack)` in
   `src/feedback.ts`. An unresolved or blank stack is a defined, non-fatal outcome
   (the escape hatch) — proceed to the per-role step below rather than treating it as
   an error.
2. Do **not** restate, summarize, or duplicate `STACK_PROFILES`' commands here —
   naming the module and reading it live is the whole mechanism. Duplication is the
   drift failure this skill exists to prevent.
3. Apply the per-role step that matches the caller:
   - **Executor** (`harny-implement`): before marking a task done, run (or confirm the
     per-turn hook already ran) the resolved profile's commands over the files the
     task touched, and address any finding before moving on.
   - **Auditor** (`harny-audit`): verify, do not re-run. Confirm the per-turn hook
     fired during implementation and that its findings were addressed, and confirm the
     generated CI workflow (`.github/workflows/harny-feedback.yml`) is present and its
     latest run against the change is green. Do not invoke the mapped lint/typecheck
     commands a second time in the auditor's own context — that duplicates work the
     hook and CI already did, and re-running is not this skill's job.
4. Map any finding onto `harny-audit`'s existing severity buckets
   (`.agents/skills/harny-audit/SKILL.md`'s CRITICAL/HIGH/MEDIUM/LOW ratings) by
   reference: a type-check failure is CRITICAL, a lint error is HIGH, a lint warning is
   MEDIUM, a formatting-only finding is LOW. A command skipped because its `requires`
   probe was false is not a finding at all — it is coverage, reported as such.
5. Report back which commands applied (or that the stack's escape hatch was in
   effect), and any finding by severity, so the caller's own checklist or audit trail
   can cite it.

## Guardrails

- **Never restate a command string.** If `src/feedback.ts` is missing or unreadable,
  report that as a finding and stop — never invent a lint/type-check command from
  memory or from what a different stack usually uses.
- **Never re-implement or re-run what the hook and CI already did.** The auditor's use
  of this skill verifies the hook fired and was heeded and that CI is green; it does
  not re-invoke the mapped commands itself.
- **Never restate a severity definition.** Findings map onto `harny-audit`'s existing
  CRITICAL/HIGH/MEDIUM/LOW buckets by reference, the same way this skill's commands
  live only in `src/feedback.ts`.
- **Portability.** Always name the target as "this project's stack-to-command mapping
  (`src/feedback.ts`, or the project's equivalent)" so a user pointing this skill at
  their own repo's mapping needs no edit to this file.
