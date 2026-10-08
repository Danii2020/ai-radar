# Spec Schema: audit.md

> Standalone template for the audit file of the SDD spec schema. Only the
> auditor creates and writes it, on the first audit round; the architect never
> writes it. Every item cites an AC or a binding constraint. Label each piece of
> evidence `rerun`, `reused` or `unavailable`.

## Template

```markdown
# Audit: <Feature Name>

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS / FAIL / PARTIAL | [evidence] (rerun / reused / unavailable) |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| [from execution-plan.md] | PASS / FAIL | [evidence] |

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | [test and file] | [status] |

### Tier Results
Check against `execution-plan.md` § Validation: tiers and setup it names, a
named tier with no tests, a test at a tier it does not name.

| Tier | Status | Evidence |
|---|---|---|
| unit | [status] | [evidence] |

## Findings
| Id | Severity | Closure condition | Status |
|---|---|---|---|
| F1 | Critical / Major / Minor | [what closes it] | Open / Closed |

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | [date] | [verdict] | |

## Final verdict
APPROVED | APPROVED WITH RESERVATIONS | REJECTED

[Summary.]
```
