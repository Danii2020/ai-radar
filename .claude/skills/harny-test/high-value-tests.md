# High-value tests

A test earns its place only if it can catch a **real regression** that the build,
the type checker, or a better-placed test wouldn't already catch. Coverage of a
contract line is not the goal — *protection against breakage* is. A test that must
be edited in lockstep with the code it mirrors (a "change-detector") costs
maintenance and gives false confidence; it is worse than no test.

Use this rubric to decide, for each candidate test: **write it, write it differently,
or don't write it.**

## The one question

> If a real bug were introduced here, would this test fail — and would it stay green
> through a harmless refactor?

- **Yes / Yes** → high value. Write it.
- **No** (a bug wouldn't trip it) → it's a tautology or a framework test. Don't write it.
- **Yes / No** (it also fails on harmless refactors) → it's a change-detector. Rewrite it
  to assert behavior, or drop it.

## Don't write these

1. **Tautologies** — assert a literal equals itself (a constant equals its own literal
   value). No logic under test; only fails when someone changes the constant on
   purpose. Constants are validated by the code that *uses* them, not by restating
   them.
2. **Third-party / framework tests** — exercising code you don't own, especially
   against mocked dependencies. Testing that a framework forwards props, that an ORM
   runs a query, or that a vendored component re-exports names is worthless when the
   dependency is mocked — you're then asserting your mock behaves like your mock.
   Trust libraries; test *your* glue at the feature level.
3. **Source-text grep tests** — reading a source file and regex-matching its contents,
   for example style class strings or migration/SQL text. These test *that a developer
   typed a string*, not that anything behaves. They break on any equivalent rewrite and
   pass even when the behavior is broken. Verify the **behavior** instead.
4. **File-existence and scaffold registries** — a hand-maintained list asserting that
   files exist. A missing file already fails the build and every test that imports it;
   the compiler and imports already catch these.
5. **Redundant duplicates of a stronger test** — a static/string assertion that
   "gestures at" behavior already covered by a real behavioral or integration test.
   Keep the strong one; drop the gesture. One global structural invariant asserted once
   is fine; it does not need to be re-asserted per file.
6. **Mechanical boilerplate cases** — the same trivial case (for example "throws on a
   bad input" / "returns empty on null") copied across dozens of identical thin
   pass-through functions. One representative test of the shared shape is enough.

## Do write these

- **Branching, arithmetic and mapping logic** — with representative and boundary
  inputs. Assert the computed output.
- **Guards and invariants you own** — business rules, gating, idempotency, anything the
  project implements and depends on.
- **Behavior at the seam, tested via the seam** — assert the *call shape* and the
  *returned or mapped value*, not the query string or the wire payload.
- **Security-critical behavior, against the real thing** — access control, triggers,
  stored procedures, and similar. Test these in an integration test against the real
  boundary, not a regex over configuration or migration text.
- **Real edge cases from the contract** — null/empty inputs, boundaries, "no-op when
  nothing to do", error propagation — where the code actually has a path for them.

## Picking the right tier

- Pure logic → unit test.
- Component output → render it in-process and assert visible behavior, never class
  names or markup soup.
- A real boundary — a database, an HTTP API, a queue, another module or service,
  security/trigger/stored-procedure behavior — → integration test, exercised against
  the real thing (or the project's own in-process stand-in for it).
- A user-visible flow across a UI (for example, a feature that touches components or
  interactions in a frontend app) → e2e test (for example Playwright, Cypress, or the
  project's own e2e runner — attributed examples, never the only option).
- A genuinely cheap structural invariant → one guard, asserted once.

## Using this in the SDD workflow

Intent acceptance criteria (ACs) are the **source of what to cover** —
but each one maps to the *cheapest test that would actually fail on a regression*, at
the right tier. Before writing a test for an AC, run it through
"The one question" above. If the only way to cover a line is a tautology, a framework
test, or a source-text grep, that line is better verified by a behavioral or
integration test, or by code review for pure styling — note it in the `tasks.md` outcome and move on rather than adding noise.
