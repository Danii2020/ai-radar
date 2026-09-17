/**
 * Shared runtime probe evaluator (see `templates/doctor/README.md` and
 * `templates/hooks/README.md`). Copied byte-for-byte into every scaffolded
 * project at `.sdd/shared/probes.mjs` (contract.md BG-11, BG-20) and imported
 * by both generated entry-point scripts — `.sdd/feedback/run-feedback.mjs` and
 * `.sdd/doctor/run-doctor.mjs` — via the identical relative specifier
 * `../shared/probes.mjs`, which resolves against each importing module's own
 * URL, not `cwd` (correct in `templates/` and in the generated `.sdd/` tree
 * alike).
 *
 * This is the single, exactly-once implementation of every `ToolProbe` check
 * (readiness-doctor BG-19): no other file under `templates/` may re-implement
 * `scriptExists`, `binaryExists`, `anyFileExists`, or `probeSatisfied`.
 *
 * Every signature here is lifted verbatim from the original, single-file
 * `run-feedback.mjs`; no behavior change, no parameter added or reordered —
 * this module IS that code, relocated.
 */
import fs from 'node:fs';
import path from 'node:path';

export function scriptExists(scriptName, cwd) {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(cwd, 'package.json'), 'utf8'));
    return Boolean(pkg.scripts && Object.prototype.hasOwnProperty.call(pkg.scripts, scriptName));
  } catch {
    return false;
  }
}

export function binaryExists(binary) {
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  const exts = process.platform === 'win32' ? (process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';') : [''];

  for (const dir of dirs) {
    for (const ext of exts) {
      try {
        fs.accessSync(path.join(dir, `${binary}${ext}`), fs.constants.X_OK);
        return true;
      } catch {
        // Keep looking in the next PATH entry.
      }
    }
  }
  return false;
}

export function anyFileExists(files, cwd) {
  return files.some((file) => fs.existsSync(path.join(cwd, file)));
}

/** A command whose `requires` probe is false is SKIPPED, never a failure (BG-9). An
 *  empty/absent `requires` always resolves true. */
export function probeSatisfied(requires, cwd) {
  if (!requires) {
    return true;
  }
  if (requires.script && !scriptExists(requires.script, cwd)) {
    return false;
  }
  if (requires.binary && !binaryExists(requires.binary)) {
    return false;
  }
  if (requires.anyFile && !anyFileExists(requires.anyFile, cwd)) {
    return false;
  }
  return true;
}
