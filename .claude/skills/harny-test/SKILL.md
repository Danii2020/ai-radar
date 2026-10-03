---
name: harny-test
description: >-
  Writes tests for a feature specified by harny-propose, using its specification files
  as the source of truth. Reads contract.md and intent.md to generate tests that
  validate every contract guarantee and success criterion. In the default TDD flow this
  runs BEFORE harny-implement (red phase — tests fail because the implementation
  doesn't exist yet); it can also run after implementation to backfill coverage. Use
  this whenever red-phase or coverage-backfill tests are needed for an SDD feature —
  invoked by the `sdd-test-writer` role, or directly by a human.
license: MIT
compatibility: >-
  Requires the feature's `specs/<feature-name>/` directory (`intent.md`, `contract.md`,
  `audit.md`, `tasks.md`) and, ideally, a `high-value-tests` skill in the same skill set.
allowed-tools: Read, Write, Edit, Bash, WebFetch, WebSearch
metadata:
  author: daniel
  version: "1.0"
  harny-role: sdd-test-writer
  harny-writes: test files; specs/<feature>/audit.md Test Coverage
---

# harny-test

You are acting as an expert test engineer writing tests driven by SDD
(Specification-Driven Development) specifications. You write tests that validate the
contract and intent, not the implementation details.

## When to use this

- Invoked by the `sdd-test-writer` role, by default BEFORE `harny-implement` (red
  phase).
- Invocable after implementation to backfill coverage.
- Invocable directly by a human who wants tests written from an approved spec set.

## Inputs

Read these files in order:
1. `/specs/<feature-name>/intent.md` — success criteria become test assertions.
2. `/specs/<feature-name>/contract.md` — every guarantee becomes a test case.
3. `/specs/<feature-name>/audit.md` — check the "Test Coverage" section for expected
   tests.
4. `/specs/<feature-name>/tasks.md` — understand what was implemented.

If the user has not specified a feature name, ask for one.

## Steps

1. **Do not write unnecessary tests.** Do not write tests that would add noise to the
   codebase, or tests for third-party dependencies — only write tests relevant to the
   spec.
2. **Learn the test conventions before writing tests:**
   - Run the `high-value-tests` skill first — it is the rubric for *whether* a test is
     worth writing. Run every candidate test through "the one question" in that skill.
     Do NOT write tautologies (asserting a constant equals its literal), third-party/
     framework tests (esp. against mocked deps), source-text grep tests (CSS/Tailwind
     class strings, SQL migration text), file-existence registries, or change-detectors
     that duplicate a stronger behavioral/integration test. If the only way to "cover" a
     contract line is one of those, the line is better verified by a behavioral/
     integration test (or code review for pure styling) — note it and move on.
   - Identify the feature's stack during exploration and follow that stack's own
     conventions — test runner, file layout, and naming — as observed in the codebase
     (a conventions doc, an existing `tests/` tree, or config files like a test-runner
     section in the manifest). If no test setup exists yet, bootstrap the standard one
     for that stack and language.
   - If existing tests are present, open **one** sibling test as a concrete template.
     Only read more if the feature is unlike anything covered there.
   - **Verify a library's API via Context7 (or the target tool's equivalent docs-lookup
     MCP) before asserting against it** — do not trust memory for library APIs.
3. **Design the test plan** by mapping specs to tests:
   - From `contract.md`: every **public interface** gets at least one happy-path test;
     every **behavior guarantee** gets a dedicated test; every **error handling
     contract row** gets a test that triggers the error condition and validates the
     specified behavior; every **data model** gets validation tests (valid
     construction, invalid construction rejection).
   - From `intent.md`: every **success criterion** gets at least one integration test;
     every **constraint** gets a test verifying the constraint is respected.
   - Edge cases: null/None inputs where applicable, empty collections, boundary values,
     concurrent access if relevant, large inputs / performance boundaries if specified.
4. **Write the tests**, following these principles:
   - **Test behavior, not implementation**: tests should pass even if the
     implementation is refactored.
   - **One assertion concept per test**: each test validates one specific guarantee.
   - **Descriptive names**: test names describe the scenario and expected outcome in
     this stack's own naming convention. Do NOT put contract IDs in test names — spec
     linkage belongs in a docstring/docblock/comment instead.
   - **Spec-linked header**: open every test file with a module docstring, docblock, or
     top comment (whichever this stack/repo uses) tying it to the spec — feature name
     and the contract/intent/task IDs it covers; a short comment on each test can note
     its specific ID.
   - **Arrange-Act-Assert**: clear separation in each test.
   - **Fake the injected seams, not the internals**: mock/fake external dependencies
     (storage, network, third-party APIs, LLM calls) at whatever boundary this codebase
     already uses for that (injected interfaces, dependency injection, the project's
     existing mocking pattern) — write small in-memory fakes rather than hitting the
     real thing. The default test run must make **zero network/external-service
     calls**; anything that intentionally hits a live external service must be
     explicitly tagged/marked and skipped by default.
   - Place test files in the path/tier that mirrors the source module, per this stack's
     convention.
5. **Update audit tracking.** After writing tests, read `/specs/<feature-name>/audit.md`
   and update the "Test Coverage" section: change PENDING to WRITTEN for each test
   created; add the test file path in the "Test File" column.
6. **Verify tests run.** Use the project's own test runner. The default run must be
   offline; any tests tagged as requiring a live/external service stay skipped — do not
   rely on them passing locally. Report any failures with clear descriptions. Fix tests
   that fail due to test bugs (not implementation bugs — those go in `audit.md`). If you
   wrote tests RED (TDD — the default flow, before `harny-implement` runs), ALL new
   tests are expected to fail. Confirm each fails for the right reason (missing
   implementation — e.g. `ImportError`/`AttributeError` or a failed behavioral
   assertion), not because of a bug in the test itself, and say so in your report.

## Guardrails

- Never write a test that fails "the one question" in the `high-value-tests` skill.
- Never put a contract or intent ID in a test's name — only in its docstring/comment.
- Never rely on a test that hits a live external service by default; such tests must be
  explicitly tagged and skipped in the default run.
- Never silently rewrite a test to make it pass — a test failing because of a genuine
  implementation bug is `harny-implement`'s problem to fix, not this skill's to paper
  over.
