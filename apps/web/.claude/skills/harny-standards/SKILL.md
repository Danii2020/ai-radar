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

A pointer plus a checklist, never a second copy of the rules. It exists so
`sdd-executor` and `sdd-auditor` check the same coding standards against the same single
document instead of each re-deriving "match the existing code style" and disagreeing.

## When to use this

- Invoked by `harny-implement` before marking any task done.
- Invoked by `harny-audit` as a compliance step under its existing severity ratings.
- Invocable directly by anyone who wants the checklist without reading the full document.

## Inputs

- **Required**: this project's own conventions document — `AGENTS.md`, `CLAUDE.md`, or
  the project's equivalent — and its coding-standards section, however many standards
  it declares. Never assume another project's stack, language or test runner applies.

## Steps

1. Read the conventions document's coding-standards section in full, live. Do **not**
   restate, summarize or duplicate its rules here or in your report; duplication is the
   drift this skill exists to prevent.
2. **Executor**: before marking a task done, confirm the change satisfies every standard the document marks as binding on implementation work.
   **Auditor**: check every standard the document declares and report each violation as a finding under the existing
   severity ratings.
3. Report which standards were checked and any violation found, by the id the document
   uses, so the caller's audit trail can cite it.

## Guardrails

- **Never restate the rules.** If the document is missing or unreadable, report that as
  a finding and fall back to observed codebase conventions, saying explicitly that the
  fallback was used — never invent a rule.
- **Never fix a violation in place.** The auditor reports; it does not edit code.
- **Portability.** Name the target as "this project's conventions document (`AGENTS.md`,
  `CLAUDE.md`, or the project's equivalent)" so pointing this skill at another repo
  needs no edit here.
