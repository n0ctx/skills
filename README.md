# software-architecture

Agent skill for structural decisions and trade-offs: boundaries, distributed state and failure, evolving existing systems, decision records. Not for routine coding; that stays with [software-engineering](https://github.com/n0ctx/software-engineering). The two skills are independent and loading one does not cancel the other.

## Install

Clone straight into the skills directory your agent reads:

```sh
git clone https://github.com/n0ctx/software-architecture.git ~/.agents/skills/software-architecture
```

`SKILL.md` is at the repository root, so the clone is the skill. `references/` is loaded only when `SKILL.md` says to.

A same-named copy in a higher-precedence directory (for example `~/.hermes/skills/`) hides this one. Keep one visible copy. Hermes also needs `skills.external_dirs` to include `~/.agents/skills`.

## Status

No eval plan yet; this release is a candidate, not a measured improvement. Current version: 1.0.0.
