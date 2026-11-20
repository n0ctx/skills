# Pitfalls

Problems met in real deployments, with the symptom and the fix. Rules already stated in SKILL.md or the contracts are not repeated here.

## Baselines

**The base moved after the baselines were written.** Baselines derived from an old base report new or stale entries as soon as the change is rebased. Run `guard.py update` again after rebasing, then commit.

**A metric definition changed and the whole baseline was regenerated from the working tree.** Every regression since the last baseline gets accepted at once. Change definitions through the policy, so the fingerprint changes, then run `update --rules-changed`. It rebuilds from the base commit and stops on entries the new definition no longer sees.

**Guards went live, then nobody ran them.** After a few weeks every guard reports new and stale entries together, and nobody can tell which matter. Wire the check into the lint entry point and CI from the first day, and write the agent instructions into the repository's instruction file.

**A guard's command has no `{root}`.** The baseline cannot be derived from the base commit, so `update` refuses with an integrity problem. Make the tool scan `{root}`, or `cd {root}` first.

## Scope

**A scan silently covers less.** A path typo, a renamed directory or a broken glob drops half the files, and the findings shrink with them, which reads as an improvement. The runner fails a run more than 5% below the baseline's scan size, and fails an empty scan outright, but only for guards that report a scan size: detector JSON, lizard, JUnit, coverage and mutation reports, the built-ins, and SARIF tools that list their artifacts. Compiler-style text (tsc, mypy, gcc) and SARIF without artifacts say nothing about what they covered; an empty SARIF `runs` array or a run without `results` is still an integrity failure. For those tools, keep the scanned paths in the command (`.`/`{root}`, not a glob) so they cannot shrink unnoticed. The 5% tolerance applies per change, so a slow decline over many changes shows only in the history of the baselines' `scanned` field.

**Old reports from an incremental build.** A build tool that skips an up-to-date test task leaves the previous run's JUnit XML in place. Report files older than the run are ignored, and a run that wrote none is an integrity failure, so force the task to run (`gradle test --rerun-tasks`, a clean output directory) in the guard command.

**A new sub-project fails only in the trusted run.** Its own lint or type configuration is a rule change, which the trusted run does not apply until it reaches the base branch. Merge the configuration on its own first. Dependency and version edits in `pyproject.toml`, `package.json` and `Cargo.toml` are not rule changes; other edits to those files are.

**Files ignored by git but present locally.** Local and CI results differ, and a clean checkout reports stale entries. Built-in guards use `git ls-files` (tracked plus untracked-not-ignored), and tools should be pointed at the same set. The runner directory and the paths in `exclude` are never scanned.

**Tool output paths do not match repository paths.** A tool run with `cd {root}` reports relative paths; one run from the root against `{root}` reports absolute temporary paths. The adapters normalize both. A path outside the repository (an installed dependency) is dropped rather than keyed.

**Coverage reports that omit untested files.** coverage.py without `source=`/`--cov=`, Vitest without `--coverage.all`, c8 without `--all`. A changed file missing from the report is reported as `unmeasured` instead of passing.

**Walking parser comments or tokens as syntax nodes.** With espree `comment: true` or `tokens: true`, a generic walker enters `comments`/`tokens` and treats them as nodes. Skip `comments`, `tokens`, `loc`, `range` and `parent` in every walker, not only the shared one.

## Keys and metrics

**Line numbers or file-wide ordinals in keys.** One inserted line renumbers everything below it into new + stale pairs. Use `path#symbol`, `outer>call` for anonymous functions, and `~2` only for real same-name collisions.

**Definitions-per-file and length metrics that count inline callbacks.** Extracting small named functions or switching a loop to `map` inflates the number while the file gets shorter. Count only named functions and classes, and treat `describe`/`it` callbacks as containers, not functions. The default policy has no definitions metric at all.

**One threshold for every kind of code.** JSX views and table-driven tests hit length and branch limits that are meant for business logic. Classify the code (`paths`) instead of raising the logic limit for everyone.

## Dead code and reference graphs

**Convention-loaded files reported as dead.** Plugins loaded by directory, framework routes, tool config files and modules loaded by test helpers through string paths. Declare them as entry points, and check the list against the exports it names, so stale entries fail.

**A module loaded dynamically counts all its exports as used.** `const { a } = await load('x')` makes every export of `x` look used and hides real dead code. Count used exports from destructuring, member access and string subscripts; fall back to "all used" only when the module object escapes.

**Unresolved static imports dropped from the graph.** A typo in a literal import path silently removes an edge. Report it as unsupported input.

## Tests

**A test command that "looks" like it excludes a directory.** Shells and test runners expand globs differently. Run the runner on a small temporary directory and look at what it collected, or rely on the JUnit inventory, which shows exactly what ran.

**Replacing a fixed sleep with polling introduced a race.** Read the code under test and make sure the polled condition becomes true only after the side effect the assertion needs.

**A custom assertion helper reported as "no assertion".** Add the helper's name to the detector's assertion list; do not weaken the rule.

**A local rename with edits looks like a deletion.** Before a commit, git pairs an untracked file with a deleted one only when the content is identical. A plain `mv` followed by edits therefore shows up as a removed file plus a new one: baseline entries go `stale` and the new file's findings are `new`. Use `git mv`, or commit the rename on its own first, and run `guard.py update`.

**Renamed tests cost an exception.** The inventory cannot tell a rename from a deletion plus an addition. That is deliberate: silent deletion is the failure this guard exists for. Write one exception per renamed group (`--key 'tests/test_api.py::*'`) with the reason.

## N+1 and runtime shape

**Every export of a query directory treated as a query.** A pure helper in `db/` called in a loop is reported as N+1. A function counts as a query only with evidence: it uses the connection, calls `prepare`/`exec`/`transaction`, or calls another query function. Ordinary modules outside the query layer never inherit the effect.

**Batch writes in a transaction reported as N+1.** Reusing a prepared statement inside a transaction callback is the recommended batch pattern for synchronous drivers. Report reads in loops, not those writes.

**Only `prepare`/`execute` in the same file recognized.** That misses the real cases, where business code calls query-layer functions in a loop. Resolve calls through imports, and treat `map`/`filter`/comprehension callbacks as loop bodies, but not the loop header, which runs once.

## Security tools

**Registry rule packs fetched at run time.** Semgrep `--config p/…` downloads the current pack, so findings change without any code change. Vendor the pack at a fixed version.

**New advisories for unchanged dependencies.** osv-scanner results change when the database does, so a run on an unrelated change can fail. Run it with `when: ["deps"]` on changes and with `check --full` on a schedule, and handle scheduled findings as maintenance, not as regressions of whoever pushed next.

**Test fixtures with fake credentials.** The built-in skips obvious placeholders. For realistic-looking test keys, record an exception for that key, or generate the value at test time.
