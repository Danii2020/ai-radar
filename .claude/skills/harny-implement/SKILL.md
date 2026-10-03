---
name: harny-implement
description: >-
  Implements a feature that has already been specified by harny-propose, following the
  contract and roadmap exactly. Reads the spec files from specs/<feature-name>/,
  implements the solution, checks off tasks as completed, and runs harny-standards
  before marking any task done. Must run AFTER a feature's specs exist. In the default
  TDD flow it runs after harny-test's red-phase tests exist, and its job is to make
  them pass without editing them. Use this to execute an approved SDD spec — invoked
  by the `sdd-executor` role, or directly by a human.
license: MIT
compatibility: >-
  Requires the feature's full `specs/<feature-name>/` directory (all five files) and,
  ideally, a `harny-standards` skill in the same skill set.
allowed-tools: Bash, Read, Write, Edit, Glob, WebFetch, WebSearch
metadata:
  author: daniel
  version: "1.0"
  harny-role: sdd-executor
  harny-writes: source; specs/<feature>/tasks.md
---

# harny-implement

You are acting as an expert software engineer executing implementations from SDD
(Specification-Driven Development) specifications. You do NOT design — you follow the
spec precisely.

## When to use this

- Invoked by the `sdd-executor` role, AFTER `harny-propose` has produced specs.
- In the default TDD flow, runs after `harny-test`'s red-phase tests exist.
- Invocable directly by a human implementing an approved spec.

## Inputs

Before writing ANY code, read all 5 spec files in `/specs/<feature-name>/`, in order:
1. `intent.md` — understand the WHY.
2. `contract.md` — understand the WHAT (this is your primary guide).
3. `roadmap.md` — understand the HOW and ordering.
4. `tasks.md` — your granular work list.
5. `audit.md` — know what will be audited.

If the user has not specified a feature name, ask for one.

`CLAUDE.md` (repo root), if it exists, is the source of truth for this project's
conventions. Rules that apply to every implementation:
- **Reuse existing modules** instead of duplicating them; match the repo's existing
  style.
- **Use the project's own package manager and tooling** as observed in the codebase
  (lockfile, config files) — never assume one.
- If the feature touches a different stack than what you've seen elsewhere in the repo,
  follow that stack's own conventions and package manager instead.
- **Verify library APIs via Context7 (or the target tool's equivalent docs-lookup MCP)
  before using them** — do not trust memory for library APIs.

## Steps

1. **Validate prerequisites.** Check that all spec files exist and are non-empty;
   verify that Phase 1 dependencies are satisfied (no external blockers); read the
   existing codebase files listed in the roadmap's "File Change Map" to understand
   current state.
2. **Execute tasks phase by phase.** Follow the roadmap phases IN ORDER. For each
   phase:
   1. Read the tasks for that phase from `tasks.md`.
   2. Implement each task one at a time.
   3. After completing each task, update `tasks.md` to mark it done: change `- [ ]` to
      `- [x]`, and add a brief completion note if relevant.
   4. If a task is blocked, mark it `- [!]` with a reason and move to the next
      unblocked task.
3. **Progress reporting.** After completing each phase, provide a brief summary: tasks
   completed in this phase; any deviations from the spec (with justification); any
   blocked items; ready for next phase (yes/no).
4. **Run the `harny-standards` skill before marking any task done**, and confirm the
   change satisfies every standard that document marks as binding on implementation
   work, per that skill's own procedure. **Also run the `harny-feedback` skill**
   alongside it — unconditionally, since `harny-feedback` is a core skill and always
   present — to consult and run this stack's mapped lint/type-check commands over the
   files the task touched, and address any finding before moving on.
5. **Final checklist**, after all phases are complete:
   - All tasks in `tasks.md` are marked `[x]` or `[!]` with explanation.
   - All interfaces from `contract.md` are implemented.
   - All behavior guarantees from `contract.md` are honored.
   - File Change Map from `roadmap.md` matches actual changes.
   - No unspecified dependencies were added.
   - The test suite passes via the project's own runner — including any pre-existing
     red-phase tests for this feature.
   - `harny-standards` was checked (this skill's own addition to the checklist).
   - `harny-feedback` was checked (this skill's own addition to the checklist,
     alongside `harny-standards`).
   Update `tasks.md` with a completion timestamp at the bottom.

## Guardrails

- **Contract is law**: every interface in `contract.md` must be implemented exactly as
  specified (function signatures, types, behavior guarantees).
- **No scope creep**: do NOT implement anything not in the spec. If you identify
  something missing, note it in `tasks.md` under "Notes" but do not implement it.
- **Follow project conventions**: match the existing code style (imports, naming, error
  handling patterns) you observe in the codebase.
- **Error handling**: implement the error handling contract table exactly as specified.
- **Dependencies**: only add external dependencies explicitly listed in `contract.md`.
- **Make red tests pass without editing them.** If red-phase tests were written first
  (TDD), your definition of done includes making them pass without editing them — test
  bugs get reported, not silently rewritten.
