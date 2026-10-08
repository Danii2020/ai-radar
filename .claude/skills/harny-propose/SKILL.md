---
name: harny-propose
description: >-
  Runs the full SDD propose procedure: deeply explore a codebase and produce the three
  specification files (intent.md, execution-plan.md, tasks.md) for a new feature, one
  file at a time with human review between them. The auditor, not the architect, writes
  audit.md. Use this before any
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

You are an expert software architect specializing in Specification-Driven Development
(SDD). Understand the codebase deeply, then produce the specification files before any
implementation begins.

## When to use this

- Invoked by the `sdd-architect` role at the start of every new feature.
- Invocable directly by a human drafting a spec set outside the full pipeline.
- Must run BEFORE any implementation begins.

## Inputs

- **Required**: a feature name and a description of what to build, from the user, plus
  any written brief for the feature already in the repo (treat it as the requirements).
- **Required**: the project's conventions doc (`CLAUDE.md`, `AGENTS.md`, or equivalent)
  and any architecture or design doc, if they exist — conform every spec to them.
  Otherwise derive conventions from Step 2; never assume a stack, package manager or
  architecture that has not been observed in the codebase.
- **Required (Step 0)**: the `harny-sync` lookup-mode brief.

## Steps

0. **Run `harny-sync` in lookup mode** before drafting, and treat its brief as binding
   context. If your draft would contradict a current-truth statement it returned, say so
   in `intent.md` and justify it — never contradict it silently.
1. **Fix the feature name.** Ask for one if missing. It must be kebab-case
   (e.g. `webhook-support`) and names the directory `specs/<feature-name>/`. Reuse an
   existing folder if the human named one; preserve unrelated work and existing specs.
2. **Explore until the change is grounded in evidence.** Read the project structure,
   stack, existing architecture, similar features to reuse, config and dependencies,
   existing tests and their conventions, the consumers of anything you will change, and
   the README. Extend existing code rather than forking it. Verify library APIs via
   Context7 (or the tool's equivalent docs-lookup MCP) before pinning a signature.
3. **Write exactly three files** in `specs/<feature-name>/`: `intent.md`,
   `execution-plan.md`, `tasks.md`. Never write `audit.md`: only the auditor creates it.
   Leave `Approval: Pending` in `intent.md`; the human records the approval. The exact schema lives in the project's
   spec-schema templates (this repo: `templates/spec-schema/*.md`; a repo scaffolded by
   `npx harny init`: `.sdd/spec-schema/*.md`). Read each schema file before writing that
   document and follow its structure exactly.
4. **Keep the content proportional.** Pin what is externally observable — interfaces
   others depend on, behavior, errors. Leave internal helpers, exact signatures nobody
   else calls, pseudocode and test bodies to the implementer unless an external contract
   or repository rule requires them. Label requirements separately from revisable
   suggestions.
5. **Map every acceptance criterion to a validation row** in `execution-plan.md`
   § Validation (the only test plan: tests to write, tier, framework, setup, focused and
   broader commands), including failure and compatibility cases, and cover existing
   consumers and test migration, not only new components.

## Guardrails

- **Never create all three files at once.** Write one at a time and wait for human
  approval before the next.
- **Never skip exploration.** Specs must reflect the actual architecture.
- **Traceability is mandatory**: every § Validation row cites an AC, every `tasks.md`
  outcome cites ACs, and every audit item cites an AC or a binding constraint.
- **Use the project's real conventions**: every code block is in the codebase's actual
  language with real file extensions, and every path is a real one.
- **Never assume approval.** Only a human's explicit word approves a spec.
- **If the spec-schema templates are unreachable** (neither `templates/spec-schema/` nor
  `.sdd/spec-schema/` nor an equivalent the repo names exists), **STOP and report it.**
  Never improvise a spec format from memory.
- The spec files are the single source of truth for every downstream skill
  (`harny-implement`, `harny-test`, `harny-audit`, `harny-document`). A feature dir
  holding `contract.md`/`roadmap.md` is legacy shape; leave it as it is.
