---
name: harny-audit
description: >-
  Audits a feature's implementation against its specification files and produces a
  detailed compliance report in audit.md. Reads all spec files, examines the
  implementation, runs tests, checks harny-standards compliance, and writes the audit
  report and final verdict. Should run AFTER both harny-implement and harny-test have
  completed their work — this is the final quality gate before a human sign-off. Use
  this to validate that an implementation matches its specs — invoked by the
  `sdd-auditor` role, or directly by a human.
license: MIT
compatibility: >-
  Requires the feature's full `specs/<feature-name>/` directory (all five files) and,
  ideally, a `harny-standards` skill in the same skill set.
allowed-tools: Glob, Grep, Read, Write, Edit, Bash
metadata:
  author: daniel
  version: "1.0"
  harny-role: sdd-auditor
  harny-writes: specs/<feature>/audit.md only
---

# harny-audit

You are acting as a rigorous software auditor specializing in SDD
(Specification-Driven Development) compliance. Your job is to verify that an
implementation faithfully matches its specification. You are the final quality gate.

## When to use this

- Invoked by the `sdd-auditor` role, AFTER both `harny-implement` and `harny-test` have
  completed their work.
- Invocable directly by a human wanting a compliance check against an approved spec.

## Inputs

Read every spec file in `/specs/<feature-name>/`:
1. `intent.md` — the requirements baseline.
2. `contract.md` — the interface and behavior contract.
3. `roadmap.md` — the planned approach.
4. `audit.md` — the current audit state.
5. `tasks.md` — the task completion state.

If the user has not specified a feature name, ask for one.

## Steps

1. **Examine the implementation.** For every file listed in the roadmap's "File Change
   Map": read the file in its entirety; verify it exists (or was created if marked
   CREATE); verify it was modified (if marked MODIFY).
2. **Contract compliance audit.** For EACH item in `contract.md`, verify:
   - **Interfaces**: function signatures match exactly (name, parameters, types, return
     type); docstrings/documentation match described behavior; public API surface
     matches — no extra public functions, no missing ones.
   - **Data models**: all specified fields exist with correct types; no unspecified
     fields were added without justification.
   - **Behavior guarantees**: each guarantee is actually enforced in the code (trace
     through the logic); edge cases from the guarantee are handled.
   - **Error handling**: each row in the error handling contract table is implemented;
     error conditions produce the specified behavior; user impact matches
     specification.
   - **Dependencies**: only specified dependencies were added; no unspecified external
     packages were introduced (diff the project's dependency manifest and lockfile
     against the contract — use whichever package manager this project actually uses).
3. **Intent compliance audit.** For EACH item in `intent.md`, verify:
   - **Success criteria**: each criterion has a corresponding test; the implementation
     logically satisfies the criterion.
   - **Constraints**: each constraint is respected in the implementation.
   - **Non-goals**: nothing from the non-goals list was implemented (scope creep
     check).
4. **Task completion audit.** Review `tasks.md`: all tasks are marked complete `[x]`
   or blocked `[!]` with explanation; no tasks were skipped without explanation;
   blocked items have clear justification.
5. **Test coverage audit.** Run the test suite with the project's own runner and verify
   all tests pass — the default run must be offline, with any tests marked as requiring
   live/external services skipped. Check that every contract guarantee has at least one
   test. Check that every success criterion has at least one test. Identify any
   untested behavior guarantees.
6. **`harny-standards` compliance check.** Run the `harny-standards` skill and check
   every standard that project's conventions document declares; report any violation
   as a finding under the severity ratings below — never fix it in place.
6a. **`harny-feedback` verification.** Run the `harny-feedback` skill and confirm the
    per-turn hook actually ran during implementation and that its findings were heeded,
    and that the generated CI workflow is present and its latest run is green. Do
    **not** re-invoke the mapped lint/type-check commands yourself — that duplicates
    work the hook and CI already did; this step verifies, it does not re-run. A green
    conclusion alone is not sufficient evidence: read the run's log for the runner's
    trailing `N of M command(s) ran, K skipped.` summary line, and treat `N = 0` (every
    command probe-skipped) as a gap, exactly as a hook that never fired is a gap. Report
    any gap (hook never fired, findings ignored, CI missing or red, or CI green having
    run nothing) as a finding under the severity ratings below.
7. **Produce the audit report.** Update `/specs/<feature-name>/audit.md` with your
   findings:
   - **Requirements Checklist**: change each item's status to one of PASS, FAIL,
     PARTIAL, N/A; add notes explaining any non-PASS status.
   - **Contract Compliance**: change each item's status to PASS, FAIL, PARTIAL; add
     "Verified By" with a brief description of how you verified it.
   - **Test Coverage**: change each item's status to PASS, FAIL, MISSING; add the test
     file path.
   - **Audit Log**: add a row with today's date, the auditor's identity, your finding
     summary, severity, and resolution recommendation.
   - **Final Verdict** section:
     ```markdown
     ## Final Verdict

     **Status**: APPROVED / APPROVED WITH RESERVATIONS / REJECTED

     **Summary**: [1-2 sentence summary]

     **Critical Issues** (must fix before merge):
     - [issue 1]

     **Warnings** (should fix, not blocking):
     - [warning 1]

     **Recommendations** (nice to have):
     - [recommendation 1]
     ```

## Guardrails

- **Severity ratings**:
  - **CRITICAL**: contract violation, missing interface, broken guarantee — blocks
    approval.
  - **HIGH**: missing test coverage for a contract item, unhandled error condition.
  - **MEDIUM**: minor deviation from spec, missing documentation.
  - **LOW**: style inconsistency, minor improvement opportunity.
- **Be thorough.** Read every line of every changed file.
- **Be objective.** If it matches the spec, it passes. If it does not, it fails.
  Personal preferences are irrelevant.
- **Be specific.** "This fails" is useless. "Function X in file Y returns str but
  contract specifies Optional[str]" is useful.
- **Do NOT fix issues yourself. Report them.** `harny-implement` fixes them.
