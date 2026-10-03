#!/usr/bin/env node
/**
 * harny commit-checks — the tool-neutral runner behind the `pre-commit` and `pre-push`
 * git hook shims beside it (specs/commit-checks). Copied byte-for-byte into every
 * install at `.sdd/git-hooks/run-git-hook.mjs`. Node builtins only.
 *
 * Usage (from a shim): node run-git-hook.mjs <pre-commit|pre-push> [git's hook args]
 *   exit 0 lets git proceed; exit 1 aborts the commit or push. Reasons go to stderr.
 *
 * pre-commit, stopping at the first failure:
 *   1. a commit to a protected branch that already has history is refused;
 *   2. `gitleaks git --pre-commit --staged`, when gitleaks is installed;
 *   3. the feedback runner's `run --staged` over the staged files;
 *   4. a pre-existing `.git/hooks/pre-commit`, chained.
 * pre-push: a push to a protected branch is refused, then a pre-existing
 *   `.git/hooks/pre-push` is chained with the same arguments and stdin.
 *
 * The protected list is `git.protectedBranches` in `.sdd/permissions/policy.json`, the
 * same list the permissions guard reads. The only bypass is git's own `--no-verify`,
 * which the permissions baseline denies to agents.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
/** The install directory: this script lives at `<install>/.sdd/git-hooks/`. */
const INSTALL_DIR = path.resolve(SCRIPT_DIR, '..', '..');
const POLICY_PATH = path.join(INSTALL_DIR, '.sdd', 'permissions', 'policy.json');
const FEEDBACK_RUNNER = path.join(INSTALL_DIR, '.sdd', 'feedback', 'run-feedback.mjs');
const COMMANDS_PATH = path.join(SCRIPT_DIR, 'commands.json');
const ZERO_OBJECT = /^0+$/;

function notice(message) {
  process.stderr.write(`harny commit-checks: ${message}\n`);
}

function fail(message) {
  notice(message);
  process.exit(1);
}

function git(args, cwd = process.cwd()) {
  try {
    return execFileSync('git', args, { cwd, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return undefined;
  }
}

/** `*` stays within one `/`-separated segment (permissions-baseline PB-7). */
function branchRegExp(glob) {
  const escaped = glob.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*');
  return new RegExp(`^${escaped}$`);
}

function protectedBranches() {
  try {
    const policy = JSON.parse(fs.readFileSync(POLICY_PATH, 'utf8'));
    const list = policy && policy.git && policy.git.protectedBranches;
    if (Array.isArray(list) && list.every((item) => typeof item === 'string')) {
      return list.map(branchRegExp);
    }
  } catch {
    // fall through to the notice below
  }
  notice(`${POLICY_PATH} is missing or invalid; protected-branch checks skipped`);
  return [];
}

function isProtected(patterns, branch) {
  return patterns.some((pattern) => pattern.test(branch));
}

/** Runs `.git/hooks/<name>` if it exists, is executable, and is not this hook. */
function chain(name, args, input) {
  const commonDir = git(['rev-parse', '--git-common-dir']);
  if (!commonDir) return;
  const legacy = path.resolve(commonDir, 'hooks', name);
  try {
    fs.accessSync(legacy, fs.constants.X_OK);
  } catch {
    return;
  }
  if (fs.realpathSync(legacy) === fs.realpathSync(path.join(SCRIPT_DIR, name))) return;
  const result = spawnSync(legacy, args, {
    input,
    stdio: [input === undefined ? 'inherit' : 'pipe', 'inherit', 'inherit'],
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function preCommit(args) {
  const top = git(['rev-parse', '--show-toplevel']) ?? process.cwd();

  const branch = git(['symbolic-ref', '--quiet', '--short', 'HEAD']);
  const hasHistory = git(['rev-parse', '--verify', '--quiet', 'HEAD']) !== undefined;
  if (branch && hasHistory && isProtected(protectedBranches(), branch)) {
    fail(`committing to protected branch "${branch}" is refused; create a feature branch and open a pull request`);
  }

  const leaks = spawnSync('gitleaks', ['git', '--pre-commit', '--staged', '--redact', '--no-banner'], {
    cwd: top,
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  if (leaks.error) {
    notice('gitleaks is not installed; the staged-secret scan was skipped (CI still scans)');
  } else if (leaks.status !== 0) {
    fail('gitleaks reported a secret in the staged changes; remove it before committing');
  }

  if (fs.existsSync(FEEDBACK_RUNNER) && fs.existsSync(COMMANDS_PATH)) {
    const lint = spawnSync(process.execPath, [FEEDBACK_RUNNER, 'run', '--staged', '--commands', COMMANDS_PATH], {
      cwd: INSTALL_DIR,
      stdio: ['ignore', 'inherit', 'inherit'],
    });
    if (lint.status !== 0) {
      fail('a lint check reported findings on the staged files; fix them before committing');
    }
  } else {
    notice('feedback runner or commands.json missing; staged lint skipped (run npx harny init)');
  }

  chain('pre-commit', args, undefined);
}

function prePush(args) {
  let input = '';
  try {
    input = fs.readFileSync(0, 'utf8');
  } catch {
    input = '';
  }
  const lines = input.split('\n').filter((line) => line.trim().length > 0);
  if (lines.length > 0) {
    const patterns = protectedBranches();
    for (const line of lines) {
      const [, localObject, remoteRef] = line.split(' ');
      if (!remoteRef || !remoteRef.startsWith('refs/heads/')) continue;
      const branch = remoteRef.slice('refs/heads/'.length);
      if (isProtected(patterns, branch)) {
        const action = localObject && ZERO_OBJECT.test(localObject) ? 'deleting' : 'pushing to';
        fail(`${action} protected branch "${branch}" is refused; push a feature branch and open a pull request`);
      }
    }
  }
  chain('pre-push', args, input);
}

const [hook, ...args] = process.argv.slice(2);
if (hook === 'pre-commit') {
  preCommit(args);
} else if (hook === 'pre-push') {
  prePush(args);
} else {
  fail(`unknown hook "${hook ?? ''}" (expected pre-commit or pre-push)`);
}
process.exit(0);
