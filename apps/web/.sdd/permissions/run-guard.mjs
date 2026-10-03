#!/usr/bin/env node
/**
 * harny permissions guard — the tool-neutral pre-tool-call check every generated
 * harness wires to its own "before a tool runs" hook (specs/permissions-baseline).
 *
 * Copied byte-for-byte into every install at `.sdd/permissions/run-guard.mjs`, beside
 * the editable baseline `policy.json`. Node builtins only.
 *
 * Usage: node run-guard.mjs [--policy <path>]
 *   stdin : the tool's raw pre-tool hook event, as JSON
 *   exit 0: allow (nothing on stdout; a notice may go to stderr)
 *   exit 2: deny  (one line on stderr: the reason)
 *   exit 3: ask   (one line on stderr: the reason)
 *
 * Each tool's hook wrapper translates those three outcomes into that tool's own
 * decision channel; this script never knows which tool called it.
 *
 * Best-effort by nature: it reads the command text the agent wrote, not what a
 * program does once it runs. An interpreter that opens a file itself is not caught.
 * It raises the floor; git hooks and server-side branch protection are the walls.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ALLOW = 0;
const DENY = 2;
const ASK = 3;

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
/** The install directory: this script lives at `<install>/.sdd/permissions/`. */
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, '..', '..');

/** Shell programs whose path arguments are file reads (PB-4). */
const READ_PROGRAMS = new Set([
  'cat', 'less', 'more', 'head', 'tail', 'bat', 'nl', 'xxd', 'od', 'strings', 'base64',
  'source', '.', 'cp', 'scp', 'grep', 'sed', 'awk',
]);
/** Leading wrappers stripped before a subcommand is judged (PB-3). */
const WRAPPERS = new Set(['sudo', 'env', 'command', 'nohup', 'time']);
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash']);
/** git verbs that write history onto the branch in effect (PB-6). */
const HISTORY_WRITERS = new Set(['commit', 'merge', 'cherry-pick', 'revert', 'am', 'rebase']);
/** git global options that consume the next token. */
const GIT_VALUE_OPTIONS = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace']);
/** `git push` options that consume the next token. */
const PUSH_VALUE_OPTIONS = new Set(['--repo', '-o', '--push-option', '--receive-pack', '--exec']);

function finish(code, message) {
  if (message) {
    process.stderr.write(`${message}\n`);
  }
  process.exit(code);
}

function parseArgs(argv) {
  const index = argv.indexOf('--policy');
  return index >= 0 && argv[index + 1] ? path.resolve(argv[index + 1]) : path.join(SCRIPT_DIR, 'policy.json');
}

function isStringArray(value) {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isRuleArray(value) {
  return (
    Array.isArray(value) &&
    value.every(
      (rule) => rule && typeof rule === 'object' && typeof rule.pattern === 'string' && typeof rule.reason === 'string',
    )
  );
}

/** Mirrors `parsePermissionPolicy` in `src/permissions.ts` (PB-1). */
function validPolicy(policy) {
  if (!policy || typeof policy !== 'object' || Array.isArray(policy)) return false;
  const keys = Object.keys(policy).sort().join(',');
  return (
    keys === 'commands,git,read,version' &&
    policy.version === 1 &&
    policy.git && isStringArray(policy.git.protectedBranches) &&
    policy.read && isStringArray(policy.read.deny) && isStringArray(policy.read.allow) &&
    policy.commands && isRuleArray(policy.commands.deny) && isRuleArray(policy.commands.ask)
  );
}

function loadPolicy(policyPath) {
  let source;
  try {
    source = fs.readFileSync(policyPath, 'utf8');
  } catch {
    finish(ALLOW, `harny-permissions: ${policyPath} not found; the permissions guard is inactive (run npx harny init)`);
  }
  let policy;
  try {
    policy = JSON.parse(source);
  } catch {
    policy = undefined;
  }
  if (!validPolicy(policy)) {
    finish(DENY, `harny-permissions: ${policyPath} is not a valid permissions policy; fix it before any tool call can proceed`);
  }
  return policy;
}

function readStdinJson() {
  try {
    return JSON.parse(fs.readFileSync(0, 'utf8'));
  } catch {
    return undefined;
  }
}

/** Accepts `toolArgs` as an object or as a JSON string (Copilot sends both). */
function objectOf(value) {
  if (value && typeof value === 'object') return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

/** The only place the five tools' payload shapes meet (contract § Input normalization). */
function normalize(payload) {
  const input = objectOf(payload.tool_input);
  const args = objectOf(payload.toolArgs);
  const command = [input.command, args.command, payload.command].find((value) => typeof value === 'string');
  const paths = [input.file_path, input.path, args.path, payload.file_path].filter((value) => typeof value === 'string');
  if (Array.isArray(input.operations)) {
    for (const operation of input.operations) {
      if (operation && typeof operation.path === 'string') paths.push(operation.path);
    }
  }
  const name = String(payload.tool_name ?? payload.toolName ?? '');
  const isRead = /read|view/i.test(name) || payload.hook_event_name === 'beforeReadFile';
  const cwd = typeof payload.cwd === 'string' && payload.cwd.length > 0 ? payload.cwd : process.cwd();
  return { command, readPaths: isRead ? paths : [], cwd };
}

function escapeRegExp(text) {
  return text.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
}

/** Wildcard `*` = any run of characters; whole-string match (PB-5). */
function commandPatternRegExp(pattern) {
  return new RegExp(`^${pattern.split('*').map((part) => escapeRegExp(part)).join('.*')}$`);
}

/** gitignore-style glob to RegExp: `**` crosses segments, `*`/`?` do not. */
function globRegExp(glob) {
  let out = '';
  for (let i = 0; i < glob.length; i += 1) {
    const char = glob[i];
    if (char === '*') {
      if (glob[i + 1] === '*') {
        const slashAfter = glob[i + 2] === '/';
        out += slashAfter ? '(?:.*/)?' : '.*';
        i += slashAfter ? 2 : 1;
      } else {
        out += '[^/]*';
      }
    } else if (char === '?') {
      out += '[^/]';
    } else {
      out += escapeRegExp(char);
    }
  }
  return new RegExp(`^${out}$`);
}

/** gitignore semantics: no `/` matches the basename at any depth; a `/` anchors. */
function pathMatches(pattern, relative) {
  const anchored = pattern.replace(/^\//, '');
  if (!anchored.includes('/')) {
    return globRegExp(anchored).test(path.posix.basename(relative));
  }
  if (relative.startsWith('../')) return false;
  return globRegExp(anchored).test(relative);
}

function judgeRead(policy, rawPath, cwd) {
  const absolute = path.resolve(cwd, rawPath);
  const relative = path.relative(PROJECT_ROOT, absolute).split(path.sep).join('/');
  const denied = policy.read.deny.find((pattern) => pathMatches(pattern, relative));
  if (!denied || policy.read.allow.some((pattern) => pathMatches(pattern, relative))) {
    return undefined;
  }
  return `harny-permissions: reading ${relative} is denied (matches read.deny "${denied}"); secrets stay out of the agent's context`;
}

/**
 * Splits a command into subcommands of tokens, outside quotes, on `&&`, `||`, `;`,
 * `|`, `|&`, `&` and newlines. `<` redirection targets are collected separately.
 */
function splitCommand(command) {
  const subcommands = [];
  let tokens = [];
  let redirects = [];
  let token = '';
  let hasToken = false;
  let quote = '';
  let pendingRedirect = false;

  const endToken = () => {
    if (hasToken) {
      if (pendingRedirect) {
        redirects.push(token);
        pendingRedirect = false;
      } else {
        tokens.push(token);
      }
    }
    token = '';
    hasToken = false;
  };
  const endSubcommand = () => {
    endToken();
    if (tokens.length > 0 || redirects.length > 0) subcommands.push({ tokens, redirects });
    tokens = [];
    redirects = [];
  };

  for (let i = 0; i < command.length; i += 1) {
    const char = command[i];
    if (quote) {
      if (char === quote) {
        quote = '';
      } else if (char === '\\' && quote === '"' && i + 1 < command.length) {
        token += command[++i];
      } else {
        token += char;
      }
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      hasToken = true;
    } else if (char === '\\' && i + 1 < command.length) {
      token += command[++i];
      hasToken = true;
    } else if (char === '\n' || char === ';') {
      endSubcommand();
    } else if (char === '&' || char === '|') {
      if (command[i + 1] === char || (char === '|' && command[i + 1] === '&')) i += 1;
      endSubcommand();
    } else if (char === '<' && command.startsWith('<<<', i)) {
      // A here-string feeds a word, not a file (Amendment A1).
      endToken();
      i += 2;
    } else if (char === '<') {
      endToken();
      pendingRedirect = true;
    } else if (char === '>') {
      endToken();
      if (command[i + 1] === '>') i += 1;
    } else if (char === ' ' || char === '\t') {
      endToken();
    } else {
      token += char;
      hasToken = true;
    }
  }
  endSubcommand();
  return subcommands;
}

/**
 * Removes heredoc bodies — `<<DELIM` / `<<-DELIM`, delimiter quoted or not — up to
 * the line equal to the delimiter, along with the operator itself, so text a command
 * merely writes is never judged as commands (Amendment A1, PB-3).
 */
function stripHeredocs(command) {
  let out = '';
  let quote = '';
  const pending = [];
  for (let i = 0; i < command.length; i += 1) {
    const char = command[i];
    if (quote) {
      if (char === quote) quote = '';
      out += char;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      out += char;
    } else if (char === '<' && command.startsWith('<<', i) && !command.startsWith('<<<', i)) {
      let j = i + 2;
      const dash = command[j] === '-';
      if (dash) j += 1;
      while (command[j] === ' ' || command[j] === '\t') j += 1;
      const match = /^(['"]?)([A-Za-z0-9_.-]+)\1/.exec(command.slice(j));
      if (!match) {
        out += char;
        continue;
      }
      pending.push({ delimiter: match[2], dash });
      i = j + match[0].length - 1;
    } else if (char === '\n' && pending.length > 0) {
      out += char;
      let rest = i + 1;
      for (const { delimiter, dash } of pending.splice(0)) {
        for (;;) {
          const end = command.indexOf('\n', rest);
          const line = command.slice(rest, end < 0 ? command.length : end);
          rest = end < 0 ? command.length : end + 1;
          if ((dash ? line.replace(/^\t+/, '') : line) === delimiter || end < 0) break;
        }
      }
      i = rest - 1;
    } else {
      out += char;
    }
  }
  return out;
}

/** The bodies of `$(…)` and backtick substitutions outside single quotes, each of
 *  which is judged as a command line of its own (Amendment A1, PB-3). */
function substitutions(command) {
  const bodies = [];
  let single = false;
  for (let i = 0; i < command.length; i += 1) {
    const char = command[i];
    if (char === "'") {
      single = !single;
    } else if (!single && char === '$' && command[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      while (j < command.length && depth > 0) {
        if (command[j] === '(') depth += 1;
        if (command[j] === ')') depth -= 1;
        j += 1;
      }
      bodies.push(command.slice(i + 2, j - 1));
      i = j - 1;
    } else if (!single && char === '`') {
      const end = command.indexOf('`', i + 1);
      if (end < 0) break;
      bodies.push(command.slice(i + 1, end));
      i = end;
    }
  }
  return bodies;
}

/** Index of the git verb in a `git …` token list, past git's global options. */
function gitVerbIndex(tokens) {
  let i = 1;
  while (i < tokens.length && tokens[i].startsWith('-')) {
    i += GIT_VALUE_OPTIONS.has(tokens[i]) ? 2 : 1;
  }
  return i;
}

/** The forms a subcommand is matched in (Amendment A1, PB-5): as written; with the
 *  program reduced to its basename; for git, without git's global options. */
function matchForms(tokens) {
  const program = path.posix.basename(tokens[0]);
  const forms = [tokens.join(' ')];
  if (program !== tokens[0]) forms.push([program, ...tokens.slice(1)].join(' '));
  if (program === 'git') {
    const verb = gitVerbIndex(tokens);
    if (verb > 1) forms.push(['git', ...tokens.slice(verb)].join(' '));
  }
  return forms;
}

/** Strips `VAR=value` prefixes and the leading wrappers; unwraps one `sh -c` level. */
function expand(subcommands) {
  const out = [];
  for (const subcommand of subcommands) {
    let tokens = subcommand.tokens.slice();
    for (;;) {
      if (tokens.length > 0 && /^[A-Za-z_][A-Za-z0-9_]*=/.test(tokens[0])) {
        tokens.shift();
      } else if (tokens.length > 0 && WRAPPERS.has(tokens[0])) {
        tokens.shift();
        while (tokens.length > 0 && tokens[0].startsWith('-')) tokens.shift();
      } else {
        break;
      }
    }
    const inner = tokens.indexOf('-c');
    if (tokens.length > 0 && SHELLS.has(path.posix.basename(tokens[0])) && inner > 0 && tokens[inner + 1] !== undefined) {
      out.push(...expand(splitCommand(tokens[inner + 1])));
      continue;
    }
    out.push({ tokens, redirects: subcommand.redirects });
  }
  return out;
}

function branchMatches(patterns, branch) {
  return patterns.some((pattern) => globRegExp(pattern).test(branch));
}

const branchCache = new Map();
function currentBranch(dir) {
  if (!branchCache.has(dir)) {
    let branch;
    try {
      branch = execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], {
        cwd: dir,
        stdio: ['ignore', 'pipe', 'ignore'],
      })
        .toString()
        .trim();
    } catch {
      branch = undefined;
    }
    branchCache.set(dir, branch && branch !== 'HEAD' ? branch : undefined);
  }
  return branchCache.get(dir);
}

function checkoutTarget(verb, args, dir) {
  const createFlags = verb === 'switch' ? ['-c', '-C', '--create', '--force-create'] : ['-b', '-B', '--orphan'];
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === '--') return undefined;
    if (createFlags.includes(args[i])) return args[i + 1];
  }
  const positional = args.filter((arg) => !arg.startsWith('-'));
  if (positional.length !== 1) return undefined;
  // `git checkout <file>` restores a file; only a non-path argument is a branch.
  return verb === 'checkout' && fs.existsSync(path.resolve(dir, positional[0])) ? undefined : positional[0];
}

function pushDestinations(args, inEffect) {
  const positional = [];
  let deleting = false;
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--all' || arg === '--mirror' || arg === '--branches') return { everything: true, targets: [] };
    if (arg === '--delete' || arg === '-d') deleting = true;
    if (PUSH_VALUE_OPTIONS.has(arg)) {
      i += 1;
    } else if (!arg.startsWith('-')) {
      positional.push(arg);
    }
  }
  const refspecs = positional.slice(1);
  if (refspecs.length === 0) return { everything: false, targets: [inEffect] };
  const targets = refspecs.map((refspec) => {
    const spec = refspec.replace(/^\+/, '');
    const colon = spec.indexOf(':');
    let destination = colon >= 0 ? spec.slice(colon + 1) || spec.slice(0, colon) : spec;
    if (deleting) destination = spec;
    if (destination === 'HEAD') return inEffect;
    return destination.replace(/^refs\/heads\//, '');
  });
  return { everything: false, targets };
}

/** PB-6: protected branches, resolved rather than pattern-matched. */
function judgeGit(policy, tokens, state) {
  let i = 1;
  let dir = state.cwd;
  while (i < tokens.length && tokens[i].startsWith('-')) {
    if (tokens[i] === '-C' && tokens[i + 1] !== undefined) dir = path.resolve(dir, tokens[i + 1]);
    i += GIT_VALUE_OPTIONS.has(tokens[i]) ? 2 : 1;
  }
  const verb = tokens[i];
  const args = tokens.slice(i + 1);
  if (!verb) return undefined;
  const inEffect = dir === state.cwd && state.branch !== null ? state.branch : currentBranch(dir);
  const protectedList = policy.git.protectedBranches;

  if (verb === 'checkout' || verb === 'switch') {
    const target = checkoutTarget(verb, args, dir);
    if (target && dir === state.cwd) state.branch = target;
    return undefined;
  }
  if (HISTORY_WRITERS.has(verb)) {
    if (args.includes('--abort') || args.includes('--quit')) return undefined;
    if (inEffect && branchMatches(protectedList, inEffect)) {
      return `harny-permissions: git ${verb} on protected branch "${inEffect}" is denied; create a feature branch first`;
    }
    return undefined;
  }
  if (verb === 'push') {
    const { everything, targets } = pushDestinations(args, inEffect);
    if (everything) {
      return 'harny-permissions: git push --all/--mirror would push protected branches and is denied; push one feature branch';
    }
    const hit = targets.find((target) => target && branchMatches(protectedList, target));
    if (hit) {
      return `harny-permissions: pushing to protected branch "${hit}" is denied; push a feature branch and open a pull request`;
    }
  }
  return undefined;
}

function judgeCommand(policy, command, cwd) {
  const state = { cwd, branch: null };
  const deny = policy.commands.deny.map((rule) => ({ ...rule, regexp: commandPatternRegExp(rule.pattern) }));
  const ask = policy.commands.ask.map((rule) => ({ ...rule, regexp: commandPatternRegExp(rule.pattern) }));
  let asked;
  const stripped = stripHeredocs(command);
  const lines = [stripped];
  for (let k = 0; k < lines.length; k += 1) lines.push(...substitutions(lines[k]));
  const subcommands = lines.flatMap((line) => expand(splitCommand(line)));

  for (const { tokens, redirects } of subcommands) {
    for (const target of redirects) {
      const reason = judgeRead(policy, target, cwd);
      if (reason) return { code: DENY, reason };
    }
    if (tokens.length === 0) continue;
    const text = tokens.join(' ');
    const forms = matchForms(tokens);
    const denied = deny.find((rule) => forms.some((form) => rule.regexp.test(form)));
    if (denied) return { code: DENY, reason: `harny-permissions: "${text}" is denied: ${denied.reason}` };
    if (READ_PROGRAMS.has(path.posix.basename(tokens[0]))) {
      for (const arg of tokens.slice(1)) {
        if (arg.startsWith('-')) continue;
        const reason = judgeRead(policy, arg, cwd);
        if (reason) return { code: DENY, reason };
      }
    }
    if (path.posix.basename(tokens[0]) === 'git') {
      const reason = judgeGit(policy, tokens, state);
      if (reason) return { code: DENY, reason };
    }
    if (!asked) {
      const rule = ask.find((candidate) => forms.some((form) => candidate.regexp.test(form)));
      if (rule) asked = { code: ASK, reason: `harny-permissions: "${text}" needs human approval: ${rule.reason}` };
    }
  }
  return asked ?? { code: ALLOW };
}

function main() {
  const policy = loadPolicy(parseArgs(process.argv.slice(2)));
  const payload = readStdinJson();
  if (!payload || typeof payload !== 'object') finish(ALLOW);
  const { command, readPaths, cwd } = normalize(payload);

  for (const readPath of readPaths) {
    const reason = judgeRead(policy, readPath, cwd);
    if (reason) finish(DENY, reason);
  }
  if (command !== undefined) {
    const decision = judgeCommand(policy, command, cwd);
    finish(decision.code, decision.reason);
  }
  finish(ALLOW);
}

main();
