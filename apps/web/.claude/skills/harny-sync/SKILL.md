---
name: harny-sync
description: >-
  Maintains the current-state knowledge base under specs/current/ and specs/archived/.
  Has two modes: lookup (read-only — reads specs/current/_index.md plus at most three
  matching capability docs and returns a brief of current truth, so a new proposal
  cannot silently contradict a shipped decision) and archive (moves an approved
  feature's specs/<feature>/ to specs/archived/<feature>/ after verifying preconditions,
  then updates the affected capability docs and regenerates the index). Use lookup
  before drafting any new spec, and use archive right after a feature's Shipped date is
  stamped. Invocable on demand by a human or any agent; invoked automatically by
  harny-propose before drafting and by harny-document's post-audit hand-off.
license: MIT
compatibility: >-
  Lookup requires specs/current/_index.md to exist (degrades gracefully with an empty
  brief if it does not). Archive requires the target feature's specs/<feature>/
  directory with all five files and a Shipped: header already in place.
allowed-tools: Read, Write, Bash, Glob
metadata:
  author: daniel
  version: "1.0"
  harny-role: shared
  harny-writes: "lookup: none. archive: specs/**"
---

# harny-sync

Maintains `specs/current/` (the fast-lookup picture of current truth) and
`specs/archived/` (the byte-identical historical record of every shipped feature),
across two modes that share all their preconditions and state.

## When to use this

- **Lookup**, invoked automatically as Step 0 of `harny-propose`, before drafting any
  spec file for a new feature.
- **Archive**, invoked automatically inside `harny-document`'s post-audit hand-off,
  after the `Shipped:` stamp is written and the human has signed off.
- Invocable directly, in either mode, by a human or any other agent — e.g. "what do we
  already know about X?" or "archive feature Y now."

## Inputs

- **Lookup**: `specs/current/_index.md`; the capability doc(s) it routes to.
- **Archive**: the target feature's full `specs/<feature-name>/` directory (all five
  files); the current `specs/current/<capability>.md` doc(s) for every
  capability the feature's `contract.md` names as affected — or `capability-template.md`
  (bundled next to this file) if a named capability has no file yet; `specs/current/_index.md`
  and every `specs/archived/*/decisions/*.md` (to regenerate the ADR registry table and
  to check each ADR's own `Capability:` field directly — see step 5).

## Steps

### Mode `lookup` (read-only)

1. Read `specs/current/_index.md` in full. If it is absent or unreadable, report "no
   knowledge base" and return an empty brief — never fabricate one.
2. Match the request against the index's § Keyword lookup table to select **at most 3**
   capabilities.
3. Read `specs/current/<capability>.md` in full for each matched capability.
4. Return a brief containing: the matched capabilities; the relevant Requirements (with
   their stable IDs) and Scenarios **quoted verbatim**; the capability's invariants; its
   open reservations; related ADR numbers; and the archive paths to read *only if* the
   caller needs the underlying "why".
5. **Bounded reads**: this mode reads at most 4 files total (`_index.md` plus ≤3
   capability docs) and never globs `specs/archived/**`. This bound is what makes
   lookup fast; do not widen it.
6. If nothing matches, say so explicitly, name the nearest capability by keyword
   distance, and tell the caller to fall back to full codebase exploration.
7. **Writes nothing, ever**, in this mode.

### Mode `archive` (destructive — preconditions are mandatory)

Preconditions, **all** required; on any failure, refuse and report which one failed,
without moving anything:
- `specs/<feature>/audit.md` has a final verdict of `APPROVED` or
  `APPROVED WITH RESERVATIONS` (never `REJECTED`).
- The human has signed off at the post-audit gate.
- All five spec files exist and are non-empty.
- `specs/<feature>/intent.md` carries a `Shipped:` header.
- `specs/archived/<feature>/` does not already exist.
- `<feature>` is neither `current` nor `archived`.

Procedure:
1. Record the SHA-256 of all five files.
2. Move `specs/<feature>/` to `specs/archived/<feature>/` as a whole directory. **Check
   whether the source path is tracked first** (e.g. `git ls-files --error-unmatch
   specs/<feature>/ 2>/dev/null` or equivalent): if tracked, move with `git mv` so rename
   detection and history survive; if untracked, move with a plain `mv`. Tolerate either
   state — do not assume one; a feature archived before its first commit is still
   untracked, and both must work.
3. Re-compute SHA-256 of all five files; on any mismatch, restore the directory to
   `specs/<feature>/` and abort, reporting the differing paths. **The SHA-256 check, not
   which move command ran, is what actually proves integrity in either case** — `git mv`
   is a history-quality improvement, not a correctness dependency.
4. Determine affected capabilities from the feature's (now-archived) `contract.md`.
5. For each affected capability:
   - **If `specs/current/<capability>.md` already exists**, update it in place:
     add/modify/retire Requirements and their Scenarios — **merging, never
     overwriting**: a Requirement not mentioned by this feature is left untouched;
     carry forward the feature's open reservations; add the feature to
     § Contributing features with its `Shipped:` date.
   - **If it does not exist yet** (the feature introduces a genuinely new
     capability), create it from `capability-template.md` (bundled next to this
     file) — **never invent a different shape**. Fill in every section the template
     has, and populate `## Related ADRs` and `## Contributing features` (both
     empty in the template) the same way step 6 below does, not by leaving the
     template's placeholder rows in place.
   - **Every `### Requirement:` gets a stable ID** in that capability's own
     namespace (its short prefix, e.g. `CLI-`, `SW-`), assigned by incrementing
     past the highest existing number in that file — never renumbered later.
6. Regenerate `specs/current/_index.md`'s five tables from the capability docs and the
   ADR files on disk (`specs/archived/*/decisions/*.md`). When rebuilding
   `## Decisions (ADR registry)` and each capability doc's own `## Related ADRs`
   table, **open each ADR file directly and read its own `Capability:` field** —
   do not assume an ADR belongs to the capability of the feature that wrote it, and
   do not copy one capability doc's ADR list into another's. Getting this wrong is an
   easy, silent mistake: a capability doc can end up listing every ADR in the repo
   regardless of which capability each one actually belongs to, while the capability
   the ADR really belongs to shows "none yet." Reading each ADR's own field directly,
   every time, is what prevents it.
7. Report: capabilities touched, statements added/modified/retired, ADRs registered.

## Guardrails

- **Never set `disable-model-invocation`** — even though archive mode is destructive,
  protect it with the preconditions above, not an invocation flag that would also block
  this skill from being preloaded into a subagent.
- **Archive is atomic or it didn't happen.** A checksum mismatch after the move always
  restores the original directory before reporting failure — never leave the feature
  half-moved.
- **`_index.md` is derived, never hand-edited by this skill or anyone else.** If it
  ever disagrees with a capability doc, the capability doc wins; regenerate the index
  from the capability docs, never the reverse.
- **Merge, never overwrite**, when updating a capability doc — a statement the incoming
  feature does not mention is not this skill's business to touch.
- **Lookup never globs `specs/archived/**`.** If the 4-file bound isn't enough to
  answer the request, say so and hand off to full exploration rather than silently
  widening the read.
