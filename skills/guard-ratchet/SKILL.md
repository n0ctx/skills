---
name: guard-ratchet
description: "Install and operate executable quality guards in any repository so that an autonomous coding agent cannot quietly make it worse: complexity and size thresholds adapted to code kind and language, lint/type/security findings ratcheted against a baseline, test integrity (deleted, skipped or weakened tests, test inventory, diff coverage, mutation score), secrets, dependency supply chain, migrations, API snapshots, generated-code drift, performance budgets, risk-tiered verification, and protection of the guard configuration itself (policy and baseline locks, exceptions with audit, trusted CI runs). Use when the user wants a quality gate, code health ratchet, baseline, fitness function, CI guard, or wants to stop regressions, test tampering or AI-generated code from slipping through, even without these words. Also use when a repository already has guard-ratchet guards and a check fails. Not for a one-off cleanup, a single lint error, running tests once, or a code review opinion."
---

# guard-ratchet

The goal is a repository in which every regression an agent could make, and a machine can detect reliably, fails a check that the agent cannot switch off. Existing problems are recorded in a baseline rather than fixed on day one. After that, a run fails on new problems, on existing problems getting worse, on improvements not recorded in the baseline, and on any attempt to loosen the rules, baselines or scan scope. Problems that a machine cannot judge reliably are reported as evidence, not as failures, so the gate stays trustworthy.

## What gets installed

- `tools/guard/`: the runner (`guard.py`, `guardlib/`, Python 3.10+, standard library only; 3.11+ to analyze TOML manifests such as `pyproject.toml` and `Cargo.toml`) and the bundled Semgrep rules (Python and JavaScript/TypeScript). It is copied into the repository so CI does not depend on where this skill is installed.
- `guards/policy.json`: which guards run, when, and with which thresholds. It only states what differs from the defaults in `scripts/guardlib/policy.py`.
- `guards/baselines/<guard>.json`: recorded findings, written only by `guard.py update`.
- `guards/exceptions.json`: the only way to let a new or worse problem pass. Each entry has a reason and an approver.

Detectors measure; the policy judges. A guard is an existing tool (linter, type checker, test runner, scanner) whose output the runner parses through a format adapter (SARIF, JUnit, LCOV/Cobertura/JaCoCo/Go coverage, ESLint JSON, lizard CSV, compiler text, detector JSON), or a built-in guard that needs no tool (secrets, suppressions, test changes, dependencies, migrations, file size, API snapshots, metrics, generated drift). Thresholds are applied centrally by code kind (logic, ui, model, test, script, migration, generated, vendor) and language. That is why the same complexity number can be fine in a JSX view and a problem in business logic.

## Reference files

Read each when you reach the step that needs it, not all at once.

| When | File |
|---|---|
| Before choosing guards | `references/guard-catalog.md`: every guard, what it blocks, what it only reports, defaults, false positives |
| Choosing tools for the stack | `references/language-recipes.md`: ready-to-paste guard entries per language and ecosystem |
| Editing the policy | `references/policy.md`: every field, the defaults, code kinds, roles, tiers |
| Semantics or a surprising result | `references/contract.md`: modes, categories, baselines, update rules, exceptions, CLI, report |
| Wiring CI and permissions | `references/trust-model.md`: what local runs can and cannot enforce, the trusted CI run, CODEOWNERS |
| Writing your own detector | `references/detector-contract.md` and `examples/javascript/` (seven reference detectors plus an API surface producer) |
| Anything goes wrong | `references/pitfalls.md` |

## Setting up guards in a repository

Work in this order, because each step relies on the previous one.

1. **Understand the repository.** Find the languages and which directories are production code, tests, generated code and vendored code. Find the tools already in use (linters, type checkers, test runners, coverage, CI) and whether lint or CI already fails today. If it does, tell the user, and later run each new guard on its own so the existing failure is not blamed on it. Find out whether other people or agents have uncommitted work in this checkout. Generating baselines from the base commit (step 4) keeps their half-finished work out of the baseline, but do not stash, reset or otherwise move their changes.

2. **Get a proposal.** Run `python3 <skill>/scripts/guard.py init --root <repo>` (a dry run). It profiles the repository and proposes guards that fit what is there: no migrations guard without migrations, no test inventory without a test runner that can write JUnit. Compare the proposal with what you found. Add the public API entry points (`roles.public-api`), performance-critical paths (`roles.perf-critical`) and any security-sensitive paths the path pattern misses. Fix code kinds where the default globs are wrong for this repository. Add guards from `language-recipes.md` for tools the repository already uses. Use thresholds the user gave you as they are; never tune a threshold so that today's code passes, because the baseline exists to hold today's problems. When the user named specific guards, do those. When they only gave a direction, show the proposed list with one line of reasoning per guard and let them confirm. Installing a new tool or dependency needs the user's consent unless they already gave it.

3. **Write the policy.** Run `guard.py init --root <repo> --write`, then edit `guards/policy.json`. It installs the runner into `tools/guard/` and refuses to overwrite an existing policy.

4. **Create the baselines.** Run `python3 tools/guard/guard.py update`. For a guard without a baseline, it scans the *base* commit with the current rules, so problems in uncommitted or unmerged work are reported instead of grandfathered. Until the setup is committed, `update` still exits 1 because every newly installed runner file is `protected` against the old base; the baselines are written regardless. If a hard rule already has violations (a committed `.only`, a secret, a failing test), stop and ask the user whether to fix them now (usually a test or config change, not business code) or to record exceptions.

5. **Wire it in.** Add `guard.py check` to the repository's existing lint or pre-commit entry point next to similar checks, and the CI job from `templates/` (`github-actions.yml` or `gitlab-ci.yml`). The CI job runs two steps: the normal check, and the trusted check, which runs with the base branch's runner, policy, baselines and detectors. A repository without CI gets the same two steps locally from `guard.py gate <branch> --merge`, run from a clean checkout of the target branch: it judges the merge result and merges only if both pass; a change to the guard configuration also needs `--approve-guard-changes`, given by the user after reading the diff. Tell the user that this replaces the required CI check only if every merge goes through it, and that CODEOWNERS entries only take effect on a hosting platform that enforces them. Add `templates/CODEOWNERS` entries for `guards/`, `tools/guard/` and the CI files. Write the agent instructions below into the repository's agent instruction file (`AGENTS.md`, `CLAUDE.md` or `CONTRIBUTING.md`); run `git check-ignore` on it first and pick a tracked file if it is ignored.

6. **Verify on the real repository.** Commit the setup on its own: it is the bootstrap change, which no earlier rules can judge, so it gets a human review as a whole (against the old base, every installed runner file is `protected`). Then `guard.py check --full --base HEAD` must exit 0, with the coverage numbers you expect (files, functions, tests) and no guard in `missing-tool` or `error`. In a temporary copy (`git worktree add` or `cp -R`, never the user's working tree), inject one violation per enabled guard and confirm that each one fails for the right reason. Then run `guard.py check --trusted --base <base branch>` in a clean clone where the guards are committed on the base branch, to prove the CI path works.

## Agent instructions for the repository

Adapt this block to the repository and put it in its agent instruction file:

```markdown
## Quality guards (guard-ratchet)

Run `python3 tools/guard/guard.py check` before reporting any change as done. Exit 0 is done;
exit 3 means some required guard or tier did not run (not done); exit 1 lists blocking problems.

- new / worse / lost / hard: fix the code or the test. If the user agrees the problem is
  acceptable, record it with `guard.py except add --guard G --rule R --key K --reason "..."
  --approved-by <user>` and say so in the report. Never invent an approval.
- stale / moved / unrecorded: run `python3 tools/guard/guard.py update` and commit the baselines.
- rule-change: run `guard.py update --rules-changed`; if it reports dropped entries, the rule
  change hides existing problems and needs the user's approval.
- locked / protected: you changed the policy, a baseline, the guard code or CI. Revert it unless
  the user asked for that change; then it needs an exception and a code-owner review.
- Never edit files under guards/ by hand, never weaken a test or a test configuration to get a
  pass, and never mark a guard optional or move it to a later tier to get a pass.
- Without CI, merge only through `python3 tools/guard/guard.py gate <branch> --merge`, run from the
  target branch; never with plain `git merge`. Never pass `--approve-guard-changes` yourself: that
  flag is the user's approval.
```

## Operating guards that already exist

When a check fails, read the category first; the next step for each is in `references/contract.md` and in the text report's "next steps". Improvement (`stale`) is recorded with `guard.py update`, which only ever tightens. New problems are fixed, or excepted only with the user's approval, because an exception is a decision about the product, not about the code. Advisory items (assertions removed, expectations rewritten next to implementation changes, destructive migrations, survived mutants, new dependencies) cannot be judged by a machine. Mention the relevant ones in your report with the evidence the runner printed, so a human can decide.

## Custom detectors

Write one only when no existing tool covers a problem the repository really has, such as an architecture rule specific to its layout, or N+1 queries through its own query layer. A detector prints one `guard-ratchet/detector@2` JSON document (`references/detector-contract.md`) and must fail closed: a scan that did not complete reports integrity problems, never zero findings. Base it on a real parser, not regular expressions over code structure. Prove it with fixture tests: positive, negative, boundary, key stability, parse failure, empty scan. The JavaScript examples show the patterns; their scan directories and entry points belong to the repository they came from.

## Report to the user

Lead with the verdict. Then give a table of the guards with command, tier, mode (which rules are hard) and baseline size, plus a few representative baseline entries, each judged as a real problem or a false positive. List the exceptions you created and why. Say what you changed outside the guard files to make hard rules pass, whether lint/CI passes as a whole, and which human steps remain (CODEOWNERS, branch protection, required checks). Use the trust model reference to say which protections are enforced only once those human steps are done.
