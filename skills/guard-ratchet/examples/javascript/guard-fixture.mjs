/**
 * Shared pieces of the detector fixture tests: build a small repository in a temporary directory,
 * run a detector script against it, and delete the directory after the tests.
 */

import { after } from 'node:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPTS_DIR = path.dirname(fileURLToPath(import.meta.url));

export function useGuardFixture(scriptName) {
  const dirs = [];
  after(() => dirs.forEach((d) => rmSync(d, { recursive: true, force: true })));

  const run = (root, ...args) => spawnSync(
    process.execPath, [path.join(SCRIPTS_DIR, scriptName), '--root', root, ...args], { encoding: 'utf8' },
  );

  return {
    makeRoot() {
      const root = mkdtempSync(path.join(os.tmpdir(), 'we-guard-'));
      dirs.push(root);
      return root;
    },
    write(root, rel, text) {
      mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
      writeFileSync(path.join(root, rel), text);
    },
    read(root, rel) {
      return readFileSync(path.join(root, rel), 'utf8');
    },
    run,
    // Run the detector and parse stdout as a detector@2 document; doc is null when there is no
    // output (for example on a usage error)
    scan(root, ...args) {
      const { status, stdout, stderr } = run(root, ...args);
      return { status, doc: stdout.trim() ? JSON.parse(stdout) : null, stderr };
    },
  };
}

// Item list -> ['rule:key', ...] in the existing order, for whole-list comparison
export const ruleKeys = (items) => items.map((item) => `${item.rule ?? item.metric}:${item.key}`);
