#!/usr/bin/env node
// Checks that every skill is discoverable and registered consistently:
// skills/<name>/SKILL.md frontmatter, skills/<name>/.claude-plugin/plugin.json,
// and its entry in .claude-plugin/marketplace.json must agree.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const errors = [];
const fail = (where, message) => errors.push(`${where}: ${message}`);

function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch (error) {
    fail(path.relative(root, file), error.code === 'ENOENT' ? 'missing' : `invalid JSON (${error.message})`);
    return null;
  }
}

// An unquoted one-line value that strict YAML parsers reject or cut short:
// `: ` reads as a nested mapping, ` #` starts a comment, and a leading
// indicator character changes the value's type. Lenient readers (Claude Code)
// still show such a value, so the break only appears in other tools.
function plainScalarProblem(value) {
  if (!value || /^(>-?|\|-?)$/.test(value) || /^(["']).*\1$/.test(value)) return null;
  if (/:(\s|$)/.test(value)) return 'contains ": "';
  if (/\s#/.test(value)) return 'contains " #"';
  if (/^[-?:,\[\]{}#&*!|>'"%@`]/.test(value)) return `starts with "${value[0]}"`;
  return null;
}

// Top-level keys of the leading --- block. A key with an empty inline value
// (e.g. `description: >-`) takes its indented continuation lines.
function frontmatter(text, where) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(\r?\n|$)/.exec(text);
  if (!match) return null;
  const fields = {};
  let current = null;
  for (const line of match[1].split(/\r?\n/)) {
    const key = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
    if (key) {
      current = key[1];
      const problem = plainScalarProblem(key[2].trim());
      if (problem) fail(where, `${current} ${problem}; quote the value or use a >- block so strict YAML parsers can read it`);
      fields[current] = key[2].replace(/^(>-?|\|-?)$/, '').replace(/^"(.*)"$/, '$1').trim();
    } else if (current && /^\s+\S/.test(line) && !fields[current]?.length) {
      fields[current] = line.trim();
    }
  }
  return fields;
}

const skillsDir = path.join(root, 'skills');
const names = readdirSync(skillsDir, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

const marketplace = readJson(path.join(root, '.claude-plugin', 'marketplace.json'));
const listed = new Map((marketplace?.plugins ?? []).map((plugin) => [plugin.name, plugin]));

for (const name of names) {
  const where = `skills/${name}`;
  const skillFile = path.join(skillsDir, name, 'SKILL.md');
  if (!existsSync(skillFile)) {
    fail(where, 'missing SKILL.md');
    continue;
  }
  const fm = frontmatter(readFileSync(skillFile, 'utf8'), `${where}/SKILL.md`);
  if (!fm) {
    fail(`${where}/SKILL.md`, 'missing --- frontmatter block');
    continue;
  }
  if (fm.name !== name) fail(`${where}/SKILL.md`, `frontmatter name "${fm.name ?? ''}" must equal directory name`);
  if (!fm.description) fail(`${where}/SKILL.md`, 'frontmatter description is empty');

  const plugin = readJson(path.join(skillsDir, name, '.claude-plugin', 'plugin.json'));
  if (plugin) {
    if (plugin.name !== name) fail(`${where}/.claude-plugin/plugin.json`, `name "${plugin.name}" must equal directory name`);
    if (!/^\d+\.\d+\.\d+$/.test(plugin.version ?? '')) fail(`${where}/.claude-plugin/plugin.json`, 'version must be x.y.z');
    if (fm.version && fm.version !== plugin.version) {
      fail(where, `SKILL.md version ${fm.version} differs from plugin.json version ${plugin.version}`);
    }
  }

  const entry = listed.get(name);
  if (!entry) {
    fail('.claude-plugin/marketplace.json', `no plugin entry for ${name}`);
  } else {
    if (entry.source !== `./skills/${name}`) fail('.claude-plugin/marketplace.json', `${name} source must be ./skills/${name}`);
    if (plugin && entry.description !== plugin.description) {
      fail('.claude-plugin/marketplace.json', `${name} description differs from its plugin.json`);
    }
  }
}

for (const name of listed.keys()) {
  if (!names.includes(name)) fail('.claude-plugin/marketplace.json', `entry ${name} has no skills/${name} directory`);
}

if (errors.length) {
  console.error(errors.map((error) => `✗ ${error}`).join('\n'));
  process.exit(1);
}
console.log(`✓ ${names.length} skills consistent across SKILL.md, plugin.json, and marketplace.json`);
