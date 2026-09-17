# Spec Schema: contract.md

> Standalone template for the "What" file of the 5-file SDD spec schema.
> Defines every public interface, data model, behavior guarantee, and error
> condition the feature must satisfy. This is the primary guide consumed by a
> role that implements the feature.

## Template

```markdown
# Contract: <Feature Name>

## Interfaces

### Public API
[Define every public function, class, or endpoint this feature exposes]

IMPORTANT: write this in the **actual programming language of the target
codebase** (e.g. TypeScript, Go, Ruby, Python — whatever codebase exploration
found), using that language's real syntax and the repo's actual naming/typing
conventions. Never default to a placeholder language unless the codebase
itself is written in it. The block below is illustrative shape only, not a
language to copy literally:

\```<real-language-fence, e.g. ts>
// Function signatures with full type annotations, in the codebase's own language
// and matching its existing signature conventions (param naming, error handling, etc.)
\```

### Data Models
[Define all new or modified data structures]

\```<real-language-fence>
// New/modified types or classes, in the codebase's own language and type system
\```

### State Changes
[How this feature interacts with the application state]

## Behavior Guarantees
1. [Invariant 1: "X will always Y when Z"]
2. [Invariant 2]
...

## Error Handling Contract
| Error Condition | Behavior | User Impact |
|---|---|---|
| [condition] | [what happens] | [what user sees] |

## Dependencies
- [Internal module dependencies]
- [External package dependencies with versions]

## Integration Points
- [How this connects to existing modules]
- [How this connects to existing workflows]
```
