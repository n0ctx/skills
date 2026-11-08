# software-architecture

Agent skill for structural decisions and trade-offs: boundaries, distributed state and failure, evolving existing systems, decision records. Not for routine coding; that stays with [software-engineering](../software-engineering/). The two skills are independent and loading one does not cancel the other.

## Install

Install just this skill, globally:

```bash
npx skills add n0ctx/skills --skill software-architecture -g
```

`SKILL.md` lives at `skills/software-architecture/SKILL.md` in the monorepo. `references/` is loaded only when `SKILL.md` says to.

A same-named copy in a higher-precedence directory (for example `~/.hermes/skills/`) hides this one. Keep one visible copy. Hermes also needs `skills.external_dirs` to include `~/.agents/skills`.

## Status

No eval plan yet; this release is a candidate, not a measured improvement. Current version: 1.1.0.

## Install as a Claude Code plugin

```
/plugin install software-architecture --marketplace n0ctx/skills
```
