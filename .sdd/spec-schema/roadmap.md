# Spec Schema: roadmap.md

> Standalone template for the "How" file of the 5-file SDD spec schema.
> Breaks the feature into ordered implementation phases, assesses risk, and
> maps every file that will be created or modified.

## Template

```markdown
# Roadmap: <Feature Name>

## Implementation Phases

### Phase 1: [Foundation]
**Goal**: [What this phase achieves]
**Dependencies**: None
**Estimated complexity**: Low/Medium/High

1. [Step 1]
2. [Step 2]

### Phase 2: [Core Logic]
**Goal**: [What this phase achieves]
**Dependencies**: Phase 1
**Estimated complexity**: Low/Medium/High

1. [Step 1]
2. [Step 2]

### Phase 3: [Integration]
**Goal**: [What this phase achieves]
**Dependencies**: Phase 2
**Estimated complexity**: Low/Medium/High

1. [Step 1]
2. [Step 2]

### Phase 4: [Testing & Validation]
**Goal**: [What this phase achieves]
**Dependencies**: Phase 3
**Estimated complexity**: Low/Medium/High

1. [Step 1]
2. [Step 2]

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| [risk] | Low/Med/High | Low/Med/High | [mitigation] |

## File Change Map
[List every file that will be created or modified, using the real file paths
and extensions from this codebase — not a placeholder language's extension]
- `path/to/new_file.ext` — CREATE — [purpose]
- `path/to/existing.ext` — MODIFY — [what changes]
```
