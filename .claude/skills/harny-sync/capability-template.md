# <Capability Title> Specification

> Last synced: <YYYY-MM-DD>. Owned artifacts: <real repo paths/globs>.

## Purpose

<2-3 lines: what this capability is, and why it exists as its own capability
rather than folding into another one.>

## Requirements

### Requirement: <CAP-PREFIX>-1 — <short descriptive name>

The system SHALL <statement, phrased as a SHALL clause>.

**Source:** <feature-name> · <file>.md § <section, or guarantee/criterion number>

#### Scenario: <name>
- **WHEN** <the triggering condition>
- **THEN** <the expected behavior>

<Repeat one `### Requirement:` block per fact this capability establishes.
IDs are stable and monotonic within this capability, prefixed with the
capability's own short prefix (e.g. `CLI-`, `SW-`, `TG-`) — never reused or
renumbered once assigned; a superseded Requirement is struck through
(`~~retired, see <CAP>-N~~`) and kept, never deleted.>

## Invariants

<Numbered. What must not break, and what breaks if it does. Optional if the
capability has no invariants beyond its Requirements — omit the section
rather than leave it empty.>

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|

<One row per non-blocking finding accepted at ship time and still open, for
this capability specifically. Omit the section (or write "None yet") rather
than leave the table with only a header if there are none.>

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|

<One row per shipped feature that created or modified a Requirement in this
file, most recent last. This is the capability-local mirror of
`_index.md`'s "Synchronized Changes" table — every feature listed here must
also list this capability doc under its own row there.>

## Related ADRs

| ADR | Title | Status |
|---|---|---|

<List only ADRs whose own `Capability:` field names THIS capability — check
each candidate ADR's file directly rather than assuming; do not list an ADR
here just because it was written by the same feature that touches this
capability. Omit the section (or write "None yet") rather than leave the
table with only a header if none apply.>
