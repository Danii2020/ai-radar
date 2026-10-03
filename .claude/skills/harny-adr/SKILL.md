---
name: harny-adr
description: >-
  Writes Architecture Decision Records for the significant decisions found in an
  approved feature's contract.md and roadmap.md, one file per decision, at
  specs/archived/<feature>/decisions/NNNN-<slug>.md with a globally monotonic number,
  and registers each one in specs/current/_index.md's ADR registry. Use this right
  after harny-sync has archived a feature (the decisions/ directory must already exist
  inside the archived feature's directory). Invoked by harny-document's post-audit
  hand-off, or directly by a human wanting to backfill decisions for an already-archived
  feature that was approved after this skill shipped.
license: MIT
compatibility: >-
  Requires the target feature to already be archived at specs/archived/<feature>/ (this
  skill runs after harny-sync's archive move, never before) and specs/current/_index.md
  to exist for the registry update.
allowed-tools: Read, Write, Bash, Glob
metadata:
  author: daniel
  version: "1.0"
  harny-role: sdd-documentation
  harny-writes: specs/archived/<feature>/decisions/**
---

# harny-adr

Writes one Architecture Decision Record per significant decision an approved feature
made, so rationale that would otherwise be stranded inside a contract's prose or an
audit log's findings becomes a durable, individually citable artifact.

## When to use this

- Invoked by `harny-document`'s post-audit hand-off, after `harny-sync` has moved the
  feature into `specs/archived/<feature>/`.
- Invocable directly by a human for any feature archived after this skill shipped.
- **Never** for a feature that was already archived before this skill existed in this
  project, or for any decision not traceable to an approved `contract.md`/`roadmap.md`
  — see Guardrails.

## Inputs

- The archived feature's `contract.md` and `roadmap.md` at
  `specs/archived/<feature-name>/`.
- The bundled `adr-template.md` (next to this file).
- Every existing `specs/archived/*/decisions/*.md`, to determine the next ADR number.
- `specs/current/_index.md`'s § Decisions table, to register new rows.

## Steps

1. **Scan the feature's `contract.md` and `roadmap.md`** for candidate decisions.
2. **Judge significance.** A decision earns an ADR if it meets **at least one** of:
   - (a) the contract or roadmap records a choice between two or more named viable
     options;
   - (b) it constrains future features (a rule, invariant, or reserved name others
     must obey);
   - (c) it supersedes or diverges from a previously shipped decision;
   - (d) it deliberately accepts a known cost, reservation, or unverifiable claim.
   Anything meeting none of these stays in the archived contract, where it already is
   — do not write filler ADRs.
3. **Cap at 7 ADRs per feature.** If more than seven decisions qualify, write the seven
   highest-impact and list the rest in the hand-off summary as deliberately not
   promoted.
4. **Allocate the number.** `NNNN` is a zero-padded 4-digit number, monotonic **across
   the whole repo**, not per feature. Scan `specs/archived/*/decisions/*.md` for the
   current maximum and allocate the next integer. If a number is already taken by the
   time you write (a race), rescan and allocate the next one.
5. **Write each ADR** at `specs/archived/<feature-name>/decisions/NNNN-<slug>.md`,
   following `adr-template.md` exactly: Status, Date, Feature, Capability, Source
   (the exact `contract.md § …` or `roadmap.md Phase …` citation), Trigger (which of
   (a)–(d)), Context, Decision, Alternatives considered, Consequences, Follow-ups.
6. **Register each ADR** as a new row in `specs/current/_index.md`'s § Decisions
   table (ADR number, title, status, capability, path).
7. **Report**: which decisions became ADRs, which capability each belongs to, and
   (if applicable) which candidates were not promoted and why.

## Guardrails

- **No backfill.** Features already archived before this skill existed in this project
  get **no** ADRs — reconstructing rationale for shipped work retroactively risks
  inventing it, and their reasoning already exists in their own archived contracts and
  audit logs. ADRs apply only to features approved from the point this skill was
  introduced, forward.
- **Never write an ADR for a decision that fails all four significance criteria.**
- **Never exceed 7 ADRs for one feature.**
- **Never renumber or reuse an ADR number**, even for a superseded or deprecated one —
  mark its Status field instead.
- **Run only after the archive move.** The `decisions/` directory this skill writes
  into lives inside `specs/archived/<feature>/`, which does not exist until
  `harny-sync` archive mode has already run.
