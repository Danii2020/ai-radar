# Spec Schema: intent.md

> Standalone template for the "Why" file of the SDD spec schema. A feature has
> three architect-written files (`intent.md`, `execution-plan.md`, `tasks.md`);
> `audit.md` belongs to the auditor. A role producing specs emits a file shaped
> exactly like the template below, with every bracketed placeholder replaced by
> real, feature-specific content. Do not leave placeholder brackets in an
> emitted file. Describe observable outcomes. External API, data and security
> obligations belong here; internal names and signatures do not.

## Template

```markdown
# Intent: <Feature Name>

Revision: N
Approval: Pending | Approved revision N by <person> on <date>

## Outcome
[What changes for the user or system, in two or three sentences.]

## Acceptance criteria
- **AC1** [Observable behavior.]
  Example: [input] -> [output or error]
- **AC2** [Observable behavior.]
  Example: [input] -> [output or error]
- **AC3** (compatibility) [What must keep working.]

## Scope
**In**
- [Item]

**Out**
- [Item]

## Constraints
- [Technical, business or compatibility constraint]

## Open questions
- [Question, or "None"]

## Revision history
- Revision 1 (<date>): [what changed]
```
