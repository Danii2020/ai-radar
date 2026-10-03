#!/usr/bin/env node
/**
 * The shared, tool-neutral feedback runner (see `templates/hooks/README.md` for the
 * canonical behavior this script implements). Copied byte-for-byte into every
 * scaffolded project at `.sdd/feedback/run-feedback.mjs` (contract.md BG-11) — its
 * bytes never vary by tool. Per-tool wiring (which event maps to which mode below,
 * and how findings are returned to the agent) lives entirely in each tool's own
 * generated hook config, never here.
 *
 * This is one of two generated entry-point scripts (the other is
 * `.sdd/doctor/run-doctor.mjs`, readiness-doctor's readiness runner); both import
 * their probe evaluator from a third generated file, `.sdd/shared/probes.mjs`
 * (`templates/shared/probes.mjs`, copied byte-for-byte alongside this one) rather
 * than each carrying its own copy — the generated feedback runtime is therefore two
 * files, not one, though this script's own behavior is unchanged.
 *
 * Invocation: `node run-feedback.mjs <accumulate|run>`, run with `cwd` set to the
 * target repo root. The tool's raw hook event is piped in as JSON on STDIN.
 *
 * - `accumulate` reads a turn-key field (the first available of `turn_id`,
 *   `session_id`, `sessionId`, `conversation_id`) and `tool_input.file_path` from
 *   STDIN, appends the resolved absolute path to
 *   `.sdd/feedback/.turns/<turn-key>`, and exits 0. It never executes a mapped
 *   command (BG-3).
 * - `run` additionally takes `--commands <path-to-json-file-or-inline-json>`, a
 *   JSON array of `FeedbackCommand`-shaped objects (this script never hard-codes
 *   a command string itself — BG-7 — a generated per-tool hook config supplies
 *   this value at `harny init` time, either as a file path or as inline JSON
 *   text embedded directly in the hook's own command string). It reads the turn
 *   file for the same turn key, dedupes the
 *   accumulated paths to an absolute-path set, evaluates each command's `requires`
 *   probe (skipping with a notice, never a failure, when it resolves false — BG-9),
 *   then executes the survivors exactly once. A `per-file` command receives only
 *   the deduped paths that match its declared `extensions` (no filter when absent
 *   or empty) and that still exist on disk when the command is evaluated; when
 *   that filtered set is empty the command is skipped silently — never spawned
 *   with zero path arguments (feedback-path-hygiene). `whole-project` commands
 *   receive no paths, as before. The turn file is deleted, unconditionally, so a
 *   reused turn key cannot leak into the next turn, and the runner exits.
 * - `run --whole-project` (A1, CI-only) is the same `run` mode with one boolean
 *   flag set, never a third mode. It bypasses turn state entirely: no STDIN turn
 *   key is read or required, `.sdd/feedback/.turns/` is never read, written, or
 *   deleted, and every command runs unconditionally exactly once. `per-file`
 *   commands receive exactly one argument, `.` (the repo root is the whole
 *   project), in place of the turn's touched paths — unconditionally, whatever
 *   `extensions` a command declares: neither the extension filter nor the
 *   existence check applies here (feedback-path-hygiene). The `requires` probe
 *   path is identical to normal `run` mode (BG-9). `stop_hook_active` is never
 *   read or honored under this flag — CI has no re-entry/loop-guard concept, so a
 *   finding always exits 2 (BG-19).
 * - `run --keep-turn` (SF-3) is the same `run` mode with one more boolean flag
 *   set, never a third mode. It is identical in every respect — the same turn
 *   key, the same commands, the same filters, the same probes, the same exit
 *   codes — except that the turn file is NOT deleted at the end. A later run
 *   without the flag reads the same paths again and deletes the file as usual,
 *   so a check made early (at a subagent's own completion) can never consume a
 *   finding the enclosing turn still has to report (SF-4). It is inert under
 *   `--whole-project`, which reads no turn state at all.
 * - `run --staged` (commit-checks CC-2) is the same `run` mode with a third boolean
 *   flag, never a new mode. Its paths come from git instead of a turn file: the files
 *   staged for the next commit (Added, Copied, Modified, Renamed; never deleted). It
 *   runs per-file commands only, since whole-project checks stay in CI where a slow
 *   type-check cannot push people into bypassing the commit hook. It reads no stdin,
 *   ignores `stop_hook_active`, and exits 2 on any finding, so a git `pre-commit`
 *   hook that calls it blocks the commit.
 *
 * Exit code convention for `run`: `0` when the turn produced no blocking-worthy
 * findings (a clean pass, a skip-only outcome, or an empty turn); `2` when a mapped
 * command's failure would otherwise warrant forcing the tool's blocking channel —
 * unless the tool's re-entry flag (`stop_hook_active`) is set on STDIN, in which
 * case no blocking response is ever emitted (BG-5), so this loop can never trip a
 * tool's own consecutive-block override. Under `--whole-project`, exit `2` is
 * never mediated by `stop_hook_active` (BG-19) — it is CI's own red/green signal.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { probeSatisfied as requirementMet } from '../shared/probes.mjs';

/** Where the runner accumulates one turn's touched paths, repo-relative
 *  (contract.md's `TOUCHED_FILES_DIR`). Literal here, not imported: this script is
 *  copied verbatim into target repos and cannot reach into `src/feedback.ts`. */
const TOUCHED_FILES_DIR = '.sdd/feedback/.turns';

function readStdinJson() {
  let raw = '';
  try {
    raw = fs.readFileSync(0, 'utf8');
  } catch {
    raw = '';
  }
  if (!raw.trim()) {
    return {};
  }
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

/** Turn-key precedence: `turn_id` -> `session_id` -> `sessionId` -> `conversation_id`
 *  (contract.md § Data Models "Touched-file accumulation record"). */
function resolveTurnKey(payload) {
  return payload.turn_id || payload.session_id || payload.sessionId || payload.conversation_id || undefined;
}

function turnFilePath(cwd, turnKey) {
  return path.join(cwd, ...TOUCHED_FILES_DIR.split('/'), turnKey);
}

function runAccumulate(cwd) {
  const payload = readStdinJson();
  const turnKey = resolveTurnKey(payload);
  const filePath = payload.tool_input && payload.tool_input.file_path;

  if (!turnKey || !filePath) {
    // Nothing to accumulate against; never fatal (BG-8's non-fatal posture
    // extends to malformed/partial hook payloads).
    process.exit(0);
  }

  const resolved = path.resolve(cwd, filePath);
  const file = turnFilePath(cwd, turnKey);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(file, `${resolved}\n`);
  process.exit(0);
}

function parseRunArgs(argv) {
  let commandsPath;
  let wholeProject = false;
  let keepTurn = false;
  let staged = false;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--commands') {
      commandsPath = argv[i + 1];
      i += 1;
    } else if (argv[i] === '--whole-project') {
      wholeProject = true;
    } else if (argv[i] === '--keep-turn') {
      keepTurn = true;
    } else if (argv[i] === '--staged') {
      staged = true;
    }
  }
  return { commandsPath, wholeProject, keepTurn, staged };
}

/**
 * (specs/monorepo-mode.) Normalizes a parsed `--commands` value to the runner's
 * one internal shape: a list of `{ dir, commands }` components, in payload
 * order. The bare-array form (today's shape) becomes one implicit `.` component
 * — this IS today's value, not a special case (MC-5). The object form
 * `{ components: [...] }` becomes itself, each entry defaulting `dir` to `'.'`
 * and `commands` to `[]`. Anything else (non-array, non-object, an object with
 * no `components` array) normalizes to `[]` — the unchanged tolerant posture:
 * no commands, no output, exit 0.
 */
function normalizeCommandsPayload(parsed) {
  if (Array.isArray(parsed)) {
    return [{ dir: '.', commands: parsed }];
  }
  if (parsed && typeof parsed === 'object' && Array.isArray(parsed.components)) {
    return parsed.components.map((entry) => ({
      dir: entry && typeof entry === 'object' && typeof entry.dir === 'string' ? entry.dir : '.',
      commands: entry && typeof entry === 'object' && Array.isArray(entry.commands) ? entry.commands : [],
    }));
  }
  return [];
}

/**
 * `--commands` accepts either a path to a JSON file (the documented,
 * subprocess-tested form) or inline JSON text (a generated per-tool hook config
 * may embed the resolved commands directly in its own command string rather
 * than writing a second file — see `src/generators/claude-code.ts`'s
 * `renderHook`). Inline JSON is detected by a leading `[`/`{`; anything else is
 * treated as a file path, preserving the original behavior exactly. Returns the
 * NORMALIZED component list (`normalizeCommandsPayload`), not the raw parsed
 * value — every caller below reads the normalized list only.
 */
function readCommands(commandsArg) {
  if (!commandsArg) {
    return [];
  }
  const trimmed = commandsArg.trim();
  const source = trimmed.startsWith('[') || trimmed.startsWith('{') ? trimmed : undefined;
  try {
    const raw = source ?? fs.readFileSync(commandsArg, 'utf8');
    const parsed = JSON.parse(raw);
    return normalizeCommandsPayload(parsed);
  } catch {
    return [];
  }
}

/** Resolves symlinks so a touched path recorded through one filesystem name
 *  (e.g. a temp directory reached without resolving its symlinked ancestors)
 *  still compares correctly against `process.cwd()`, which the OS always
 *  returns fully resolved. Walks up to the nearest EXISTING ancestor (the path
 *  itself, or any of its parents, may not exist — a vanished touched path, or
 *  one never written to disk at all), canonicalizes that ancestor, and rejoins
 *  the non-existent suffix unchanged; `cwd` itself always exists, so this
 *  always terminates. Used ONLY for component matching — the ORIGINAL absolute
 *  path is still what a command receives (MC-12). */
function canonicalPath(absolutePath) {
  let current = absolutePath;
  const suffix = [];
  for (;;) {
    try {
      const real = fs.realpathSync(current);
      return suffix.length > 0 ? path.join(real, ...suffix) : real;
    } catch {
      const parent = path.dirname(current);
      if (parent === current) {
        return absolutePath;
      }
      suffix.unshift(path.basename(current));
      current = parent;
    }
  }
}

/**
 * (specs/monorepo-mode, MC-9/ADR 0039.) Longest **segment**-prefix match, never
 * a raw string prefix: a component `d` matches `rel` (a path already made
 * relative to `cwd` and POSIX-normalized) iff `d === '.'`, or `rel === d`, or
 * `rel.startsWith(d + '/')`. Among matches, the one with the most path segments
 * wins — so `apps/web` never matches `apps/web-admin/x.ts`. Returns `undefined`
 * for a path outside `cwd` entirely, or matching no declared component.
 */
function componentDirFor(absolutePath, cwd, dirs) {
  // Both sides are canonicalized (symlinks resolved) before comparing: `cwd` is
  // `process.cwd()`, which the OS always returns fully resolved, so an
  // accumulated path reached through a differently-symlinked name (e.g. macOS's
  // /var vs. /private/var) would otherwise spuriously compare as "outside cwd".
  const relRaw = path.relative(canonicalPath(cwd), canonicalPath(absolutePath));
  if (relRaw === '' ? false : relRaw.startsWith('..') || path.isAbsolute(relRaw)) {
    return undefined;
  }
  const rel = relRaw.split(path.sep).join('/');

  let best;
  let bestSegments = -1;
  for (const dir of dirs) {
    let segments;
    if (dir === '.') {
      segments = 0;
    } else if (rel === dir || rel.startsWith(`${dir}/`)) {
      segments = dir.split('/').length;
    } else {
      continue;
    }
    if (segments > bestSegments) {
      bestSegments = segments;
      best = dir;
    }
  }
  return best;
}

/** `'.'`/`''` resolve to `cwd` itself; anything else is joined segment-by-segment
 *  (mirrors `TOUCHED_FILES_DIR.split('/')`'s convention below, rather than
 *  assuming `'/'` is the platform separator). Pure — no filesystem side effect:
 *  a feedback runner must not write directories into the target repository as
 *  a side effect of running a linter. Whether the result actually exists on
 *  disk is `componentDirExists`'s question, not this one. */
function resolveComponentCwd(cwd, componentDir) {
  return componentDir === '.' || componentDir === '' ? cwd : path.join(cwd, ...componentDir.split('/'));
}

/** True iff `componentDir` (resolved against `cwd`) exists on disk and is a
 *  directory. `'.'`/`''` — the install directory itself, the runner's own
 *  `cwd` — is always true. A declared component directory that does not yet
 *  exist (contract.md Error Handling Contract: legal — "a component directory
 *  may legitimately be created after scaffolding") is a genuine runtime
 *  condition, not an error: callers use this to give that component's commands
 *  a visible, non-fatal skip (the same "drop it, but say so" posture MC-11
 *  already takes for an unassigned touched path), rather than letting
 *  `spawnSync`'s `cwd` option fail outright for an unconstrained command, or
 *  silently creating the directory as a side effect of running a linter. */
function componentDirExists(cwd, componentDir) {
  if (componentDir === '.' || componentDir === '') {
    return true;
  }
  try {
    return fs.statSync(resolveComponentCwd(cwd, componentDir)).isDirectory();
  } catch {
    return false;
  }
}

/** The single stderr notice both dispatch paths print for a component whose
 *  declared directory is absent at runtime. One text, one place (`AGENTS.md`
 *  S5), phrased in MC-11's "what was dropped; skipped." notice style, and it
 *  always names the component path so the skip is never silent. */
function componentDirMissingNotice(component) {
  return (
    `harny-feedback: component directory \`${component.dir}\` does not exist; ` +
    `${component.commands.length} command(s) skipped.`
  );
}

function readTurnFile(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch {
    return undefined;
  }
}

/** Dedupes accumulated paths by absolute path, order-insensitive (BG-1: "exactly
 *  M deduped paths", not "in accumulation order"). */
function dedupedTouchedPaths(contents) {
  const lines = contents
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  return Array.from(new Set(lines));
}

function runCommand(command, touchedPaths, cwd) {
  const [binary, ...rest] = command.argv;
  const args = command.pathMode === 'per-file' ? [...rest, ...touchedPaths] : [...rest];
  return spawnSync(binary, args, { cwd, stdio: 'pipe', encoding: 'utf8' });
}

/** True iff `filePath` should reach a command declaring `extensions`.
 *  (A1) Valid entries are non-empty strings. No filter (always true) when
 *  `extensions` is not an array or has no valid entry: absent, `[]`, and
 *  `[null, '']` all mean "no filter". Otherwise a case-sensitive suffix test
 *  against the valid entries only; invalid entries are ignored. */
function matchesExtensions(filePath, extensions) {
  const valid = Array.isArray(extensions) ? extensions.filter((ext) => typeof ext === 'string' && ext.length > 0) : [];
  if (valid.length === 0) {
    return true;
  }
  return valid.some((ext) => filePath.endsWith(ext));
}

/** Keeps only the paths that exist on disk when the runner fires (G1).
 *  Paths are the accumulator's absolute paths. */
function existingPaths(paths) {
  return paths.filter((p) => fs.existsSync(p));
}

/** The argv tail a `per-file` command receives in turn-based `run` mode:
 *  extension gate FIRST, then existence check. The order is fixed: it keeps the
 *  `existsSync` calls to paths the command could actually receive. */
function perFilePathsFor(command, touchedPaths) {
  return existingPaths(touchedPaths.filter((p) => matchesExtensions(p, command.extensions)));
}

/** (A1) `--whole-project`: no turn key, no turn file, every command runs
 *  unconditionally. `per-file` commands receive exactly `.` in place of the
 *  turn's touched paths (contract.md § Data Models "Whole-project invocation
 *  record"). `stop_hook_active` is never read or honored (BG-19) — CI has no
 *  re-entry concept, so a finding always exits 2.
 *
 *  (specs/monorepo-mode, MC-19.) `components` is the NORMALIZED `{dir, commands}`
 *  list (`readCommands`'s return shape). Every command of every component runs
 *  once, from that component's own directory, with the `.` sentinel; the
 *  `ran`/`total`/`skipped` counts are summed across every component so the
 *  summary line's text is unchanged for the legacy one-`.`-component case
 *  (MC-5). The component label is added to finding/skip lines only when more
 *  than one component is present, so today's text stays byte-identical.
 *
 *  A component whose declared directory is absent on disk is skipped wholesale
 *  with one stderr notice naming it (`componentDirMissingNotice`); its commands
 *  count as `skipped` in the summary and are never spawned with a `cwd` that
 *  does not exist. */
function runWholeProject(components, cwd) {
  let anyBlockingFinding = false;
  let ranCount = 0;
  let skippedCount = 0;
  let totalCount = 0;
  const multiComponent = components.length > 1;

  for (const component of components) {
    const componentCwd = resolveComponentCwd(cwd, component.dir);
    const label = multiComponent ? ` (${component.dir})` : '';

    if (!componentDirExists(cwd, component.dir)) {
      // A declared component directory that does not exist yet is a legal runtime
      // condition, never a failure: drop its commands, but say so — the same
      // "drop it, but say so" posture MC-11 takes for an unassigned touched path.
      // The commands still count toward `total`/`skipped` so the summary line
      // below stays truthful about what was declared.
      totalCount += component.commands.length;
      skippedCount += component.commands.length;
      console.error(componentDirMissingNotice(component));
      continue;
    }

    for (const command of component.commands) {
      totalCount += 1;
      if (!requirementMet(command.requires, componentCwd)) {
        skippedCount += 1;
        console.error(`skipped \`${command.id}\`${label}: requirement not met (tool not installed in this repo)`);
        continue;
      }

      ranCount += 1;
      const result = runCommand(command, ['.'], componentCwd);
      if (result.status !== 0) {
        anyBlockingFinding = true;
        console.log(`finding from \`${command.id}\`${label} (exit ${result.status}):`);
        if (result.stdout && result.stdout.trim()) {
          console.log(result.stdout.trim());
        }
        if (result.stderr && result.stderr.trim()) {
          console.error(result.stderr.trim());
        }
      }
    }
  }

  // (A1) The trailing summary line every whole-project run prints, unlike normal
  // `run` mode's silence on a clean turn (BG-4) — this is what lets `harny-audit`
  // (BG-17's A1 clause) tell a genuinely green run apart from one that skipped
  // every command.
  console.log(`harny-feedback: ${ranCount} of ${totalCount} command(s) ran, ${skippedCount} skipped.`);

  // BG-19: `stop_hook_active` is never read or honored here — a finding always
  // exits 2, unconditionally.
  process.exit(anyBlockingFinding ? 2 : 0);
}

/**
 * The turn path's dispatch, shared by `run` and `run --staged`: assigns each touched
 * path to its component, then runs that component's commands over its share
 * (MC-11, MC-17, PH-5). `skipWholeProject` drops whole-project commands entirely
 * (commit-checks CC-2). Returns whether any command reported a finding.
 */
function dispatchTouchedPaths(components, touchedPaths, cwd, { skipWholeProject = false } = {}) {
  const multiComponent = components.length > 1;
  const dirs = components.map((component) => component.dir);

  const assignedByDir = new Map(dirs.map((dir) => [dir, []]));
  let unassignedCount = 0;
  for (const touchedPath of touchedPaths) {
    const dir = componentDirFor(touchedPath, cwd, dirs);
    if (dir === undefined) {
      unassignedCount += 1;
      continue;
    }
    assignedByDir.get(dir).push(touchedPath);
  }

  let anyBlockingFinding = false;

  for (const component of components) {
    const assignedPaths = assignedByDir.get(component.dir) ?? [];
    if (assignedPaths.length === 0) {
      // MC-17: a component with no assigned touched path runs nothing at all —
      // not its per-file commands, and not its whole-project commands.
      continue;
    }

    const componentCwd = resolveComponentCwd(cwd, component.dir);
    const label = multiComponent ? ` (${component.dir})` : '';

    if (!componentDirExists(cwd, component.dir)) {
      // Same posture as `runWholeProject`: a component directory that does not
      // exist yet is skipped visibly and non-fatally, never spawned into.
      console.error(componentDirMissingNotice(component));
      continue;
    }

    for (const command of component.commands) {
      if (!requirementMet(command.requires, componentCwd)) {
        console.error(`skipped \`${command.id}\`${label}: requirement not met (tool not installed in this repo)`);
        continue;
      }

      if (skipWholeProject && command.pathMode !== 'per-file') {
        continue;
      }

      let paths = assignedPaths;
      if (command.pathMode === 'per-file') {
        paths = perFilePathsFor(command, assignedPaths);
        if (paths.length === 0) {
          // PH-5: nothing this command should check survived the filters. Never run
          // it with zero path args (that would lint the whole repo); no output.
          continue;
        }
      }

      const result = runCommand(command, paths, componentCwd);
      if (result.status !== 0) {
        anyBlockingFinding = true;
        console.log(`finding from \`${command.id}\`${label} (exit ${result.status}):`);
        if (result.stdout && result.stdout.trim()) {
          console.log(result.stdout.trim());
        }
        if (result.stderr && result.stderr.trim()) {
          console.error(result.stderr.trim());
        }
      }
    }
  }

  // MC-11: a path matching no declared component is dropped, never reassigned;
  // exactly one notice names how many. Never printed when every touched path
  // was assigned (including today's single `.` catch-all component, MC-5), and
  // never printed when no components were declared at all (today's unchanged
  // "no --commands" no-op posture).
  if (components.length > 0 && unassignedCount > 0) {
    console.error(`harny-feedback: ${unassignedCount} touched path(s) matched no declared component; skipped.`);
  }

  return anyBlockingFinding;
}

/**
 * `run --staged` (commit-checks CC-2): the same dispatch over the files staged for
 * the next commit — Added, Copied, Modified and Renamed, never deleted — with
 * whole-project commands left to CI. Reads no stdin and no turn state. Exits 2 when
 * any command reports a finding, so a git `pre-commit` hook calling it blocks.
 */
function runStaged(components, cwd) {
  let top;
  let names;
  try {
    top = execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd, stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
    names = execFileSync('git', ['diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'], {
      cwd: top,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).toString();
  } catch {
    process.exit(0);
  }
  const touchedPaths = [...new Set(names.split('\0').filter(Boolean).map((name) => path.join(top, name)))];
  if (touchedPaths.length === 0) {
    process.exit(0);
  }
  process.exit(dispatchTouchedPaths(components, touchedPaths, cwd, { skipWholeProject: true }) ? 2 : 0);
}

/**
 * (specs/monorepo-mode, MC-9/MC-11/MC-12/MC-17/MC-18.) Partitions the turn's
 * deduped, absolute touched paths across `components` (payload order) by
 * longest-segment-prefix match, then iterates components in that same order:
 * a component with NO assigned path runs nothing at all — not its per-file
 * commands, and not its whole-project commands (MC-17). A surviving component's
 * commands run with `cwd` = that component's own directory (MC-12); per-file
 * commands receive their assigned, extension-filtered, still-existing paths,
 * `whole-project` commands receive none, exactly as today's single-component
 * loop did. A touched path matching no declared component is dropped and
 * counted; when that count is nonzero, exactly one stderr notice names it
 * (MC-11) — for today's single `.` component this count is always 0, so the
 * notice is never printed (MC-5). The component label is added to finding/skip
 * lines only when more than one component is present. A surviving component whose
 * declared directory is absent on disk is itself skipped, with one stderr notice
 * naming it (`componentDirMissingNotice`) — visible, non-fatal, never spawned into.
 */
function runRunMode(cwd) {
  const { commandsPath, wholeProject, keepTurn, staged } = parseRunArgs(process.argv.slice(3));
  const components = readCommands(commandsPath);

  if (wholeProject) {
    runWholeProject(components, cwd);
    return;
  }

  if (staged) {
    runStaged(components, cwd);
    return;
  }

  const payload = readStdinJson();
  const turnKey = resolveTurnKey(payload);
  const stopHookActive = Boolean(payload.stop_hook_active);

  if (!turnKey) {
    process.exit(0);
  }

  const file = turnFilePath(cwd, turnKey);
  const contents = readTurnFile(file);
  if (contents === undefined) {
    // BG-4: no turn file means the turn touched no files. No-op, no output.
    process.exit(0);
  }

  const touchedPaths = dedupedTouchedPaths(contents);
  const anyBlockingFinding = dispatchTouchedPaths(components, touchedPaths, cwd);

  // Delete the turn file so a turn key reused across turns cannot leak this
  // turn's paths into the next one, regardless of outcome above — unless
  // `--keep-turn` asked for it to survive (SF-3/SF-4), in which case the next
  // run without the flag deletes it exactly as this one would have.
  if (!keepTurn) {
    fs.rmSync(file, { force: true });
  }

  // BG-5: re-entry never drives a tool's runaway guard — suppress the blocking
  // response on re-entry even when a mapped command failed.
  if (anyBlockingFinding && !stopHookActive) {
    process.exit(2);
  }
  process.exit(0);
}

function main() {
  const mode = process.argv[2];
  const cwd = process.cwd();

  if (mode === 'accumulate') {
    runAccumulate(cwd);
  } else if (mode === 'run') {
    runRunMode(cwd);
  } else {
    console.error(`run-feedback.mjs: unknown mode "${mode ?? ''}" (expected "accumulate" or "run")`);
    process.exit(1);
  }
}

main();
