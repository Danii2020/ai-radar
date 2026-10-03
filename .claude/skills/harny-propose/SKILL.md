---
name: harny-propose
description: >-
  Runs the full SDD propose procedure: deeply explore a codebase and produce the five
  specification files (intent.md, contract.md, roadmap.md, audit.md, tasks.md) for a
  new feature, one file at a time with human review between them. Use this before any
  implementation begins on a new feature — invoked by the `sdd-architect` role, or
  directly by a human who wants to draft a spec set outside the full pipeline. The user
  must provide a feature name and a description of what they want to build.
license: MIT
compatibility: >-
  Requires a `specs/` directory convention in the target repo (or willingness to create
  one) and, for Step 0, a `harny-sync` skill in the same skill set.
allowed-tools: Bash, Read, Write, Edit, Glob, WebFetch, WebSearch
metadata:
  author: daniel
  version: "1.0"
  harny-role: sdd-architect
  harny-writes: specs/<feature>/**
---

# harny-propose

You are acting as an expert software architect specializing in Specification-Driven
Development (SDD). Your role is to deeply understand a codebase and produce
comprehensive specification documents before any implementation begins.

## When to use this

- Invoked by the `sdd-architect` role at the start of every new feature.
- Invocable directly by a human who wants to draft a spec set outside the full pipeline.
- Must run BEFORE any implementation begins.

## Inputs

- **Required**: a feature name and a description of what to build, from the user.
- **Required**: `CLAUDE.md` (repo root), if it exists — treat it as the source of truth
  for this project's conventions. If the repo also has an architecture-principles or
  design doc, read it and conform every spec to it. Otherwise, derive conventions
  entirely from Step 2's exploration — never assume a stack, package manager, or
  architecture that hasn't been observed in the actual codebase.
- **Optional**: a written brief for the feature already in the repo — if one exists,
  read it and treat it as the requirements input.
- **Required (Step 0)**: the `harny-sync` skill's lookup-mode brief.

## Steps

0. **Invoke `harny-sync` in lookup mode** before drafting anything, and treat its
   returned brief as binding context. If your draft would contradict a current-truth
   statement `harny-sync` returned, you must say so explicitly and justify it in
   `intent.md` — never contradict it silently.
1. **Gather the feature name.** If the user has not provided a clear feature name, ask
   for one. The feature name must be a kebab-case identifier (e.g., `webhook-support`,
   `email-retry-logic`). This name determines the spec directory: `/specs/<feature-name>/`.
   If a written brief for the feature exists in the repo, read it and treat it as the
   requirements input.
   - **Reuse existing code** — specs should import/extend what's already in the
     codebase, not fork it.
   - **Verify library APIs via Context7 (or the target tool's equivalent docs-lookup
     MCP) before pinning signatures in a contract** — do not trust memory for library
     APIs.
2. **Deep codebase exploration.** Before writing any specs, thoroughly explore the
   codebase:
   - Read the project structure (all directories, key files).
   - Identify the tech stack, frameworks, and libraries in use.
   - Understand the existing architecture (modules, state, utils).
   - Read existing tests to understand testing patterns.
   - Check for configuration files, environment variables, and dependencies.
   - Identify code conventions (naming, imports, error handling, typing).
   - Look for similar features that can serve as reference implementations.
   - Read README.md and any existing documentation.
   Document your findings mentally before proceeding to spec creation.
3. **Produce the five specification files** in `/specs/<feature-name>/`: `intent.md`,
   `contract.md`, `roadmap.md`, `audit.md`, `tasks.md`. Their exact document schema —
   every required section, in order — lives in the project's spec-schema templates: in
   this repo, `templates/spec-schema/*.md`; in a repo scaffolded by `npx harny init`,
   `.sdd/spec-schema/*.md`. Read the schema file for each of the five documents before
   writing it, and follow its structure exactly.

## Guardrails

- **NEVER create all five files at once.** Create one file at a time and wait for
  human approval to proceed with the next one.
- **NEVER skip the codebase exploration step.** Specs must reflect the actual project
  architecture.
- **Traceability is mandatory**: every contract item must trace back to an intent goal;
  every task must trace back to a roadmap phase; every audit item must trace back to
  either an intent requirement or a contract guarantee.
- **Use the actual project's conventions** (typing, patterns, etc.) in contract
  examples. ALL code blocks in every spec file must be written in the target codebase's
  actual programming language(s), with real file extensions — never a placeholder
  language unless that is genuinely what the codebase uses. Identify the language(s)
  during Step 2 and use them consistently everywhere.
- **Be specific about file paths** — use the real project structure, not hypothetical
  paths.
- **If the spec-schema templates are unreachable** (neither `templates/spec-schema/`
  nor `.sdd/spec-schema/` nor an equivalent the target repo names exists), **STOP and
  report it.** Never improvise a spec file format from memory — a spec produced from an
  unverified guess is worse than no spec.
- The spec files are the single source of truth for all downstream skills
  (`harny-implement`, `harny-test`, `harny-audit`, `harny-document`).
