# Spec Schema: tasks.md

> Standalone template for the working-state file of the SDD spec schema. Check
> an outcome only with evidence. Never erase history or weaken criteria. Record
> an unavailable required check as unavailable, never as a pass. Each outcome
> cites the ACs it serves. Paths and commands must be real, never placeholders.

## Template

```markdown
# Tasks: <Feature Name>

## Status
Awaiting intent approval | Implementing | Needs audit | Repairing | Blocked | Interrupted | Accepted — pending synchronization

## Baseline
- Base commit: [sha]
- Branch: [name]
- Interpreter: [version]
- Cwd: [dir]
- Commands: [test, lint, type-check]
- Pre-existing failures: [list, or "none"]

## Outcomes
- [ ] **O1** (AC1, AC2): [outcome]
  - Tests: [files]
  - Red: [command and failing result]
  - Green: [command and passing result]
- [ ] **O2** Migration: [existing consumers and tests]
- [ ] **O3** Docs: [docs updated]
- [ ] **O4** Broader suite vs baseline: [command and result]
- [ ] **O5** Independent audit: [verdict from audit.md]

## Working state
- Updated: [timestamp]
- Outcome: [On]
- Phase: [phase]
- In progress: [what]
- Last command: [command and result]
- Next step: [what]

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
[Where to resume, in one or two lines.]
```
