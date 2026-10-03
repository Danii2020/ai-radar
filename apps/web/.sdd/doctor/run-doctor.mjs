#!/usr/bin/env node
/**
 * The shared, tool-neutral readiness runner (see `templates/doctor/README.md` for
 * the canonical behavior this script implements). Copied byte-for-byte into every
 * scaffolded project at `.sdd/doctor/run-doctor.mjs` (contract.md BG-11) — its bytes
 * never vary by stack or by tool. Every command string, stack name, spec-directory
 * name, schema-file name, and `Shipped:`/verdict literal it evaluates arrives via
 * `--checks`; this script hard-codes none of them (BG-3).
 *
 * This is one of two generated entry-point scripts (the other is
 * `.sdd/feedback/run-feedback.mjs`, the per-turn/CI feedback runner); both import
 * their probe evaluator from a third generated file, `.sdd/shared/probes.mjs`
 * (`templates/shared/probes.mjs`), rather than each carrying its own copy. This
 * script contains no probe logic of its own (BG-19).
 *
 * Invocation: `node run-doctor.mjs [--checks <path-or-inline-json>] [--only <family>]`,
 * run with `cwd` set to the repo being checked. `--checks` defaults to
 * `.sdd/doctor/checks.json`, relative to `cwd`, when omitted. `--checks` accepts
 * either a path to a JSON file or inline JSON text detected by a leading `{` — the
 * identical dual-form convention `run-feedback.mjs`'s `--commands` flag already
 * implements.
 *
 * `--only <family>` (added by documentation-role-completion, contract.md RC-1-RC-4)
 * scopes a run to exactly one of the five families named below (`FAMILY_TOKENS`),
 * instead of all five. It is additive and default-transparent: when absent, every
 * family runs, byte-for-byte identical to this script's pre-`--only` behavior. The
 * selector this feature exists for is `--only spec-state`, cheap enough to run at
 * the end of every documentation turn because it spawns no child process — in
 * particular, none from family 5 (tests). A value outside `FAMILY_TOKENS`, or
 * `--only` with no following value, is a usage error (exit 1) naming the offending
 * value/flag — never a silently-empty run that exits 0 and falsely reports
 * readiness.
 *
 * Five check families run in this fixed order, every time, so two runs of the same
 * repo state produce identical output (BG-1, amended by ai-sdlc-readiness from four
 * families to five, and doctor-security-checks to six — see `templates/doctor/README.md`):
 *
 * 1. **environment** — the running Node version is reported (always `ok`); when the
 *    supplied `commands` list is empty (an unresolved/blank stack, BG-8), a single
 *    notice is reported (`skip`, never a failure).
 * 2. **harness manifest** — one line per `require` entry, evaluated by the shared
 *    `evaluateEntry` (see below).
 * 3. **repo readiness** — one line per `repoReadiness` entry, evaluated by the same
 *    `evaluateEntry` as family 2 — a different question (is the target repo itself
 *    legible to an agent) from family 2 (is harny's own harness installed), so it
 *    gets its own labelled section rather than more entries in family 2.
 * 4. **security** — one line per `security` entry, evaluated by the same
 *    `evaluateEntry`, every entry `recommended`. An entry may carry an `assert` in
 *    place of its `anyOf` presence check: `probe` (the shared ToolProbe evaluator),
 *    `gitIgnored`, `gitConfig` (both skip outside a git work tree) or `fileContains`.
 * 5. **spec state** — every `specs/<feature>/` directory (excluding the configured
 *    `reservedDirs`) is checked for the configured `schemaFiles`, and for the
 *    shipped-but-unarchived condition (BOTH a `shippedMarker` header line in
 *    `intent.md` AND an `approvedVerdicts` match in `audit.md`) — reported by feature
 *    name, one line per finding; a feature with no finding contributes no line. The
 *    marker is matched at the line start after stripping leading Markdown emphasis,
 *    list-item, blockquote and heading punctuation (`STAMP_LEADING_MARKUP`), so the
 *    bolded `**Shipped: <date>**` stamp the documentation role writes is seen as
 *    readily as a bare one — but prose that merely names the marker is not.
 * 6. **tests** — one line per `commands` entry: its `requires` probe is evaluated
 *    first (a false probe is `skip`, never a failure); when it passes, the command is
 *    spawned once and its exit status becomes `ok`/`fail`.
 *
 * `evaluateEntry` is the one presence-entry evaluator shared by families 2 and 3
 * (AR-12): its own `requires` gate is evaluated first (a false gate is `skip`, never
 * a failure — BG-9); when the gate passes (or is absent), the entry's `anyOf` paths
 * are checked for existence (`ok` if any exists); when none exists, the miss splits
 * on the entry's own declared `tier` — `'recommended'` emits `warn` naming the
 * entry's `remediation`, anything else (absent or unrecognised) emits `fail` naming
 * it (AR-5, the conservative default a repo's pre-feature `checks.json` and every
 * family-2 entry rely on).
 *
 * A failing check never aborts the run (BG-2): every check in every family is always
 * evaluated, so one report shows everything wrong at once. A trailing summary line
 * names the ok/skipped/warned/failed counts.
 *
 * Exit codes: `0` when every check is `ok`, `skip`, or `warn` (ready — a warned run
 * is still a ready run); `2` when at least one check is `fail` (not ready); `1` when
 * `--checks` is missing, unreadable, or not valid JSON, or an unknown flag is given
 * (the runner itself could not run) — never confused with a red-but-correctly-run
 * result.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { probeSatisfied as requirementMet } from '../shared/probes.mjs';

/** The shared component-discovery module (component-level-docs CL-1), imported
 *  dynamically so an install that predates it still runs every other family (CL-4). */
const componentsModule = await import(new URL('../shared/components.mjs', import.meta.url).href).catch(() => undefined);

/** The runner's own default location for its checks data, relative to `cwd`. Not a
 *  value this script receives via `--checks` — a hard-coded convention of the
 *  runner's own invocation, the same way `run-feedback.mjs` hard-codes its own
 *  `TOUCHED_FILES_DIR`. */
const DEFAULT_CHECKS_PATH = path.join('.sdd', 'doctor', 'checks.json');

/** Markdown emphasis, list-item, blockquote and heading punctuation a stamp line may
 *  carry ahead of the marker itself. The documentation role writes the stamp bolded
 *  (`**Shipped: <date>**`), so matching the bare marker at the exact line start missed
 *  every stamp it produced — the shipped-but-unarchived check could not see the very
 *  artifact it exists to detect. Stripped only from the START of an already-trimmed
 *  line, never searched for anywhere in it: a substring match would mistake prose that
 *  merely names the marker (e.g. an indented "in-place `Shipped: <date>` header"
 *  sentence) for a real stamp. `shippedMarker` itself stays the literal configured in
 *  `checks.json`, so an older checks file keeps working unchanged. */
const STAMP_LEADING_MARKUP = /^[*_~>#\s-]+/;

/** The six check families, in the fixed order `main` runs them below (the fourth,
 *  security, added by doctor-security-checks). Structural —
 *  which code paths exist in this script — not data that arrives via `--checks`, so
 *  it follows `DEFAULT_CHECKS_PATH`'s precedent of being a hard-coded convention of
 *  the runner's own invocation (contract.md § Interfaces item 1). `--only`'s value
 *  must be a member of this array. */
const FAMILY_TOKENS = ['environment', 'harness', 'repo-readiness', 'security', 'spec-state', 'tests'];

function fail(message) {
  console.error(`run-doctor.mjs: ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  let checksArg;
  let onlyArg;
  let i = 0;
  while (i < argv.length) {
    const token = argv[i];
    if (token === '--checks') {
      checksArg = argv[i + 1];
      i += 2;
    } else if (token === '--only') {
      const value = argv[i + 1];
      if (value === undefined) {
        fail(`--only requires a value (one of: ${FAMILY_TOKENS.join(', ')})`);
      }
      if (!FAMILY_TOKENS.includes(value)) {
        fail(`--only "${value}" is not a recognized family (expected one of: ${FAMILY_TOKENS.join(', ')})`);
      }
      onlyArg = value;
      i += 2;
    } else {
      fail(`unknown flag "${token}" (expected --checks <path-or-inline-json> or --only <family>)`);
    }
  }
  return { checksArg, onlyArg };
}

/** Dual-form `--checks` resolution, in spirit identical to `run-feedback.mjs`'s
 *  `readCommands`: a leading `{` is treated as inline JSON text; anything else is a
 *  file path. Unlike `readCommands`, a bad value here is a hard failure (exit 1),
 *  never a silent empty result — a readiness run must never claim readiness having
 *  read nothing. */
function readChecks(checksArg) {
  const target = checksArg ?? DEFAULT_CHECKS_PATH;
  const trimmed = target.trim();
  const isInline = trimmed.startsWith('{');

  let raw;
  if (isInline) {
    raw = target;
  } else {
    try {
      raw = fs.readFileSync(target, 'utf8');
    } catch {
      fail(`could not read --checks file "${target}"`);
    }
  }

  try {
    return JSON.parse(raw);
  } catch {
    fail(`--checks did not contain valid JSON (from "${isInline ? 'inline JSON' : target}")`);
  }
}

function safeRead(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch {
    return undefined;
  }
}

function anyPathExists(paths, cwd) {
  return (paths ?? []).some((p) => fs.existsSync(path.join(cwd, p)));
}

/** Runs git from `cwd`; `{ status, stdout }`, with status `null` when git is absent. */
function runGit(args, cwd) {
  const result = spawnSync('git', args, { cwd, stdio: ['ignore', 'pipe', 'ignore'] });
  return { status: result.error ? null : result.status, stdout: result.stdout ? result.stdout.toString() : '' };
}

function insideGitWorkTree(cwd) {
  const { status, stdout } = runGit(['rev-parse', '--is-inside-work-tree'], cwd);
  return status === 0 && stdout.trim() === 'true';
}

/**
 * An entry's `assert` (doctor-security-checks DS-3), when it has one: `'ok'`,
 * `'miss'`, or `{ skip: reason }`. Git-backed kinds skip outside a git work tree
 * (DS-4). `git check-ignore` answers "any of these is ignored", so each path gets
 * its own call. An unknown kind is a miss that names it, never a crash.
 */
function evaluateAssertion(assert, cwd) {
  if (assert.kind === 'probe') {
    return requirementMet(assert.probe, cwd) ? 'ok' : 'miss';
  }
  if (assert.kind === 'fileContains') {
    const contents = safeRead(path.join(cwd, assert.path));
    return contents !== undefined && contents.includes(assert.text) ? 'ok' : 'miss';
  }
  if (assert.kind === 'gitIgnored' || assert.kind === 'gitConfig') {
    if (!insideGitWorkTree(cwd)) {
      return { skip: 'not a git repository' };
    }
    if (assert.kind === 'gitIgnored') {
      return (assert.paths ?? []).every((p) => runGit(['check-ignore', '-q', '--', p], cwd).status === 0) ? 'ok' : 'miss';
    }
    const { status, stdout } = runGit(['config', '--get', assert.key], cwd);
    return status === 0 && stdout.trim() === assert.equals ? 'ok' : 'miss';
  }
  return { unknown: assert.kind };
}

function main() {
  const { checksArg, onlyArg } = parseArgs(process.argv.slice(2));
  const checks = readChecks(checksArg);
  const cwd = process.cwd();

  /** `onlyArg` undefined (the flag absent) means "run all five families" — the
   *  default-transparent, pre-`--only` behavior (RC-1). `parseArgs` already
   *  rejected any value outside `FAMILY_TOKENS`, so a defined `onlyArg` here is
   *  always a valid family token. */
  function selected(token) {
    return onlyArg === undefined || onlyArg === token;
  }

  const lines = [];
  let okCount = 0;
  let skipCount = 0;
  let warnCount = 0;
  let failCount = 0;

  function emit(id, outcome, detail) {
    lines.push(`${outcome.toUpperCase()} ${id}${detail ? ` - ${detail}` : ''}`);
    if (outcome === 'ok') okCount += 1;
    else if (outcome === 'skip') skipCount += 1;
    else if (outcome === 'warn') warnCount += 1;
    else failCount += 1;
  }

  /** One presence-entry evaluator, shared by family 2 (harness manifest) and family 3
   *  (repo readiness) — the same single-implementation discipline `requirementMet`
   *  follows (RD-3). The miss branch splits on the entry's own declared `tier`: an
   *  absent or unrecognised `tier` is must-have (`fail`), preserving family 2's
   *  pre-feature behavior exactly (AR-5). */
  function evaluateEntry(entry, cwdForEntry) {
    if (!requirementMet(entry.requires, cwdForEntry)) {
      emit(entry.id, 'skip', 'requirement not met, skipping');
      return;
    }
    const outcome = entry.assert ? evaluateAssertion(entry.assert, cwdForEntry) : undefined;
    if (outcome && outcome.skip) {
      emit(entry.id, 'skip', outcome.skip);
    } else if (outcome && outcome.unknown !== undefined) {
      emit(entry.id, 'warn', `unknown assertion kind "${outcome.unknown}"; re-run npx harny init`);
    } else if (outcome ? outcome === 'ok' : anyPathExists(entry.anyOf, cwdForEntry)) {
      emit(entry.id, 'ok');
    } else if (entry.tier === 'recommended') {
      emit(entry.id, 'warn', entry.remediation);
    } else {
      emit(entry.id, 'fail', entry.remediation);
    }
  }

  // 1. environment.
  const commands = checks.commands ?? [];
  if (selected('environment')) {
    emit('node-version', 'ok', `running on Node ${process.version}`);
    if (commands.length === 0) {
      emit(
        'readiness-commands',
        'skip',
        'no test-suite command configured for this stack; the test family reports no findings',
      );
    }
  }

  // 2. harness manifest.
  if (selected('harness')) {
    for (const entry of checks.require ?? []) {
      evaluateEntry(entry, cwd);
    }
  }

  // 3. repo readiness. `checks.repoReadiness`/`checks.repoReadinessLabel` are the
  // only new reads (AR-11); both tolerate absence so a pre-feature checks.json
  // contributes no family-3 lines rather than erroring (AR-5, SC9).
  if (selected('repo-readiness')) {
    if (checks.repoReadinessLabel) {
      lines.push(`-- ${checks.repoReadinessLabel} --`);
    }
    for (const entry of checks.repoReadiness ?? []) {
      evaluateEntry(entry, cwd);
    }
    // (component-level-docs, CL-3.) One doc entry per discovered component, then one
    // entry per bridged tool once the doc exists — all recommended.
    const componentDocs = checks.componentDocs;
    if (componentDocs && componentsModule) {
      const { discoverComponents, fillComponentTemplate } = componentsModule;
      for (const dir of discoverComponents(cwd, componentDocs.discovery ?? {})) {
        const docPath = `${dir}/${componentDocs.docName}`;
        if (!fs.existsSync(path.join(cwd, docPath))) {
          emit(
            `repo-readiness:component-doc:${dir}`,
            'warn',
            `add ${docPath} describing this component's purpose, key files, local commands and conventions`,
          );
          continue;
        }
        emit(`repo-readiness:component-doc:${dir}`, 'ok');
        for (const bridge of componentDocs.bridges ?? []) {
          const bridgePath = fillComponentTemplate(bridge.path, dir);
          const marker = fillComponentTemplate(bridge.marker, dir);
          const contents = safeRead(path.join(cwd, bridgePath));
          if (contents !== undefined && contents.includes(marker)) {
            emit(`repo-readiness:component-bridge:${bridge.tool}:${dir}`, 'ok');
          } else {
            const fix =
              contents === undefined
                ? `create ${bridgePath} (it must include "${marker}") containing exactly: ${JSON.stringify(fillComponentTemplate(bridge.contents, dir))}`
                : `add "${marker}" to ${bridgePath}`;
            emit(`repo-readiness:component-bridge:${bridge.tool}:${dir}`, 'warn', `${fix} (or run npx harny init)`);
          }
        }
      }
    }
  }

  // 4. security (doctor-security-checks DS-1). Same tolerance as family 3: a checks
  // file without `security`/`securityLabel` contributes no lines (DS-8).
  if (selected('security')) {
    if (checks.securityLabel) {
      lines.push(`-- ${checks.securityLabel} --`);
    }
    for (const entry of checks.security ?? []) {
      evaluateEntry(entry, cwd);
    }
  }

  // 5. spec state.
  if (selected('spec-state')) {
    const specs = checks.specs ?? {};
    const specsDir = specs.dir;
    const reservedDirs = new Set(specs.reservedDirs ?? []);
    const schemaFiles = specs.schemaFiles ?? [];
    const legacySchemaFiles = specs.legacySchemaFiles;
    const shippedMarker = specs.shippedMarker;
    const approvedVerdicts = specs.approvedVerdicts ?? [];

    let featureNames = [];
    try {
      featureNames = fs
        .readdirSync(path.join(cwd, specsDir), { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && !reservedDirs.has(entry.name))
        .map((entry) => entry.name);
    } catch {
      featureNames = [];
    }

    for (const name of featureNames) {
      const featureDir = path.join(cwd, specsDir, name);
      let entries;
      try {
        entries = fs.readdirSync(featureDir);
      } catch (err) {
        emit(`spec-state:${name}`, 'fail', `could not read ${specsDir}/${name}: ${err.message}`);
        continue;
      }

      // A dir holding contract.md or roadmap.md is legacy shape (even beside an
      // execution-plan.md); a checks.json without legacySchemaFiles judges every dir
      // against schemaFiles, as before.
      const isLegacy =
        Array.isArray(legacySchemaFiles) &&
        (entries.includes('contract.md') || entries.includes('roadmap.md'));
      const required = isLegacy ? legacySchemaFiles : schemaFiles;
      const missing = required.filter((name2) => !entries.includes(`${name2}.md`));
      if (missing.length > 0) {
        emit(
          `spec-state:${name}`,
          'fail',
          `${specsDir}/${name} is missing ${missing.map((m) => `${m}.md`).join(', ')}`,
        );
        continue;
      }

      const intentContents = safeRead(path.join(featureDir, 'intent.md'));
      const auditContents = safeRead(path.join(featureDir, 'audit.md'));
      const shipped = Boolean(
        intentContents &&
          intentContents
            .split('\n')
            .some((line) => line.trim().replace(STAMP_LEADING_MARKUP, '').startsWith(shippedMarker)),
      );
      const approved = Boolean(
        auditContents && approvedVerdicts.some((verdict) => auditContents.includes(verdict)),
      );
      if (shipped && approved) {
        emit(
          `spec-state:${name}`,
          'fail',
          `${specsDir}/${name} is shipped and approved but was never archived (run harny-sync archive mode)`,
        );
      }
    }
  }

  // 6. tests. (specs/monorepo-mode, MC-21.) Each command's working directory AND
  // its `requires` probe are resolved from `command.dir ?? '.'`, relative to the
  // runner's own `cwd` — `path.resolve(cwd, '.')` is `path.resolve(cwd)`, so a
  // `checks.json` generated before this feature (no `dir` anywhere) produces
  // byte-identical behavior.
  if (selected('tests')) {
    for (const command of commands) {
      const commandCwd = path.resolve(cwd, command.dir ?? '.');
      if (!requirementMet(command.requires, commandCwd)) {
        emit(command.id, 'skip', 'requirement not met, skipping');
        continue;
      }
      const [binary, ...rest] = command.argv;
      const result = spawnSync(binary, rest, { cwd: commandCwd, stdio: 'pipe', encoding: 'utf8' });
      if (result.status === 0) {
        emit(command.id, 'ok');
      } else {
        const output = [result.stdout, result.stderr].filter((part) => part && part.trim()).join('\n').trim();
        emit(command.id, 'fail', output || `exited with status ${result.status}`);
      }
    }
  }

  for (const line of lines) {
    console.log(line);
  }
  console.log(`summary: ${okCount} ok, ${skipCount} skipped, ${warnCount} warned, ${failCount} failed`);

  process.exit(failCount > 0 ? 2 : 0);
}

main();
