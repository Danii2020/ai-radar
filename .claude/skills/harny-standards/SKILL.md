---
name: harny-standards
description: >-
  Points the caller at this project's coding-conventions document and hands back a
  short per-role checklist. Use before marking an implementation task done (as the
  executor) or before signing off on one (as the auditor), so both roles check the same
  standards against the same single source of truth instead of re-deriving
  conventions from the codebase separately and risking disagreement. Also usable
  directly by a human who wants a quick reminder of what this repo's code-level
  conventions are and where they are written down.
license: MIT
compatibility: >-
  Requires this project's own conventions document to exist and be readable — e.g.
  `AGENTS.md`, `CLAUDE.md`, or the project's equivalent.
metadata:
  author: daniel
  version: "1.0"
  harny-role: shared
  harny-writes: none
---

# harny-standards

This skill is a pointer plus a checklist, never a second copy of the rules. It exists so
`sdd-executor` and `sdd-auditor` check the same coding standards against the same
single document, instead of each re-deriving "match the existing code style" from
scratch and reaching different conclusions.

## When to use this

- Invoked by `harny-implement` (the executor) before marking any task done.
- Invoked by `harny-audit` (the auditor) as a compliance step under its existing
  severity ratings.
- Invocable directly by a human, or any other role, that wants the checklist without
  reading the full conventions document.

## Inputs

- **Required**: this project's own conventions document — `AGENTS.md`, `CLAUDE.md`, or
  the project's equivalent — and its coding-standards section, however many standards it
  declares.

## Steps

1. Locate this project's own conventions document — commonly `AGENTS.md` or `CLAUDE.md`,
   but use whatever document this project names as its source of truth for conventions.
   Read its coding-standards section in full.
2. Do **not** restate, summarize, or duplicate its rules here — naming the document and
   reading it live is the whole mechanism. Duplication is the drift failure this skill
   exists to prevent.
3. Apply the per-role checklist below, matching the caller's role. The exact standards —
   their count, their ids, and what each covers — are whatever this project's own
   conventions document declares; never assume any other project's stack, language, or
   test runner applies here.
   - **Executor** (`harny-implement`): before marking a task done, confirm the change
     satisfies every standard this project's own document marks as binding on
     implementation work — typically covering module/import conventions, error-handling
     conventions, determinism and formatting rules, dependency policy, reuse of shared
     constants instead of re-literalling them, and how this project expects its own
     tests to be structured and named.
   - **Auditor** (`harny-audit`): check every standard the document declares — including
     any rule against naming one tool's mechanic as the only possibility in portable
     content — and report violations as findings under the existing severity ratings.
4. Report back which standards were checked and any violation found, by whatever id this
   project's own document uses for them, so the caller's own audit trail can cite it.

## Guardrails

- **Never restate the rules.** If the conventions document is missing or unreadable,
  report that as a finding and fall back to observed codebase conventions, stating
  explicitly that the fallback was used — never invent or assume a rule.
- **Never fix a violation in place.** This skill (via the auditor) reports; it does not
  edit code.
- **Portability.** Always name the target as "this project's conventions document
  (`AGENTS.md`, `CLAUDE.md`, or the project's equivalent)" so a user pointing this skill
  at their own repo's conventions doc needs no edit to this file.
