# software-engineering

Agent skill for coding, debugging, configuring, testing and reviewing: local implementation decisions, and guards against recurring coding-agent failures. Structural decisions belong to [software-architecture](https://github.com/n0ctx/software-architecture); the two skills are independent and loading one does not cancel the other.

## Install

Clone straight into the skills directory your agent reads:

```sh
git clone https://github.com/n0ctx/software-engineering.git ~/.agents/skills/software-engineering
```

`SKILL.md` is at the repository root, so the clone is the skill. `references/` is loaded only when `SKILL.md` says to. `evals/` and `research/` are maintainer material and are not loaded during coding.

A same-named copy in a higher-precedence directory (for example `~/.hermes/skills/`) hides this one. Keep one visible copy. Hermes also needs `skills.external_dirs` to include `~/.agents/skills`.

## Status

`evals/software-engineering.md` is the check plan; `research/software-engineering-v1.2.md` explains why the current rules exist. Neither has been run as a live A/B test, so this release is a candidate, not a measured improvement. Current version: 1.2.1.
