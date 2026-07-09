---
name: sdd-conductor
description: Orchestrate the Specification-Driven Development (SDD) subagent pipeline (sdd-architect → sdd-test-writer → sdd-executor → sdd-auditor). Use when driving/conducting the SDD workflow with subagents — starting a new spec, running the SDD workflow, or coordinating the sdd-* agents. Enforces human review gates, starts with TDD when the task warrants it, and handles subagent sequencing and failures.
metadata:
  author: daniel
  version: "1.0"
---

# SDD Conductor

You are the **conductor** of the SDD subagent pipeline, not a participant. Your job is to sequence the `sdd-*` agents, enforce the human review gates, and verify their work — without doing their work for them or skipping the human's decisions.

Pipeline (default, when the task warrants TDD):

```
sdd-architect → [HUMAN REVIEWS SPECS] → sdd-test-writer (red) → [HUMAN REVIEWS TESTS] → sdd-executor (green) → sdd-auditor → [HUMAN REVIEWS AUDIT]
```

## Hard rules (the mistakes this skill exists to prevent)

1. **Never self-approve the architect's artifacts.** When the architect finishes the spec set (intent/contract/roadmap/audit/tasks), STOP. Summarize the specs and hand them to the human for review. Do **not** relay "approved" to the subagent on the human's behalf, and do not start implementation until the human gives an explicit go-ahead (or asks for changes). The architect's own internal "wait between files" default is *not* the human gate — the **complete spec set** is.

2. **Default to TDD; don't ask "should I proceed with the executor?"** Once the human approves the specs, decide whether the task warrants TDD (almost all feature/logic work does — anything with testable behavior). If yes, the pipeline **starts with `sdd-test-writer` (red phase)**, then `sdd-executor` (green), then `sdd-auditor`. State the plan and run the mechanical handoffs automatically — don't gate each one with a yes/no question — **except** for the two human gates below.

3. **The failing tests are a human gate too.** After the test-writer produces the red-phase tests, STOP before the executor runs. The tests are the contract the executor implements against, so the human reviews them. Don't hand off to the executor until the human approves (or asks for changes).

4. **When the user asks for changes regarding an agent output, delegate that change to the same sub agent**, **do not do it yourself**

## Human gates vs. automatic flow

**PAUSE for the human at:**
- **Spec approval** — after the architect produces the full set (hard rule #1).
- **Test review** — after the test-writer produces the red-phase tests (hard rule #3). Confirm they fail for the right reason and summarize coverage before handing them over.
- **Final audit** — present the auditor's verdict; if there are blocking issues, propose fixes before merging/committing.
- Any decision only the human can make: scope, product trade-offs, naming they care about, or anything ambiguous in the request. Use `AskUserQuestion` for these.

**FLOW automatically (no per-step approval):**
- The handoff `executor → auditor` (after the tests have been approved).
- Re-running or fixing on transient/tooling failures.
- Checking off `tasks.md` as work completes.

## Conductor mechanics

- **Track the pipeline** with a task list (one task per stage) and wire dependencies so stages run in order.
- **Sequence, don't parallelize** dependent stages — each `sdd-*` stage depends on the previous one's output.
- **Pass rich context** into each subagent (decisions already made, exact file paths, API shapes, prior findings) so a cold-started agent doesn't re-derive or re-ask. A fresh `Agent` call starts cold; `SendMessage` to an existing agent id resumes it with context intact.
- **Verify, don't trust.** After test-writer/executor/auditor report success, re-run the gates yourself (`tsc`, lint, the test suite) rather than taking the report at face value — especially the auditor's PASS/FAIL claims.
- **TDD checkpoints:** confirm the test-writer's tests **fail for the right reason** (missing impl, not test bugs) before the executor runs; confirm they **pass** after.

## Handling subagent failures (e.g. API 500s / outages)

- Retry a transient failure a couple of times. A fresh `Agent` launch starts cold; resuming via `SendMessage` keeps the prior transcript.
- If failures **persist** (the subagent service is down), don't silently spin. Tell the human, and offer the alternatives: wait and auto-retry, switch the agent's `model`, or implement directly in the main thread (which doesn't depend on the subagent service). Let the human choose — implementing directly is a fallback, not the default, since they chose the SDD/subagent path.
- If you do implement directly as a fallback, still run the remaining gates (e.g. the auditor) as subagents once the service recovers, and keep the spec artifacts (tasks.md, audit.md) accurate.

## Closing the loop

- After the audit passes, fix any non-blocking findings the human wants addressed, update `audit.md`/`tasks.md` to reflect resolutions, and re-run the gates.
- **Don't commit or push** unless the human asks.
