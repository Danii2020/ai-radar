# Spec Schema: execution-plan.md

> Standalone template for the single reviewed plan of the SDD spec schema. Keep
> binding constraints separate from revisable suggestions. Leave out exact file
> lists, pseudocode, signatures and test bodies unless an external contract or a
> repo rule needs them. The Validation section is the only test plan: approving
> the specs approves test scope. Every Validation row cites an AC.

## Template

```markdown
# Execution Plan: <Feature Name>

## Guidance consulted
- [Repo rules, docs and specs read]

## Ownership
- [Modules or areas that own the change]
- Affected `specs/current` capabilities: [list, or "none"]

## Binding constraints
- [Constraint] (source: [rule, spec or external contract])

## Proposed approach
Revisable by the executor if it records why.
- Decision: [what] — rationale: [why]; rejected: [alternative and why]

## Consumers and migration
- [Existing consumers, tests and docs to migrate, or "none"]

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| [Risk] | Low/Med/High | Low/Med/High | [Mitigation] |

## Validation
One row per AC.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | [what shows it] | [tests] | unit / integration / e2e | [inferred from repo] | none / [what to add] | [cmd] | [cmd] | [dir] |

## Revision log
- Revision 1 (<date>): [what changed]
```
