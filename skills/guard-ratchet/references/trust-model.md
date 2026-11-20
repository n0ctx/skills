# Trust model

A guard that the agent it judges can edit is a convenience, not a gate. The runner, the policy, the baselines and the exceptions all sit in the same working tree as the code. Anything the agent can write, it can rewrite. This file states what each layer actually guarantees and what it needs from outside the repository.

## Layer 1: local runs (no extra setup)

Locally, `guard.py check` compares the working tree with the base commit. It makes loosening visible and blocking: a raised threshold, a removed guard, a hand-edited baseline, a changed detector, a test-config trick that drops tests from the inventory, a new suppression comment, a file that gained a generated-code header. An honest agent that runs the check gets a precise failure and the fix.

It cannot stop an agent that is willing to edit the guard itself. Such an agent can write an exception with any `approved_by`, edit the runner, or skip running the check. Every one of these edits shows up in the diff (`guards/exceptions.json`, `protected` files), so layer 1 turns a silent bypass into a visible one, but it does not prevent it.

Layer 1 also only sees what it can trace. It protects the scripts a guard command runs directly (`python3 {root}/tools/lint.py`, `./check.sh`, `python -m checks`), but not scripts reached through `npm run`, `make` or another file's import: list those in the guard's `config_files`, which makes any edit a `rule-change`. A baseline rewritten by hand together with a fingerprint matching the edited rules passes locally; only the trusted run, which restores baselines and configuration from base, catches it. The policy's `base` setting belongs to the change, so pass `--base` explicitly wherever the result matters. Report files read through `input` must be written during the run, which stops stale and committed reports, but not a process that touches the file just before the check.

## Layer 2: CI with the trusted run

The CI templates run two steps on every pull request:

1. `guard.py check` with the change's own files. This keeps baselines in sync and runs new guards.
2. `guard.py check --trusted --base <target>`, executed by the runner extracted from the base branch (`git archive`). Before running, it restores the policy, baselines, runner directory, detector directories and each guard's `config_files` from the base commit, and sets aside files the change added under those paths (a new nested lint config). External tools then read the base configuration from disk, while the built-in guards still judge the change's own content (a `pyproject.toml` restored for ruff is still checked for new dependencies). It keeps the change's `exceptions.json`, because exceptions are how an approved deviation travels with the change. `--base` is required, because the policy's own `base` setting is part of the change. The run rewrites files in the working tree and puts them back afterwards, so use it in CI or a clean clone.

The trusted run judges the change with the rules that were in force before it, so editing a detector, a threshold, a baseline, a lint config or the runner in the same change has no effect on the verdict. Improvements are not blocking there, since the base baseline is expected to be looser than the change's. The same holds for legitimate rule changes: a new package with its own `pyproject.toml` or `tsconfig.json` is judged with the configuration the base already has. Land such a configuration in its own change first (it passes, since it adds no code), then the code that relies on it.

This needs:

- **The required status check** on the protected branch, so the job has to pass before merge. Name the job and keep the name stable.
- **The base branch fetched** (`fetch-depth: 0`), or the runner cannot compute the merge-base and fails with exit 2.
- **Pinned tools**, installed by the workflow from versions written in the workflow itself or taken from the base branch, not from files the change can edit. Tools installed from the change's own lockfile (`npx eslint`, test runners, lint plugins) can be swapped by the change; the lockfile change itself is reported by the `deps` guard and raises the tier to strict, but a reviewer has to look at it. A tool version that differs from the baseline's is a `rule-change` failure, which is intended.
- **No `pull_request_target`**. The job executes the change's code (its tests), so it must run with the change's permissions (`pull_request`, `contents: read`, no secrets).

## Without CI: the local merge gate

`guard.py gate <branch> [--into <target>] [--merge]` does on the developer's machine what the CI template does, and judges the result that would actually land:

1. It merges the branch into the target's tip in a scratch worktree. A conflict stops the gate.
2. It runs that merge commit's own `check` in a fresh worktree.
3. Only then does it extract the target's runner, blob by blob from the target's tree, and run it as `check --trusted --base <target>` on another fresh worktree of the merge. The change is judged by the policy, baselines, detectors and tool configuration of the target's tip.
4. With `--merge`, it fast-forwards the checked-out target to exactly that merge commit, provided both checks exit 0 and the target did not move meanwhile.

After each step the gate checks that the worktree is still a clean checkout of the merge, that the step's exit code agrees with the report it wrote, and, after the trusted step, that the extracted runner still holds the target's bytes. Any mismatch, a crash or a killed step is an error, never a pass. Repository hooks never run, in the gate or in any git command the runner issues, because with a tracked hooks path they are the change's own code; that includes your own hooks, such as a `post-merge` that installs dependencies.

The gate refuses to run unless the runner executing it is exactly the target's committed runner, with the same files and the same content as git stores them. Start it from a clean checkout of the target branch. A change to the policy, the exceptions, protected files (runner, detectors, code owners, CI files) or hook files fails the gate (exit 1) unless `--approve-guard-changes` is given, with or without `--merge`. This is the local stand-in for code-owner review: look at the diff the gate prints first, because an exception the branch wrote itself is honored by the trusted step, as in CI. The flag is only as good as the person who passes it; an agent with a shell can pass it too.

Two things stay outside the gate. First, it judges what goes through it: anyone who can run `git merge` directly, including an agent with a shell, can skip it. It fits a workflow where agents work on branches and a person merges. Second, the branch's tests and detectors run as the current user, exactly as in a CI job. Dependency folders (`.venv`, `node_modules`) are linked in from the main checkout, so that code can also write there, and a background process it leaves behind can change files and put them back between the gate's checks. The gate stops a branch from rewriting the rules that judge it, and it notices tampering that leaves traces. It does not contain code that is malicious; judge untrusted branches inside a container or VM. The gate needs a POSIX system (macOS, Linux, WSL).

## Layer 3: code owners and review

The trusted run still trusts two things the change can touch: the exceptions file, and the workflow file that runs it.

- `guards/exceptions.json`, `guards/`, `tools/guard/` and the CI configuration must be owned in `CODEOWNERS` by people who are not the agent, with "require review from code owners" enabled. Only then is an exception an approval, and a change to the workflow cannot slip in.
- Where the platform supports it, require the guard workflow through a branch ruleset that pins it to the default branch. A change that rewrites the job then cannot replace the check that judges it.

A change that introduces the guards for the first time has no base policy; `--trusted` refuses it (exit 2) and it needs a human review of the whole setup.

## What is enforced where

| Protection | Local check | Trusted CI | Needs CODEOWNERS / branch protection |
|---|---|---|---|
| New or worse findings, lost tests, failing tests, secrets, edited migrations | blocks | blocks | |
| Raised thresholds, removed guards, narrowed scope, hand-edited baselines | blocks | rules from base: change ignored | |
| Detector, runner or tool-config edits that hide findings | flags directly run scripts as `protected` and listed `config_files` as `rule-change`; misses scripts reached through `npm run`/`make` unless listed | base detectors and configs: hidden findings reappear | |
| Code moved into a laxer kind (generated header, `vendor/`, `scripts/`, tests) | blocks as `locked` | blocks | |
| Stale or committed report files standing in for a run | blocks (`integrity`) | blocks | |
| Self-approved exception | visible in diff | honored | reviewed by owners |
| Workflow edited to skip the guard | flags as `protected` | can be bypassed by the edited workflow | owners review; ruleset-pinned workflow |
| Agent never runs the check | — | required status check | branch protection |
| Without CI: branch merged without being judged | `guard.py gate --merge` judges the merge result like the trusted run | — | a person merges through the gate, approving guard changes |

## Reporting the boundary

When you set guards up, tell the user which layers are in place. Until the code-owner rule and the required check are configured, the honest statement is: "the guards block honest mistakes and make bypasses visible; they do not yet prevent a determined bypass."
