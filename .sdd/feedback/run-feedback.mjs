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
 *   executes the survivors exactly once (`per-file` commands receive the deduped
 *   paths appended to `argv`; `whole-project` commands do not), deletes the turn
 *   file so a reused turn key cannot leak into the next turn, and exits.
 * - `run --whole-project` (A1, CI-only) is the same `run` mode with one boolean
 *   flag set, never a third mode. It bypasses turn state entirely: no STDIN turn
 *   key is read or required, `.sdd/feedback/.turns/` is never read, written, or
 *   deleted, and every command runs unconditionally exactly once. `per-file`
 *   commands receive exactly one argument, `.` (the repo root is the whole
 *   project), in place of the turn's touched paths. The `requires` probe path is
 *   identical to normal `run` mode (BG-9). `stop_hook_active` is never read or
 *   honored under this flag — CI has no re-entry/loop-guard concept, so a finding
 *   always exits 2 (BG-19).
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
import { spawnSync } from 'node:child_process';
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
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--commands') {
      commandsPath = argv[i + 1];
      i += 1;
    } else if (argv[i] === '--whole-project') {
      wholeProject = true;
    }
  }
  return { commandsPath, wholeProject };
}

/**
 * `--commands` accepts either a path to a JSON file (the documented,
 * subprocess-tested form) or inline JSON text (a generated per-tool hook config
 * may embed the resolved commands directly in its own command string rather
 * than writing a second file — see `src/generators/claude-code.ts`'s
 * `renderHook`). Inline JSON is detected by a leading `[`/`{`; anything else is
 * treated as a file path, preserving the original behavior exactly.
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
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
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

/** A touched path accumulated earlier in the turn may no longer exist by the
 *  time `run` executes — e.g. a `git mv`/`rm` run through Bash after the file
 *  was Edited/Written, which the accumulator (Edit|Write-hooked) never
 *  observes. Passing a since-vanished path to a per-file command makes the
 *  mapped tool fail to open it (e.g. ruff's E902), not a real finding. */
function existingPaths(paths) {
  return paths.filter((p) => {
    try {
      fs.accessSync(p);
      return true;
    } catch {
      return false;
    }
  });
}

/** A `per-file` command only knows how to check its own language — running
 *  `ruff`/`mypy` against a touched `.mjs`/`.yml`/`.json` file makes them try
 *  to parse it as Python and report bogus syntax "findings". `command.
 *  extensions`, when present, restricts touched paths to that command's own
 *  file types before anything else runs. `.` (the `--whole-project` sentinel,
 *  never a real touched file) always passes through unfiltered. Absent
 *  `extensions` keeps today's behavior (no filtering) for any command that
 *  doesn't declare one. */
function matchesExtensions(p, extensions) {
  if (!extensions || extensions.length === 0 || p === '.') {
    return true;
  }
  const ext = path.extname(p).toLowerCase();
  return extensions.some((allowed) => allowed.toLowerCase() === ext);
}

function runCommand(command, touchedPaths, cwd) {
  const [binary, ...rest] = command.argv;
  if (command.pathMode === 'per-file') {
    const existing = existingPaths(touchedPaths.filter((p) => matchesExtensions(p, command.extensions)));
    // Every touched path vanished mid-turn (BG-4-style no-op): most `per-file`
    // tools (e.g. `ruff check`) default to `.` — the whole project — when
    // given zero file arguments, which would silently widen this command far
    // past its per-file scope. Skip the subprocess entirely instead.
    if (existing.length === 0) {
      return { status: 0, stdout: '', stderr: '' };
    }
    return spawnSync(binary, [...rest, ...existing], { cwd, stdio: 'pipe', encoding: 'utf8' });
  }
  const args = [...rest];
  return spawnSync(binary, args, { cwd, stdio: 'pipe', encoding: 'utf8' });
}

/** (A1) `--whole-project`: no turn key, no turn file, every command runs
 *  unconditionally. `per-file` commands receive exactly `.` in place of the
 *  turn's touched paths (contract.md § Data Models "Whole-project invocation
 *  record"). `stop_hook_active` is never read or honored (BG-19) — CI has no
 *  re-entry concept, so a finding always exits 2. */
function runWholeProject(commands, cwd) {
  let anyBlockingFinding = false;
  let ranCount = 0;
  let skippedCount = 0;

  for (const command of commands) {
    if (!requirementMet(command.requires, cwd)) {
      skippedCount += 1;
      console.error(`skipped \`${command.id}\`: requirement not met (tool not installed in this repo)`);
      continue;
    }

    ranCount += 1;
    const result = runCommand(command, ['.'], cwd);
    if (result.status !== 0) {
      anyBlockingFinding = true;
      console.log(`finding from \`${command.id}\` (exit ${result.status}):`);
      if (result.stdout && result.stdout.trim()) {
        console.log(result.stdout.trim());
      }
      if (result.stderr && result.stderr.trim()) {
        console.error(result.stderr.trim());
      }
    }
  }

  // (A1) The trailing summary line every whole-project run prints, unlike normal
  // `run` mode's silence on a clean turn (BG-4) — this is what lets `harny-audit`
  // (BG-17's A1 clause) tell a genuinely green run apart from one that skipped
  // every command.
  console.log(`harny-feedback: ${ranCount} of ${commands.length} command(s) ran, ${skippedCount} skipped.`);

  // BG-19: `stop_hook_active` is never read or honored here — a finding always
  // exits 2, unconditionally.
  process.exit(anyBlockingFinding ? 2 : 0);
}

function runRunMode(cwd) {
  const { commandsPath, wholeProject } = parseRunArgs(process.argv.slice(3));
  const commands = readCommands(commandsPath);

  if (wholeProject) {
    runWholeProject(commands, cwd);
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
  let anyBlockingFinding = false;

  for (const command of commands) {
    if (!requirementMet(command.requires, cwd)) {
      console.error(`skipped \`${command.id}\`: requirement not met (tool not installed in this repo)`);
      continue;
    }

    const result = runCommand(command, touchedPaths, cwd);
    if (result.status !== 0) {
      anyBlockingFinding = true;
      console.log(`finding from \`${command.id}\` (exit ${result.status}):`);
      if (result.stdout && result.stdout.trim()) {
        console.log(result.stdout.trim());
      }
      if (result.stderr && result.stderr.trim()) {
        console.error(result.stderr.trim());
      }
    }
  }

  // Delete the turn file so a turn key reused across turns cannot leak this
  // turn's paths into the next one, regardless of outcome above.
  fs.rmSync(file, { force: true });

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
