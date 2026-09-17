# Spec Schema: tasks.md

> Standalone template for the granular work-list file of the 5-file SDD spec
> schema. Each task maps to a roadmap phase and, through it, to the contract
> items / intent goals that phase serves. Paths must be the real target files
> in the codebase, never placeholders.

## Template

```markdown
# Tasks: <Feature Name>

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

(Use the real file paths/extensions from this codebase throughout, not a
placeholder language's extension.)

## Phase 1: [Foundation]
- [ ] Task 1.1: [description] — `path/to/real/file.ext`
- [ ] Task 1.2: [description] — `path/to/real/file.ext`

## Phase 2: [Core Logic]
- [ ] Task 2.1: [description] — `path/to/real/file.ext`
- [ ] Task 2.2: [description] — `path/to/real/file.ext`

## Phase 3: [Integration]
- [ ] Task 3.1: [description] — `path/to/real/file.ext`
- [ ] Task 3.2: [description] — `path/to/real/file.ext`

## Phase 4: [Testing & Validation]
- [ ] Task 4.1: [description] — `path/to/real/file.ext`
- [ ] Task 4.2: [description] — `path/to/real/file.ext`

## Blocked Items
[None yet]

## Notes
[Any additional context for the executor]
```
