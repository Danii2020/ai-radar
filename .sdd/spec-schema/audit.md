# Spec Schema: audit.md

> Standalone template for the compliance-tracking file of the 5-file SDD spec
> schema. Rows are seeded PENDING; the role that audits a feature (e.g. an
> auditor-style role) fills in status and verification after implementation.

## Template

```markdown
# Audit: <Feature Name>

## Requirements Checklist
| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | [requirement from intent] | intent.md | PENDING | |
| R2 | [requirement from intent] | intent.md | PENDING | |

## Contract Compliance
| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | [interface/guarantee from contract] | PENDING | |
| C2 | [interface/guarantee from contract] | PENDING | |

## Test Coverage
| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | [test description] | PENDING | |
| T2 | [test description] | PENDING | |

## Audit Log
| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| | | | | |

## Final Verdict
_(to be completed by the auditing role)_

**Status**: PENDING

**Summary**:

**Critical Issues** (must fix before merge):

**Warnings** (should fix, not blocking):

**Recommendations** (nice to have):
```
