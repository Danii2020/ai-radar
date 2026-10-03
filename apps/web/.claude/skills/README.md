# The `harny-*` skill shape contract

This directory holds the `harny-*` skill library scaffolded by `npx harny init` — the
same ten-skill SDD pipeline library harny's own repository runs, shaped to the
portable Agent Skills specification (https://agentskills.io/specification) so any
compliant tool can discover it directly. Every skill is a real, standalone directory
containing a `SKILL.md` (and, for three of them, one bundled resource file) — never a
symlink and never a partial copy.

**This is the extension point.** A user adds a ninth `harny-*` skill (or a tenth, or a
completely unrelated skill) by satisfying this document and nothing else.

## Frontmatter — the six portable keys, and no others

```yaml
---
# The six portable Agent Skills fields. NO OTHER KEY IS PERMITTED.
name: harny-<action>                 # REQUIRED. kebab-case, `harny-` prefix, verb-shaped.
description: >-                      # REQUIRED. <= 1024 chars. Must state WHAT it
  ...                                #   does AND WHEN to use it — the harness selects on this.
license: MIT                         # OPTIONAL.
compatibility: >-                    # OPTIONAL, <= 500 chars. Prerequisites, e.g. which
  ...                                #   directories must exist.
allowed-tools: Read, Glob, Grep      # OPTIONAL. Least privilege. Omit to inherit.
metadata:                            # OPTIONAL free-form map.
  author: your-name
  version: "1.0"
  harny-role: sdd-architect          # the pipeline role that invokes it, or `shared`
  harny-writes: specs/<feature>/**   # every path the skill may write, or `none`
---
```

`name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools` are the
only frontmatter keys a `harny-*/SKILL.md` may declare — the six fields defined by the
portable Agent Skills specification. Any other key (for example
`disable-model-invocation`, `context`, `agent`, `paths`, `model`, `when_to_use`) is a
tool-specific extension that a spec-compliant validator may reject outright.

## Body — five required sections, in this order

```markdown
# <Title>

<One paragraph: what this skill is for and who invokes it.>

## When to use this
<Bulleted triggers, including automatic invocations by name.>

## Inputs
<Every file/artifact read, by path, and what is required vs. optional.>

## Steps
<Numbered, imperative. The substance of the skill.>

## Guardrails
<Hard rules — what this skill must never do, and what it hands off instead.>
```

## Binding rules

1. **Portable frontmatter only.** Only the six fields above. Any other key is a
   violation.
2. **`disable-model-invocation` is specifically forbidden**, both by rule 1 and because
   it would block a skill from being preloaded into an agent that depends on it.
   Destructive skills (e.g. `harny-sync` archive mode) are protected by
   **preconditions in the `## Guardrails` section**, not by an invocation flag.
3. **A real directory in every skill root this project uses, always.** Each skill lives
   at `<root>/harny-<action>/SKILL.md`, where `<root>` is one of this project's actual
   skill-discovery directories (for example `.agents/skills/`, `.claude/skills/`, or
   `.kiro/skills/` — whichever your tool documents). A skill copy is never a symlink and
   never partial — every root that carries it carries the whole directory.
4. **Name discipline.** `harny-` prefix; never colliding with an existing skill or agent
   `name:`.
5. **Reference other skills by name, never by path** — e.g. "run the `harny-standards`
   skill", not a hardcoded path into one specific tool's directory. A tool-neutral file
   must not hardcode one tool's directory as the only place a reader can find something.
6. **Bundled resources are allowed** next to `SKILL.md` and are referenced by bare
   filename (e.g. `adr-template.md`), loaded on demand.
7. **One action per skill.** If a skill's `## Steps` splits cleanly into two independent
   outcomes, it is two skills — except where the two share all their preconditions and
   state, which is the documented reason `harny-sync` carries two modes rather than
   splitting into `harny-lookup` / `harny-archive`.

## Adding a ninth skill

1. Create `harny-<action>/SKILL.md` in each skill root this project actually uses,
   following the frontmatter and body shape above — a real directory in every root,
   never a symlink.
2. If a role should preload it at startup, add it to that role's own instructions or
   configuration, following whatever mechanism your tool uses for that.
3. Nothing else needs to change.
