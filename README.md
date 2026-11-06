# Skills

[中文](README.zh-CN.md)

Personal collection of agent skills. Each skill is a self-contained directory, with `SKILL.md` as its entry point.

## Index

| Skill | Purpose |
|---|---|
| dag-engineering | Planning and control for large multi-session engineering work |
| guard-ratchet | Ratchet-style source guards: complexity, dead code, duplication, N+1, cycles, test shape |
| software-architecture | Architecture work: boundaries, trade-offs, migrations, decision records |
| software-engineering | Coding, debugging, configuration, testing, review |
| tavern-aesthetic | Immersive UI design for role-play, interactive fiction, and narrative pages |
| writing-for-agents | Writing and revising text agents read and execute: prompts, SKILL.md, AGENTS.md, handoffs |

## Install

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
~/Projects/skills/scripts/link.sh           # link into ~/.agents/skills
~/Projects/skills/scripts/link.sh --dry-run # preview changes only
```

`link.sh` symlinks `skills/<name>` into `~/.agents/skills/<name>`. Only directories recognized as skills (containing `SKILL.md`) are linked, and existing real directories are never overwritten.

## Update

```bash
cd ~/Projects/skills && git pull
```

Symlinks point inside the skill directories, so every agent picks up changes after a pull. No reinstall needed.

## Layout

```
skills/
└── <name>/
    ├── SKILL.md          # Required; YAML frontmatter with name/description
    ├── references/       # Optional; docs loaded on demand
    └── scripts/          # Optional; executable scripts
```

## License

See the LICENSE file in each skill directory. Skills without one are all rights reserved.
