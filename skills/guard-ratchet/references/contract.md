# Runner contract

What `guard.py` decides and why. The executable specification of the ratchet comparison is `conformance/cases.json` (run `guard.py conformance`); the runner's behavior around it is covered by `scripts/tests/`.

## Items and modes

A guard produces items `{rule, key, count}` plus integrity problems. `key` identifies the affected entity stably (`path#symbol`, a content hash, a test id, a module pair), never a line number. Each item has a mode, which decides how it is judged:

| Mode | Meaning | Typical use |
|---|---|---|
| `hard` | Fails whenever present; never baselined | committed `.only`, secrets, failing tests, edited migrations, cycles when there are none today |
| `ratchet` | Lower is better. Existing entries are baselined; new = fail, higher = fail, lower = baseline must be tightened | lint/type/security findings per file, complexity above the limit, dead code, duplication |
| `budget` | Lower is better with tolerated growth: fails only when growth exceeds every configured limit (`pct` and `abs`); growth within the budget is never written back, so it cannot accumulate | function length, file size, bundle size, benchmark time |
| `keep` | Presence is required. A missing entry is `lost`; a new entry is recorded by `update` | test inventory (`present`, `active`), public API snapshot (`surface`) |
| `advisory` | Reported, never fails | near-threshold warnings, evidence a machine cannot judge |
| `off` | Ignored | a metric a project does not want |

Metric values from detectors (`fn-complexity`, `fn-length`, `file-size`, `fan-out`, or any custom metric) become items only above the threshold for the file's code kind and language (`references/policy.md`). The threshold's mode becomes the item's mode. A guard's `modes` map can override the mode per rule, for example making `cycle` hard.

## Categories

Every judged problem has one category. Blocking categories fail the run unless an exception covers them. Integrity problems, stale baselines, moves, unrecorded entries and rule changes cannot be excepted, because each has a safe mechanical fix.

| Category | Blocking | Exceptable | Next step |
|---|---|---|---|
| `integrity` | yes | no | The scan did not complete (tool crash, unexpected exit code, unparseable output, parse failure, `scanned < planned`, unresolved deterministic input, empty scan, missing or stale report, failing version command). Fix the tool or configuration. |
| `hard` | yes | yes | Fix it. |
| `new` | yes | yes | Fix it, or an approved exception. |
| `worse` | yes | yes (`max` caps it) | Bring it back to the baseline, or an approved exception. |
| `lost` | yes | yes | A recorded test or API entry is gone or skipped. Restore it, or an approved exception (after which `update` drops it). |
| `stale` | yes | no | Improvement not recorded: `guard.py update`. |
| `moved` | yes | no | Baseline key points at a renamed file or moved symbol: `guard.py update`. |
| `unrecorded` | for `strict_sync` guards (snapshots) | no | `guard.py update`. For the test inventory it is advisory. |
| `scope` | yes | yes (rule `scope`, key `scanned`) | The scan covers more than `scope_tolerance` (default 5%) less than when the baseline was written. |
| `rule-change` | yes | no | The rule fingerprint or tool version changed: `guard.py update --rules-changed`. |
| `locked` | yes | yes | The change loosens the policy or a baseline relative to base. |
| `protected` | yes | yes | Guard code, detector code, CI configuration or CODEOWNERS changed. |
| `exception` | yes | no | An exception entry is malformed or expired. |
| `advisory`, `slack`, `within-budget`, `improved`, `excepted` | no | | Information. |

## Baselines

`guards/baselines/<guard>.json`, written only by `guard.py update`:

```json
{"version": 2, "guard": "complexity", "fingerprint": "sha256:…", "tool": "1.26.1", "scanned": 412,
 "modes": {"fn-length": "budget"}, "entries": {"fn-complexity": {"src/a.py#parse": 41}}}
```

- `fingerprint` hashes everything besides the code that changes what a guard reports: the guard definition (minus `name`, `tier`, `when`, `required`, `requires`, `timeout`, `note`), the thresholds of the metrics it can report, the code-kind globs and excludes, and the content of the guard's `config_files`. `tool` is the tool version. When either differs at check time, the run fails with `rule-change` instead of comparing, because the difference could come from the rules rather than from the code.
- `scanned` is the scan size at update time and drives the `scope` check.
- Version 1 baselines (`{version: 1, guard, entries}`) are read as ratchet entries without a fingerprint; the next `update` upgrades them.

## What `update` may write

`update` is safe to run at any time, because it never writes a change that hides a regression:

- ratchet and lower-is-better budget entries are lowered or dropped, never raised or added;
- higher-is-better budgets are raised with improvements, never lowered;
- keep entries are added; a lost keep entry is dropped only when an exception covers it;
- keys are rewritten for renamed files (git rename detection, plus exact-content matching for uncommitted renames) and for a symbol that moved to another file without getting worse (one-to-one only: a split or a copy stays new + stale);
- `scanned` is lowered only within `scope_tolerance` or under a `scope` exception.

New problems never enter a baseline through `update`; they pass only through exceptions.

A guard without a baseline, or `update --rules-changed`, derives the baseline by scanning the base commit with the current rules in a temporary worktree. `node_modules`/`.venv` are linked in and the guard's `config_files` are copied in, so tools that read configuration from the scanned tree apply the current rules. Entries the old baseline had but the new rules no longer see on the same base code mean the detection was loosened; each needs an exception with rule `rule-change` (key `*` covers a whole tool upgrade), otherwise nothing is written. Commands must use `{root}` for this to work.

## Locks against base

`check` compares the change with the base commit (merge-base of the base ref and HEAD, against the working tree):

- **Policy lock**: any change to the effective policy that could make problems go unreported is `locked` (guard `policy`, rule `loosen`, key = the policy path, such as `thresholds.fn-complexity.limit.logic`). This covers a raised or disabled threshold, a weakened mode (including a new per-rule `modes` entry other than `hard`, since the rule's previous mode may have come from the detector), a coverage `min`, `min_score` or `untested_lines` looser than the value in force (an explicit setting or the built-in default), a wider growth budget, a removed guard, a later tier, a narrower `when`, a guard made optional, any change to a guard's command or options, more files classified as a laxer kind, new excludes, extensions removed from `languages`, fewer protected paths, fewer strict roles, a higher strict-tier threshold, a wider scope tolerance, or a changed base or runner path. Tightening is free.
- **Baseline lock**: baseline entries added or raised by hand, keep entries removed, a lowered `scanned`, a deleted baseline or removed fingerprint are `locked` under the guard's own name, rule and key, so the exception that would cover the finding also covers the lock. A baseline whose fingerprint changed is left to the trusted run.
- **Protected files**: changes to the runner directory, CI configuration, CODEOWNERS and the in-repo code a guard command runs are `protected`. That code is the program or interpreter script (`tools/x.py`, `{root}/x.py`, `./x.sh`, also inside `bash -c "…"`), a `python -m` module, and the value of a `--config`/`--rules` option; a script in a tooling directory (`tools/`, `scripts/`, `bin/`) protects its whole directory. Paths count when they exist in the working tree or at base, so deleting a detector does not unprotect it. Scan targets and data files a command only reads are not protected.
- **Reclassification**: logic, model or UI code that leaves those kinds is `locked` (rule `reclassified`): a file that gains a generated-code header, a rename into `vendor/`, `scripts/`, a test path or a migration path, and a new file marked generated only by its header. One exception with a directory prefix approves a generator's output (`--guard policy --rule reclassified --key 'src/api/*'`). A move between logic, model and UI (`Button.js` to `Button.jsx`) only changes the limits and is advisory; so is a new file under a vendor path.

`check --trusted` needs an explicit `--base`. It restores the policy, baselines, runner, detector directories and tool config files from base before running and sets aside files the change added there (built-in guards still read the change's version of all of them), keeps the change's `exceptions.json`, and treats improvements as non-blocking. See `trust-model.md`.

## Exceptions

`guards/exceptions.json`, edited with `guard.py except add`:

```json
{"version": 1, "exceptions": [
  {"guard": "complexity", "rule": "fn-complexity", "key": "src/proto/table.py#decode", "max": 48,
   "reason": "protocol dispatch table; splitting it hides the mapping", "approved_by": "alice",
   "expires": "2027-03-31"}
]}
```

`guard`, `rule`, `key`, `reason` (10+ characters) and `approved_by` are required. `rule` and `key` accept `*` only as a wildcard, so test ids containing brackets match literally. A key must start with a literal prefix (`src/legacy/*`, `tests/test_api.py::*`): `*`, `**` or `*.py` would switch a rule off. The only exception is the bare `*` for rule `rule-change`, which covers one tool upgrade; exceptions for guard `policy` must name the exact setting, except rule `reclassified`, which like `protected` takes a file or a directory prefix (`tools/guard/*` approves a runner upgrade in one entry). `max` caps the tolerated count. An expired or malformed entry is itself a blocking problem. An entry that matched nothing in a run is reported as advisory. Exceptions are audit records, not authorization: `approved_by` becomes an approval only when the file is behind code-owner review (`trust-model.md`).

## Selection and tiers

The risk tier is computed from the change: `fast` when only `risk.fast_roles` (docs) changed; `strict` when a file has a strict role (security, migration, schema, public-api, deps, ci, build, infra, guard, test-config, perf-critical), when the change exceeds `strict_changed_lines` or `strict_changed_files`, or when test files were deleted, assertions removed, or expectations rewritten next to implementation changes; otherwise `standard`. A guard runs when its `tier` is at or below the run's tier and, if it has `when`, one of those roles changed. Code kinds count as roles too, so `when: ["ui"]` runs a visual regression suite only for UI changes. `--full` (and `update`) runs everything. `--tier` lower than the computed tier makes the run `incomplete`.

## CLI

```
guard.py check  [--base REF|none] [--tier fast|standard|strict] [--full] [--only a,b] [--trusted]
                [--format text|json|markdown] [--output FILE] [--root DIR]
guard.py update [--rules-changed] [same selection flags]
guard.py gate BRANCH [--into TARGET] [--merge] [--approve-guard-changes] [--format text|json] [--root DIR]
guard.py risk | init [--write] [--force] | except add … | pyapi DIR… | conformance [cases.json]
```

Exit codes: `0` pass, `1` blocking problems, `2` usage or configuration error (unknown policy field, unresolvable base, invalid exceptions file, `--only` naming an unknown guard, `--trusted` without `--base`), `3` incomplete: nothing failed, but a required guard's tool is missing or the requested tier is below the required one. Exit 3 is never a pass. `gate` returns the worst exit code of its two steps (2, then 1, then 3; any other code, such as a killed step, is 2). A step whose report disagrees with its exit code, whose worktree changed, or whose extracted runner was modified is 2 as well. The gate returns 1 for a guard-configuration or hook change without `--approve-guard-changes`, whether or not `--merge` was given, and 130 when interrupted. Under `--format json` every outcome, errors included, is one `guard-ratchet/gate@1` object: `branch`, `commit`, `target`, `target_commit`, `merge_commit` (the judged trial merge), `exit_code`, `merged`, `guard_changes`, `note`, `issues` (what made a step an error), `error`, and `steps` with each step's `name`, `exit_code` and JSON report.

Command placeholders, in every command including those of built-in guards: `{root}` (scanned tree, which is a temporary base worktree during baseline derivation), `{out}` (report file the tool writes), `{tmp}` (per-run directory shared by guards, e.g. a coverage report written by the tests guard and read by `diff-coverage`), `{base}` (base commit sha). Commands run with the repository root as working directory.

## Report

`--format json` prints `guard-ratchet/report@1`:

```json
{"schema": "guard-ratchet/report@1", "verdict": "fail", "exit_code": 1, "base": "…", "tier": "strict",
 "risk": {"tier": "strict", "reasons": ["security: src/auth/session.ts"], "changed_files": 4, "changed_lines": 120, "roles": {}},
 "incomplete": [], "summary": {"blocking": 2, "by_category": {"new": 1, "lost": 1}, "guards": {"tests": "fail"}},
 "guards": [{"name": "tests", "status": "fail", "coverage": {"scanned": 212, "unit": "tests"}, "baseline_entries": 424,
             "problems": [{"category": "lost", "guard": "tests", "rule": "present", "key": "tests.test_api::test_refund",
                           "message": "test removed: tests.test_api::test_refund", "blocking": true, "exceptable": true}]}],
 "problems": [], "exceptions": []}
```

Guard `status` is one of `pass`, `fail`, `error` (integrity), `missing-tool` and `skipped` (with `reason`). `--format markdown` is meant for a CI step summary.
