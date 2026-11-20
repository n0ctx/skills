# Guard catalog

What each guard prevents, how it decides, and where its judgement stops. Choose guards for problems the repository can actually have: no migrations guard without a database, no cycle guard in Go (the compiler already forbids package cycles). The policy entries are in `language-recipes.md`; field semantics are in `policy.md`.

Each guard sorts what it sees into one of three outcomes:

- **Blocks**: reliable enough to fail a run (hard, or new/worse/lost against a baseline).
- **Reports**: real risk, but context decides; printed as advisory evidence and, where noted, raises the verification tier.
- **Human**: cannot be judged by a machine at all; the guard only makes sure a reviewer sees it.

## Summary

| Guard | Blocks | Reports | Cost |
|---|---|---|---|
| `secrets` (built-in) | prefixed tokens and private keys in added lines; committed `.env`, key and credential files | URLs with embedded passwords | instant |
| gitleaks / trufflehog | new findings per file (entropy and 150+ rules) | | seconds |
| `suppressions` (built-in) | more lint/type/coverage/security suppressions or skipped tests in a file; any focused test | | instant |
| `test-changes` (built-in) | deleted test files, test files moved out of the test paths | assertions removed and expectations rewritten next to implementation changes (both also raise the tier), sizable source change without test change | instant |
| test inventory (`junit`) | failing tests, removed tests, newly skipped tests, collection shrinking by more than 5% | new tests (recorded by update) | the test suite |
| `diff-coverage` (built-in) | changed lines of a kind below its minimum; changed files missing from the report | uncovered line ranges | the test suite |
| `mutation` (built-in) | mutation score on changed lines below `min_score` | each survived mutant | high: strict tier |
| complexity / length (lizard, detectors) | functions above the kind's limit (ratchet); length growth beyond budget | near-limit functions | seconds |
| `size` (built-in) | files above the kind's limit growing beyond budget; new oversized files | | instant |
| lint / types (ruff, ESLint, tsc, mypy, golangci-lint, clippy, ...) | new findings per file and rule | tool `note` levels | seconds |
| Semgrep (bundled + chosen packs) | new findings per file and rule | | seconds |
| `deps` (built-in) | git/URL/path dependencies, `*`/`latest` versions, new package indexes, off-registry lockfile hosts, manifest changed without lockfile | new dependencies, aliases, open ranges, install scripts | instant |
| osv-scanner / audit tools | new known vulnerabilities in lockfiles | | network, when deps change |
| zizmor / actionlint | new workflow findings (injection, `pull_request_target`, permissions, unpinned actions) | | seconds |
| `migrations` (built-in) | edits, renames, deletions of migrations already on base | destructive operations in new migrations | instant |
| API snapshot (`snapshot`) | removed or changed public symbols | | seconds |
| contract tools (oasdiff, buf, graphql-inspector, cargo-semver-checks, ...) | breaking changes against base | | seconds |
| `generated` (built-in) | committed generated files that differ from the generator's output | | the generator |
| build / typecheck (`exit`) | the command failing | | the build |
| `metric` (built-in) | a number (bundle size, benchmark) growing beyond budget | | depends |
| architecture, cycles, dead code, duplication, N+1 (detectors) | new findings (or any, when hard) | | seconds |
| Policy / baseline locks, protected files (always on) | loosening relative to base | new policy (initial setup) | instant |

## Code quality metrics

**Complexity** (`fn-complexity`). Prevents functions from growing one branch at a time. Lizard measures it for about 30 languages; the JavaScript reference detector adds a private single-caller helper's decisions back to its caller, so moving branches into a helper does not lower the score. Limits depend on kind and language (`policy.md`): ratchet mode, so a legacy function over the limit may not get any more complex. When it fails, the useful advice is to move the *new* responsibility out of the function this change mixed it into. Splitting a function into steps only to lower the number does not help: the moved part is reported as new if it is still over the limit, and the add-back cancels helper extraction. Dispatch tables and protocol mappings are inherently complex: keep them in the baseline, or record an exception with the reason.

**Length and size** (`fn-length`, `file-size`). These limit how much a reader has to hold in their head. They are a weaker signal than complexity, so both use budget mode: a 300-line legacy function can absorb a bug fix but cannot creep, because growth is always measured against the recorded value, never against the last run. Tests, models, migrations and generated code are exempt by kind. "Definitions per file" and "imports per file" are deliberately not offered: both reward meaningless splitting.

**Duplication.** Prevents copy-paste. Fingerprint normalized statement token sequences with identifiers stripped (jscpd, PMD CPD, or the JS detector); the count is the number of occurrences. Plain call sequences (setters, route registrations) must match verbatim, or every list of different setters would look copied. Tests and generated code are excluded. Code that must stay identical in two places (a client and server copy of one algorithm) gets a `guard-allow(duplication)` marker on one side.

**Dead code.** Unreferenced files and exports, from an in-repo reference graph (knip, vulture, `deadcode`, staticcheck U1000, or the JS detector). Declare entry points and loading conventions explicitly (routes by filename, plugins by directory, config files loaded by tools, strings loaded by test helpers), and check the declarations against reality, or the baseline fills with false positives that hide real dead code. Calls through variables cannot be resolved; leave those in the baseline and say so in the report.

**Cycles and architecture.** Load-time import cycles (hard when there are none today) and forbidden dependencies between layers or modules (dependency-cruiser, import-linter, ArchUnit, or the JS detector). Write rules only for boundaries the repository actually has. An unclassified-module check catches new top-level directories created to escape a boundary.

## Test integrity

The risk with an agent writing code is that it also writes the checks that verify it. The guards below compare tests with the base commit instead of trusting the current test run alone.

- **Inventory** (`junit` parser). Every test id the runner reports is recorded twice: once as present, and once as active (not skipped). A removed test is `lost: present`, a newly skipped one is `lost: active`, and a failing one is `hard`. Collection shrinking by more than 5% (a changed glob, a moved directory) is `scope`. Removing a test legitimately needs an exception naming it, after which `update` drops it. Renaming a test is a removal plus an addition. That costs an exception, and it is the price of making silent test deletion impossible. Parametrized cases are separate tests. Nearly every runner can write JUnit: pytest `--junitxml`, vitest/jest/mocha reporters, `node --test --test-reporter=junit`, gotestsum, cargo-nextest, Gradle/Maven Surefire, dotnet `--logger junit`, PHPUnit, RSpec.
- **Test changes** (built-in, diff only). Deleting a test file blocks. Fewer assertion lines in a test file, and an expected literal changed while implementation files changed in the same diff, are reported with the old and new lines. Both raise the tier to strict, which pulls in diff coverage and mutation testing where they are configured. They do not block, because refactoring tests legitimately does both. A machine cannot tell whether a new expectation is the requirement or the bug.
- **Diff coverage** (built-in). Of the changed executable lines of each kind, the covered share must reach `min` (default logic 80%). A changed file absent from the report fails, because an uninstrumented file reads as 100% covered otherwise; configure the tool to include all sources (`--cov=src` / `source=`, `--coverage.all`, `--all`). Total coverage is not ratcheted by default: it drops when well-tested code is deleted, which is not a regression. Add it as a higher-is-better `metric` if the team wants it.
- **Mutation** (built-in, strict tier). Reads the mutation-testing-elements JSON (Stryker for JS/TS/.NET/Scala, PIT with its report plugin, others that export it) and scores only mutants on changed lines. A survived mutant on a changed line means no test notices when that line's logic changes. Restrict the tool to changed files (Stryker `--mutate`, cargo-mutants `--in-diff`) to keep it affordable.
- **Shape** (JS detector, or the language's test lint rules): tests without assertions, tautological assertions (`assert True`, `expect(1).toBe(1)`), long fixed sleeps outside end-to-end tests, browser dependencies outside the e2e directory, repeated expensive setup per file.
- **Suppressions** (built-in). `.only`/`fit` in a test file always blocks. Skips (`.skip`, `xit`, `@pytest.mark.skip`, `t.Skip`, `#[ignore]`, `@Disabled`, ...) are counted per test file and ratcheted.

## Bypass resistance

- **Suppressions** count inline suppressions per file and family: lint (`eslint-disable`, `# noqa`, `//nolint`, `#[allow(`, `@SuppressWarnings`, `rubocop:disable`, ...), type (`@ts-ignore`, `# type: ignore`, ...), coverage (`istanbul ignore`, `pragma: no cover`, ...), security (`nosec`, `nosemgrep`, `gitleaks:allow`, `NOSONAR`, ...) and `guard-allow`. A suppression is the cheapest way to make a failing check pass, so each new one is a new finding.
- **Locks and protected files** are always on (`contract.md`). Tool configuration belongs in a guard's `config_files`, so disabling a rule in `ruff.toml` is a rule change whose dropped findings need an exception, not an improvement.
- **Generated headers**: a file that gains `DO NOT EDIT` exempts itself from source guards, so the change is locked.

## Security and supply chain

- **Secrets**: the built-in scans only added lines, for formats that are unambiguous (private key blocks; AWS, GitHub, GitLab, Slack, Stripe live, Google, OpenAI, Anthropic, npm, PyPI, SendGrid tokens), and blocks committed credential files. Values that look like placeholders (`EXAMPLE`, `xxxx`, `${...}`) are skipped. Messages show four characters and a length, never the secret. gitleaks adds entropy-based and provider rules for the whole tree as a ratchet. A leaked secret must be rotated, whatever the guard says.
- **SAST**: Semgrep with the bundled rules (`rules/semgrep/`: command injection, SQL built from strings, unsafe deserialization, disabled TLS verification, `eval`, unbounded retry loops, swallowed exceptions, requests without timeouts, blocking calls in async code) plus registry packs vendored at a pinned version. Language tools add depth: bandit or ruff `S`, gosec, eslint-plugin-security, brakeman, SpotBugs/find-sec-bugs. Findings ratchet per file and rule; keep severities the tool marks low-confidence advisory through `advisory_levels` or `modes`.
- **Dependencies** (built-in `deps`) checks what a change does to manifests and lockfiles, for npm, PyPI (requirements, PEP 621, Poetry, uv), Go, Cargo, RubyGems and Composer; other ecosystems are listed as not analyzed. Known vulnerabilities need a database: run osv-scanner (all major lockfiles) when `deps` changes, and on a schedule with `check --full` to catch advisories published for unchanged dependencies. Lockfile consistency is best proven by the ecosystem itself, as an `exit` guard: `npm ci --ignore-scripts --dry-run` and `go mod tidy -diff` (Go 1.23+) fail on a mismatch (verified); `uv lock --check`, `poetry check --lock`, `cargo metadata --locked --format-version 1`, Bundler in frozen mode and `composer validate --strict` do the same according to their documentation. Typosquatting and package reputation need registry data, and the built-in does not guess: new dependencies are listed for review, and services like OpenSSF Scorecard or Socket can be added if the team uses them.
- **CI and automation**: zizmor (GitHub Actions: template injection, `pull_request_target` with checkout, excessive permissions, unpinned actions, credential persistence) or actionlint. For other platforms, protect the files and review them. Infrastructure files: checkov, tfsec/trivy config, kube-linter as SARIF guards when the repository has them.
- **Security-sensitive changes** (auth, sessions, crypto, permissions, CORS/CSRF: `security_pattern` plus `roles.security`) raise the tier to strict. Whether an authorization change is correct is a **human** question. The guards ensure it runs the full suite and appears in the risk reasons.

## Build, interfaces and regressions

- **Build and types** as `exit` guards when they pass today, or as ratchets when there is a backlog (`tsc`, `mypy` parsers, or SARIF/gcc-style output): `tsc --noEmit`, `mypy`, `pyright`, `go build ./...`/`go vet`, `cargo check --locked`, `dotnet build -warnaserror`, `gradle compileJava`.
- **Public API**: the `snapshot` builtin stores one line per public symbol and treats a removed or changed line as `lost`. Additions must be recorded by `update`, so the snapshot always matches the code (`strict_sync`). Producers: `guard.py pyapi <pkg>` (Python), `examples/javascript/api-surface.mjs` (JS), API Extractor reports (TS), `cargo public-api`, `go doc -all`/apidiff, `javap` over the public jar. For semantic diffs prefer the ecosystem's checker as an `exit` guard against `{base}`: cargo-semver-checks, gorelease/apidiff, japicmp/revapi, griffe check.
- **Schemas and contracts**: oasdiff (`breaking`), `buf breaking --against .git#ref={base}`, graphql-inspector, avro/JSON Schema compatibility tools, run when the `schema` role changes. A snapshot of a schema dump (`sqlite3 db .schema`, `pg_dump --schema-only`) works as a generic fallback.
- **Database migrations**: the built-in blocks edits to merged migrations and reports destructive statements (drops, truncates, renames, type changes, `NOT NULL` without default, `DELETE` without `WHERE`) for review. Framework checks catch model changes without a migration: `manage.py makemigrations --check --dry-run`, `alembic check`, `prisma migrate diff --exit-code`, `rails db:migrate:status`. Squawk lints PostgreSQL locking problems.
- **Generated code**: the built-in runs the generator and fails when committed outputs differ. It leaves the regenerated files in the working tree, because they are the fix.
- **Smoke and integration tests**: an `exit` or `junit` guard with `tier: strict` or `when` (for example `when: ["public-api", "schema"]`). **Visual regression** for UI changes: Playwright `toHaveScreenshot`, Storybook test runners or Chromatic as a `junit`/`exit` guard with `when: ["ui"]`; the snapshots live in the repository and are protected by review.

## Runtime stability and performance

Static signals with low false-positive rates ratchet per file. Everything that depends on context is reported, or covered by a targeted test, not failed.

| Risk | Detected by | Mode |
|---|---|---|
| Swallowed exceptions | bundled Semgrep `gr.*.empty-catch` / `swallowed-exception`, ruff `S110`/`BLE001`, ESLint `no-empty`, errcheck | ratchet |
| Unbounded retry loops | bundled Semgrep `gr.*.unbounded-retry` (medium confidence: intentional daemon loops look the same) | ratchet; downgrade with `modes` if noisy |
| External calls without timeouts | bundled Semgrep `fetch-without-timeout` / `requests-without-timeout`, ruff `S113`, Go `noctx`, `bodyclose` | ratchet |
| Resource leaks | ruff `SIM115`, pylint `R1732`, Go `bodyclose`/`sqlclosecheck`, SpotBugs `OBL`, clippy | ratchet |
| Blocking calls in async code | bundled Semgrep `blocking-sleep-in-async` / `sync-io-in-async`, ruff `ASYNC`, typescript-eslint `no-floating-promises`, `no-misused-promises` | ratchet |
| N+1 queries | JS perf-shape detector (effects propagated through the query layer), Django `nplusone`/`django-zeal` in tests, Bullet (Rails) in tests | ratchet / test failure |
| Concurrency hazards | `go vet` (copylocks), `go test -race` as an `exit` guard, ESLint `require-atomic-updates`, ThreadSanitizer builds | blocks when the tool is exact |
| Performance regressions | `metric` guard with a budget: bundle size (size-limit, `du -b dist`), benchmark medians (`repeat: 5`), query counts from a test; `when: ["perf-critical"]` | budget |

Benchmarks are noisy: use the median of several runs, a generous budget, and the `perf-critical` role to run them only where they matter. A failing benchmark budget should be rare and meaningful, or it will be excepted by reflex.

## Not offered as guards

- Naming style, "one word per concept", derivable state: these need semantic judgement and produce noise.
- `await` inside loops: often intentional sequencing; the cost of review exceeds the benefit.
- Same-name exports across files: normal in layered code.
- Ratcheting total test count or total coverage: legitimate refactoring lowers both. The inventory and diff coverage measure what actually matters.
- Whether a business rule, an authorization decision or a new test expectation is *correct*. No static signal decides it. The guards make sure such changes are marked strict, fully tested, and listed in the report for a human.
