/**
 * Component discovery (specs/component-level-docs). Copied byte-for-byte into every
 * install at `.sdd/shared/components.mjs`, imported by the doctor runner, and loaded
 * by `harny init` from the templates root, so there is exactly one implementation of
 * "what are this repository's components" (CL-1). Node builtins only.
 *
 * A component is (CL-2):
 *   (a) a non-root directory, at most `maxDepth` levels down, holding one of
 *       `manifests` (a package of its own);
 *   (b) a `declared` directory (monorepo components from `.sdd/harness.json`);
 *   (c) a direct child directory of a top-level `sourceRoots` entry that holds at
 *       least `minFiles` files of its own (a domain inside a single package).
 * Directories named in `ignore`, and every hidden directory, are never entered.
 * Results are POSIX paths relative to the root, sorted and unique, never '.'.
 */
import fs from 'node:fs';
import path from 'node:path';

function listDir(dir) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
}

function enterable(entry, ignore) {
  return entry.isDirectory() && !entry.name.startsWith('.') && !ignore.has(entry.name);
}

export function discoverComponents(root, options) {
  const ignore = new Set(options.ignore ?? []);
  const manifests = new Set(options.manifests ?? []);
  const maxDepth = options.maxDepth ?? 3;
  const minFiles = options.minFiles ?? 3;
  const found = new Set();

  const walk = (relative, depth) => {
    if (depth > maxDepth) return;
    const entries = listDir(path.join(root, relative));
    if (depth > 0 && entries.some((entry) => entry.isFile() && manifests.has(entry.name))) {
      found.add(relative);
    }
    for (const entry of entries) {
      if (enterable(entry, ignore)) walk(relative ? `${relative}/${entry.name}` : entry.name, depth + 1);
    }
  };
  walk('', 0);

  for (const declared of options.declared ?? []) {
    const normalized = declared.replace(/\\/g, '/').replace(/^\.\/+/, '').replace(/\/+$/, '');
    if (normalized && normalized !== '.') found.add(normalized);
  }

  for (const sourceRoot of options.sourceRoots ?? []) {
    for (const entry of listDir(path.join(root, sourceRoot))) {
      if (!enterable(entry, ignore)) continue;
      const relative = `${sourceRoot}/${entry.name}`;
      const fileCount = listDir(path.join(root, relative)).filter((child) => child.isFile()).length;
      if (fileCount >= minFiles) found.add(relative);
    }
  }

  return [...found].sort();
}

/** `apps/web` → `apps-web`: a component as a single path segment. */
export function componentSlug(dir) {
  return dir.split('/').filter(Boolean).join('-');
}

/** Fills `{dir}` and `{slug}` in a bridge path or contents template. */
export function fillComponentTemplate(template, dir) {
  return template.split('{dir}').join(dir).split('{slug}').join(componentSlug(dir));
}
