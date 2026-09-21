---
name: high-value-tests
description: Decide whether a test is worth writing/keeping. Use when writing tests (especially in the SDD test-writer step), reviewing a test suite, or pruning tests — to avoid tautologies, third-party/framework tests, source-text grep tests, and other change-detectors that add maintenance cost without catching real regressions.
metadata:
  author: daniel
  version: "1.0"
---

# High-value tests

A test earns its place only if it can catch a **real regression** that the build,
the type checker, or a better-placed test wouldn't already catch. Coverage of a
contract line is not the goal — *protection against breakage* is. A test that must
be edited in lockstep with the code it mirrors (a "change-detector") costs
maintenance and gives false confidence; it is worse than no test.

Use this skill to decide, for each candidate test: **write it, write it differently,
or don't write it.**

## The one question

> If a real bug were introduced here, would this test fail — and would it stay green
> through a harmless refactor?

- **Yes / Yes** → high value. Write it.
- **No** (a bug wouldn't trip it) → it's a tautology or a framework test. Don't write it.
- **Yes / No** (it also fails on harmless refactors) → it's a change-detector. Rewrite it to assert behavior, or drop it.

## Don't write these (low / negative value)

1. **Tautologies** — assert a literal equals itself.
   `expect(LOCALE).toBe("es-EC")`, `expect(DEFAULT_IVA_PCT).toBe(15)`. No logic under
   test; only fails when someone changes the constant on purpose. Constants are
   validated by the code that *uses* them, not by restating them.

2. **Third-party / framework tests** — exercising code you don't own.
   Testing a shadcn/Radix wrapper, that React forwards children, that an ORM runs a
   query, that a vendored component re-exports names. Especially worthless when the
   dependency is mocked — you're then asserting your mock behaves like your mock.
   Trust libraries; test *your* glue at the feature level.

3. **Source-text grep tests** — reading a source file and regex-matching its contents.
   - CSS/Tailwind class strings: `expect(src).toMatch(/grid-cols-1|min-w-0/)`.
   - SQL migration text: `expect(sql).toMatch(/security definer/i)`.
   These test *that a developer typed a string*, not that anything behaves. They break
   on any equivalent rewrite (reorder classes, reformat SQL, rename a CTE) and pass
   even when the behavior is broken. Verify the **behavior** instead (render and assert
   the outcome; run the migration against a real DB in an integration test).

4. **File-existence / scaffold registries** — `expect(existsSync("lib/foo.ts")).toBe(true)`
   for a hand-maintained list of files. A missing file already fails the build (tsc)
   and every test that imports it. The list only duplicates the compiler while
   demanding upkeep on every new feature.

5. **Redundant duplicates of a stronger test** — a static/string assertion that
   "gestures at" behavior already covered by a real behavioral or integration test.
   Keep the strong one; drop the gesture. (A boundary/architecture invariant enforced
   once globally — e.g. a single grep-gate — does not need to be re-asserted per file.)

6. **Mechanical boilerplate cases** — the same `"throws when the query errors"` /
   `"returns [] when null"` copied across dozens of trivial pass-through functions.
   One representative test of the error/empty contract is enough; don't multiply it
   across functions that share the identical thin shape.

## Do write these (high value)

- **Branching / arithmetic / mapping logic** — calculators, totals, IVA/margin math,
  row→view-model mapping, label building. Assert the computed output for representative
  and boundary inputs.
- **Guards and invariants you own** — "can't edit a confirmed receipt", role gating,
  reconciliation that must not drop related rows, idempotency you implement.
- **Behavior at the seam, via the seam** — repository functions tested through the
  chainable `Db` mock: assert the *call shape* and the *returned/mapped value*, not
  the SQL string.
- **Security-critical behavior, against the real thing** — RLS, security-definer RPCs,
  DB triggers (finance auto-feed, stock decrement/restore). These belong in
  `integration/*.live.test.ts` against real Postgres — a regex over the migration is
  not a substitute.
- **Real edge cases from the contract** — null/empty inputs, boundaries, "no-op when
  nothing to do", error propagation — where the function actually has a code path for them.

## Picking the right tier (so the test is both real and stable)

- Pure logic → unit test.
- Component output → render (SSR string per project convention) and assert visible
  behavior/text, never the className soup.
- DB/RLS/trigger/RPC behavior → live integration test against Postgres.
- A genuinely cheap structural invariant (e.g. migrations are sequentially numbered,
  no import crosses an architectural boundary) → one structural guard, asserted once.

## Using this in the SDD workflow

Contract guarantees and intent success criteria are the **source of what to cover** —
but each one maps to the *cheapest test that would actually fail on a regression*, at
the right tier. Before writing a test for a contract line, run it through "the one
question" above. If the only way to "cover" a line is a tautology, a framework test, or
a source-text grep, that line is better verified by a behavioral/integration test (or by
code review for pure styling) — note that and move on rather than adding noise.
