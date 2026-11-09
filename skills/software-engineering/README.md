# software-engineering

Agent skill for coding, debugging, configuring, testing and reviewing: local implementation decisions, and guards against recurring coding-agent failures. Structural decisions belong to [software-architecture](../software-architecture/): when a task needs one, including one discovered mid-implementation, this skill loads it and both apply. The two skills are independent and loading one does not replace the other.

## Install

Install just this skill, globally:

```bash
npx skills add n0ctx/skills --skill software-engineering -g
```

`SKILL.md` lives at `skills/software-engineering/SKILL.md` in the monorepo. `evals/` and `research/` are maintainer material and are not loaded during coding.

A same-named copy in a higher-precedence directory (for example `~/.hermes/skills/`) hides this one. Keep one visible copy. Hermes also needs `skills.external_dirs` to include `~/.agents/skills`.

## Status

`evals/software-engineering.md` is the check plan; `research/` explains why the current rules exist. Only directional pilots have been run (results in `research/`); this release is a candidate, not a measured improvement. Current version: 1.3.2.

## Install as a Claude Code plugin

```
/plugin install software-engineering --marketplace n0ctx/skills
```
