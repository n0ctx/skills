# Changelog

## 2.1.0

- **Local merge gate** for repositories without CI: `guard.py gate <branch> --merge` merges the branch into the target's tip in a scratch worktree, runs that merge commit's own check and then the target's runner in trusted mode (each in a fresh worktree), and fast-forwards the target to exactly the judged merge only if both pass. After each step it verifies the worktree, the step's report against its exit code, and the extracted runner's bytes. Guard-configuration and hook changes need `--approve-guard-changes`, hooks never run, and the gate refuses to run from a runner that differs from the target's committed one.
- The runner no longer runs repository hooks in its own git commands, and looks in its own directory last when importing, so a stray module next to it cannot shadow the standard library.

## 2.0.0

The skill now installs a runner that owns every baseline and protects its own configuration, instead of a comparison script that each detector piped into.

- **Runner** (`scripts/guard.py`, Python 3.10+, stdlib only) replaces `scripts/ratchet.py`. It selects guards by change risk, runs tools, normalizes their output through format adapters (SARIF, ESLint JSON, JUnit, lizard, tsc, mypy, gcc-style, regex, snapshot lines, metric numbers, exit status, detector JSON v1/v2), judges metrics against per-kind thresholds, applies exceptions and reports in text, JSON or Markdown with exit codes 0/1/2/3.
- **Adaptive thresholds**: code kinds (logic, ui, model, test, script, migration, generated, vendor) and per-language limits; budget mode for length and size so legacy code can take fixes without creeping; no definitions-per-file metric.
- **Ratchet hardening**: rule fingerprints and tool versions in baselines, with rebuilds from the base commit when rules change and approved exceptions for findings the new rules drop. Also: scope floors, rename and move handling that cannot hide splits, a policy lock and a baseline lock against base, protected detector scripts, detection of code moved into a laxer kind (generated header, vendor, scripts, tests), and report files that must be written during the run. A run whose guard lacked a capability for part of its input (TOML parsing on Python 3.10) is incomplete, not a pass. Trusted CI runs (`--trusted --base`) judge the change with the base branch's runner, policy, baselines, detectors and tool configuration. `update` never adds a regression.
- **Any language**: 60+ extensions are source code out of the box, and the policy's `languages` map adds more. Diff parsing does not depend on the user's git configuration or on unusual file names.
- **New built-in guards**: secrets, suppressions, test changes, dependencies (npm, PyPI, Go, Cargo, RubyGems, Composer), migrations, file size, diff coverage (LCOV, Cobertura, JaCoCo, Go), mutation score (mutation-testing-elements), API snapshots (`pyapi` producer), metric budgets, generated-code drift.
- **Test inventory** from JUnit: removed, newly skipped and failing tests, and shrinking collection.
- **Bundled Semgrep rules** for injection, SQL built from strings, unsafe deserialization, disabled TLS verification, eval, unbounded retries, swallowed exceptions, missing timeouts and blocking calls in async code, with rule tests.
- **`init`** profiles a repository and proposes a policy (tool configuration globs at any depth); `except add` writes validated exceptions; CI and CODEOWNERS templates; a trust model reference.
- **JavaScript detectors** print `guard-ratchet/detector@2` with raw metrics; their local baseline logic is removed, `api-surface.mjs` is added, and `fit`/`fdescribe` are now detected.
- The skill is English-only; the Chinese README was removed.

## 1.0.0

Baseline ratchet (`scripts/ratchet.py`), conformance cases, detector contract, guard catalog and JavaScript reference detectors.
