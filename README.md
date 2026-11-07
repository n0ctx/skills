# Skills

[Simplified Chinese](README.zh-CN.md)

English is the default for READMEs in this repo; Simplified Chinese versions live in `README.zh-CN.md` next to the English file.

Personal collection of agent skills. Each skill is a self-contained directory, with `SKILL.md` as its entry point.

## Index

| Skill | Purpose |
|---|---|
| dag-engineering | Planning and control for large multi-session engineering work |
| guard-ratchet | Ratchet-style source guards: complexity, dead code, duplication, N+1, cycles, test shape |
| reader-first-writing | Sentence-level readability for any text humans read, in any genre or language |
| software-architecture | Architecture work: boundaries, trade-offs, migrations, decision records |
| software-engineering | Coding, debugging, configuration, testing, review |
| tavern-aesthetic | Immersive UI design for role-play, interactive fiction, and narrative pages |
| writing-for-agents | Writing and revising text agents read and execute: prompts, SKILL.md, AGENTS.md, handoffs |

## Install

Each skill can be installed on its own, into any agent. Three paths; pick one.

### 1. skills CLI — per skill, per agent

```bash
npx skills add n0ctx/skills --list
npx skills add n0ctx/skills --skill guard-ratchet -a claude-code -g
npx skills add n0ctx/skills --skill tavern-aesthetic -a cursor -g --copy
```

| Flag | Meaning |
|---|---|
| `-s, --skill <name>` | Install one skill; repeat, comma-separate, or use `*` for all |
| `-a, --agent <name>` | Target agent, e.g. `claude-code`, `cursor`, `codex`; omit to pick interactively |
| `-g, --global` | User-level directory instead of the current project |
| `--copy` | Copy files instead of symlinking |
| `-l, --list` | Preview available skills without installing |

The CLI discovers `skills/<name>/SKILL.md` automatically. No manifest required.

### 2. Claude Code plugin marketplace

```bash
/plugin marketplace add n0ctx/skills
/plugin install guard-ratchet@n0ctx-skills
```

One step on Claude Code 2.1.275+:

```
/plugin install guard-ratchet --marketplace n0ctx/skills
```

The marketplace name comes from `name` in `.claude-plugin/marketplace.json` (`n0ctx-skills`); check `/plugin marketplace list` if your client registers it under a different name. One plugin per skill, each with its own `.claude-plugin/plugin.json`.

### 3. link.sh — self-hosted, symlink-based

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
~/Projects/skills/scripts/link.sh --dry-run
~/Projects/skills/scripts/link.sh --skill guard-ratchet --agent claude,workbuddy
~/Projects/skills/scripts/link.sh --agent all
~/Projects/skills/scripts/link.sh --skill tavern-aesthetic --agent cursor --copy
```

| Flag | Meaning |
|---|---|
| `--skill NAME` | Only these skills; repeatable or comma-separated. Default: all |
| `--agent NAME` | `agents`, `claude`, `workbuddy`, `codex`, `cursor`, `all`. Repeatable |
| `--target DIR` | Append a custom target directory |
| `--copy` | Copy instead of symlink |
| `--dry-run` | Print changes without touching anything |
| `--force` | Replace a real directory of the same name (moves it into `.trash`) |

With no flags, all skills are symlinked into `~/.agents/skills`. Missing target directories are created automatically.

## Update

| Install path | Update |
|---|---|
| link.sh (symlink) | `git pull` — every agent sees changes immediately |
| link.sh `--copy` | Re-run the same command |
| skills CLI | `npx skills update` |
| plugin marketplace | `/plugin marketplace update n0ctx-skills` |

## Uninstall

- CLI: `npx skills remove guard-ratchet -g`
- Marketplace: `/plugin uninstall guard-ratchet@n0ctx-skills`
- link.sh: `unlink` the symlink inside the agent's skills directory. Never delete the target it points to.

## Layout

```
skills/
└── <name>/
    ├── SKILL.md                     # Required; YAML frontmatter with name/description
    ├── .claude-plugin/plugin.json  # Claude Code plugin manifest
    ├── references/                 # Optional; docs loaded on demand
    └── scripts/                    # Optional; executable scripts
.claude-plugin/marketplace.json     # Marketplace catalog, one plugin per skill
scripts/link.sh                     # Local installer
```

## Compatibility notes

- Do not mix install paths in the same agent directory. If another tool already manages symlinks in `~/.claude/skills`, `~/.agents/skills`, or `~/.workbuddy/skills`, installing a skill with the same name will replace its link. Run `--dry-run` first; a "reset symlink" line means an existing link points somewhere else.
- Symlinks are the default for both the CLI and `link.sh`. Use `--copy` when the install must not depend on the clone path.
- Keep `SKILL.md` at `skills/<name>/SKILL.md`. Moving it deeper (e.g. `plugins/<name>/skills/<name>/SKILL.md`) breaks discovery by `npx skills add`. `plugin.json` uses `"skills": "./"` precisely to avoid that move.

## License

See the LICENSE file in each skill directory. Skills without one are all rights reserved.
