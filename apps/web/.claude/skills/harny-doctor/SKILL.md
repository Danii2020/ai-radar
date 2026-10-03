---
name: harny-doctor
description: >-
  Runs this project's readiness check — a deterministic, feedforward pre-flight that
  confirms the SDD harness is actually installed and coherent before an agent starts
  work — and hands back how to read its report. Use at the start of a session, and
  again before starting new spec work, so the agent begins on verified ground instead
  of rediscovering a half-scaffolded harness, an incoherent spec state, or an unproven
  test suite partway through a feature. The per-turn lint/type-check trigger and the
  before-marking-a-task-done trigger belong to harny-feedback and are never duplicated
  here — this skill owns session-start and pre-spec-work readiness only. Also
  assesses whether this repo carries the documentation an agent needs (purpose,
  components, validation commands), states a ready/not-ready verdict, and, only
  after the caller says yes, hands off drafting any gap to harny-document. Also
  usable directly by a human who wants to confirm a repository is ready for SDD
  work before handing it to an agent.
license: MIT
compatibility: >-
  Requires a scaffolded readiness runner and checks data to exist in the target
  repo — in this repo, `.sdd/doctor/run-doctor.mjs` and `.sdd/doctor/checks.json`
  (or a downstream project's equivalents, written by `npx harny init`). Full effect
  also benefits from `.sdd/harness.json` being present, though its absence is a
  defined, non-fatal outcome for a repo this tool never scaffolded.
metadata:
  author: daniel
  version: "1.0"
  harny-role: shared
  harny-writes: none
---

# harny-doctor

This skill is a runner plus a reading procedure, never a second implementation of the
checks. It exists so an agent can ask "is this harness actually ready?" once, at the
start of its work, instead of discovering a deleted spec-schema template, an unproven
test suite, or a shipped-but-unarchived feature several turns into a session.

## When to use this

- At the start of a session, before relying on any part of the harness.
- On demand, before starting new spec work — confirming the knowledge base and the
  harness files a new feature will build on are actually coherent.
- Invocable directly by a human who wants to confirm a repository is ready for SDD
  work.
- **Not** for the per-turn lint/type-check trigger or the before-marking-a-task-done
  trigger — those triggers belong to `harny-feedback` and are never duplicated here;
  this skill owns session-start and pre-spec-work readiness only.

## Inputs

- **Required**: the scaffolded readiness runner and its checks data — in this repo,
  `.sdd/doctor/run-doctor.mjs` and `.sdd/doctor/checks.json` (or the project's
  equivalents, written by `npx harny init`).
- **Optional, read for context**: `.sdd/harness.json`, if present — its absence is a
  defined, non-fatal outcome for a repo this tool never scaffolded, not an error.
- **Read by the check itself, not by this skill directly**: `specs/`, the project's
  conventions document, and the resolved stack's full test-suite command.

## Steps

1. Run the scaffolded readiness runner (directly with `node`, or via the project's
   own `doctor` command if one is wired up) rather than re-deriving what it checks —
   naming the runner and running it live is the whole mechanism.
2. Read the report in full: it evaluates every check regardless of an earlier
   failure, so one run shows everything wrong at once.
3. **Assess coherence.** For each guidance document the runner reported present —
   this project's conventions document, its README, its architecture/structure
   document — read it and judge three elements:
   - **Purpose** — does it state what this project is and what it is for?
   - **Components** — does it name the top-level structure and what each main part
     does?
   - **Validation** — does it name the commands that prove a change is good (tests,
     lint, type-check, build)?
   Report each element as stated or missing, per document, by name. All three are
   **must-have for the conventions document** — the file the agent actually reads as
   its instructions — and **recommended** for the README and the architecture
   document. This is presence-vs-coherence: the runner already asserted presence; this
   step is the judgement a deterministic check cannot make.
4. **Report a readiness verdict, then ask.** State "ready for SDD work" or "not ready
   for SDD work": not ready when the runner failed any must-have entry, or when the
   conventions document is missing any coherence element. Then name the specific files
   and the specific missing elements and **ask the caller whether to delegate drafting
   to `harny-document`**. Invoke `harny-document` only after an explicit yes.
5. Act on what it reports:
   - A **failed** check is addressed before spec work begins.
   - A **warned** check is named with its remediation but never blocks — recommended,
     not must-have. Every entry in the **security** family is recommended: report its
     warnings (for example, `.env` not git-ignored, commit-check hooks not active,
     no local secret scanner) so the caller can decide, and never treat one as a
     failure.
   - A **skipped** check is reported as coverage that could not be evaluated here
     (e.g. an absent tool), never treated as a pass.
   - A clean report (every check `ok`, `skip`, or `warn`) means the harness is ready;
     proceed.
6. Report back which checks failed, warned, or were skipped, so the caller's own
   checklist or audit trail can cite it.

## Guardrails

- **Never restate a command string.** This skill does not name what the readiness
  runner runs; it names the runner and its checks data and reads them live, the same
  discipline `harny-feedback` applies to its own stack-to-command mapping.
- **Never fix what it finds.** This skill reports and stops; it does not edit files,
  regenerate anything, or otherwise work around a failed or skipped check on the
  human's behalf.
- **Never invoke `harny-sync` archive mode on the human's behalf**, even when the
  readiness check reports a feature that looks shipped-but-unarchived. Name the
  finding; let the human (or `harny-sync` itself) decide.
- **The hand-off is offered, never taken unilaterally.** This skill does not write
  files and does not decide on the human's behalf that a gap should be filled — it
  states the verdict, names the gaps, and asks. `harny-document` runs only after an
  explicit yes.
- **Portability.** Always name the target as "this project's readiness runner and
  checks data (`.sdd/doctor/run-doctor.mjs` / `.sdd/doctor/checks.json`, or the
  project's equivalents)" so a user pointing this skill at their own repo needs no
  edit to this file.
- **Refer to other skills by name, never by path.** `harny-feedback` owns the
  per-turn and before-marking-a-task-done triggers; `harny-audit` owns mapping any
  finding onto its own severity buckets; `harny-sync` owns archive mode. None of
  their commands or definitions are restated here.
