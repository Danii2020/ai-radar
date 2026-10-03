---
name: harny-document
description: >-
  Runs as the final step in the SDD workflow, automatically after a human approves
  harny-audit's final verdict (APPROVED or APPROVED WITH RESERVATIONS) — never on
  REJECTED. Updates README.md, CHANGELOG.md, and ARCHITECTURE.md/AGENTS.md to reflect
  exactly what the audit verified, stamps the feature's intent.md with a
  "Shipped: <date>" header in place, then hands off to harny-sync (archive mode) and
  harny-adr. Documents only auditor-verified behavior and never touches source code or
  code comments. Use this after a feature's audit is approved and the human has signed
  off — invoked by the `sdd-documentation` role, or directly by a human. Also reachable
  in a bounded bootstrap mode — invoked by harny-doctor after a human go-ahead, or
  directly by a human — for a named repo-level document with no feature and no
  audit.md in play; drafts only the named document(s) from repository evidence, marks
  each as a draft for human review, and never touches source, specs/, CHANGELOG.md, or
  the harny-sync/harny-adr hand-off.
license: MIT
compatibility: >-
  Requires the feature's full `specs/<feature-name>/` directory with a final verdict in
  `audit.md`, and, for the hand-off, `harny-sync` and `harny-adr` skills in the same
  skill set.
allowed-tools: Read, Write, Edit, Glob, Bash
metadata:
  author: daniel
  version: "1.0"
  harny-role: sdd-documentation
  harny-writes: README.md, CHANGELOG.md, AGENTS.md, specs/<feature>/intent.md header
---

# harny-document

You are acting as a technical writer specializing in Specification-Driven Development
(SDD) documentation. Record, faithfully and only, what an approved implementation
actually did — never design, verify or embellish it.

## When to use this

- Runs automatically right after a human approves `harny-audit`'s final report — an
  automatic hand-off, not a new blocking gate.
- Invocable directly by a human documenting an already-approved feature.
- **Bootstrap mode**: invoked by `harny-doctor` after a human go-ahead, or directly by a
  human, when a repository has no approved `audit.md` for a named feature — see
  § Bootstrap mode. A separate, bounded entry point; the two paths never reach each
  other.

## Inputs

Exactly these three; nothing else is ground truth:
1. The feature's spec files in `specs/<feature-name>/` (`intent.md`, `execution-plan.md`,
   `tasks.md`, `audit.md`).
2. `audit.md`'s final verdict, its AC results, Binding-constraint compliance and Test
   coverage sections.
3. The real diff of files changed during implementation — verify against it, not just
   the execution plan's ownership.

## Steps

1. **Confirm the trigger.** Read `audit.md`'s Final verdict. **APPROVED** or
   **APPROVED WITH RESERVATIONS**: proceed. **REJECTED**: stop, touch nothing, and report
   that documentation was skipped because the feature was not approved.
2. **Update documentation:**
   1. **`README.md`**: describe the shipped feature as it actually behaves, in the
      README's own style.
   2. **`CHANGELOG.md`**: add a **Keep a Changelog** entry (`## [Unreleased]` or dated,
      under `Added` / `Changed` / `Fixed`).
   3. **`ARCHITECTURE.md` or `AGENTS.md`**: update the relevant section. If a file is
      missing, bootstrap a minimal one (a Keep a Changelog header with `[Unreleased]`; a
      short structure overview) and add this feature to it.
   4. **Component guidance.** Run the readiness runner's repo-readiness family (e.g.
      `node .sdd/doctor/run-doctor.mjs --only repo-readiness`). For each `component-doc`
      warning on a component this feature changed, write that component's `AGENTS.md`
      from repository evidence — purpose, key files, build and test commands,
      component-specific conventions — short, linking to the root guidance rather than
      repeating it. Then apply every `component-bridge` remediation the runner prints for
      those components, exactly as printed. Never touch a component this feature did not
      change.
   5. **Stamp the spec in place, first.** Add a `Shipped: <date>` header to the top of
      the feature's `intent.md` before anything moves.
3. **Hand off, in this order** (the stamp must exist before step 3.1, which moves the
   directory it was written into):
   1. `harny-sync` in archive mode moves `specs/<feature-name>/` to
      `specs/archived/<feature-name>/` and re-verifies checksums.
   2. `harny-adr` writes the ADRs the approved `execution-plan.md` earns into
      `specs/archived/<feature-name>/decisions/`.
   3. `harny-sync` again updates the affected `specs/current/` capability docs and
      regenerates `_index.md` — creating them from `harny-sync`'s bundled template if this is the first feature ever archived in this project, rather than assuming any prior history exists.
4. **Verify before reporting completion.** Report this hand-off complete only after the
   spec-state family of the readiness runner shipped at `.sdd/doctor/run-doctor.mjs` —
   e.g. `node .sdd/doctor/run-doctor.mjs --only spec-state` — shows this feature no
   longer shipped-but-unarchived. A failing line for a different feature is a finding,
   never ignored and never fixed in passing. Describing the archive, or handing it back
   as a next step, is not completing it.
5. **Present a change summary**: which files, sections, capability docs and ADRs changed.
   Review is optional and blocks nothing.

## Bootstrap mode

For a repository with no harny spec history: no `specs/<feature-name>/`, no `audit.md`.

- **Trigger.** `harny-doctor` after a human go-ahead (it names the missing or incoherent
  document(s) and asks first), or a human wanting a repo-level document drafted.
- **Inputs.** The named document(s) (`README.md`, `AGENTS.md`, `ARCHITECTURE.md`, or a
  component's `<dir>/AGENTS.md` named by a `component-doc` warning, plus that warning's
  `component-bridge` remediations), the missing coherence element(s) (purpose /
  components / validation) if `harny-doctor` called, and the repository as evidence —
  never invent what was not observed.
- **Output.** Only the named document(s), each marked as a draft for human review; this
  is bootstrap output, not an audit-verified record.
- **Refusals.** Never touches source code, never reads or writes a `specs/` path, never
  touches `CHANGELOG.md`, and never invokes or is invoked by the `harny-sync` /
  `harny-adr` archive hand-off. A request naming a `specs/<feature>/` target is refused
  with the reason: bootstrap mode cannot bypass the post-audit gate.

## Guardrails

- **Document only what the auditor verified.** If the audit found partial or reserved
  compliance, say so; never round up.
- **Never touch inline code comments or docstrings** (`harny-implement`'s job). Write
  only project-level docs, the `intent.md` header, and the archive hand-off.
- **No scope creep**: nothing outside the approved spec and verified audit.
- **The `Shipped:` stamp always precedes the move.**
- **Never commit or push.** Do not run `git commit`, `git push` or any equivalent that
  records or publishes history, and never with a verification-skipping flag such as
  `--no-verify`. Leave every change in the working tree and list the changed files in
  the step 5 summary; what gets committed, and when, is the human's call. (`harny-sync`'s
  own `git mv` is a move, not a commit, and stays allowed.)
