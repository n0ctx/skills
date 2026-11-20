# Recipes per language

Guard entries that turn a stack's existing tools into guards. Prefer the tools the repository already uses, in the configuration it already has, and pin their versions (lockfile, `==` pins, `go run pkg@vX`, a pinned CI install step). A tool whose version differs from the one recorded in the baseline fails with `rule-change`, which keeps local and CI runs comparable. Never use a tool's own "fail above N" switch as the guard: it has no baseline, and a threshold inside a tool flag escapes the policy lock.

Commands run from the repository root. Write `{root}` for the scanned tree (it is a temporary base worktree while baselines are derived) and `{out}` for the report file. When a tool reads its configuration from the current directory, `cd {root} && …` and list the configuration in `config_files`, so the current configuration is copied into the base worktree. Entries marked *verified* were exercised against the real tool, either by the skill's integration tests or through real output kept as a test fixture; for the others, check the flags against the installed version once.

## Any language

```json
{"name": "complexity", "run": "lizard --csv -x \"*/node_modules/*\" -x \"*/vendor/*\" -x \"*/tools/guard/*\" {root}", "parse": "lizard", "tier": "fast", "requires": ["lizard"], "version": "lizard --version"}
{"name": "semgrep", "run": "semgrep scan --metrics=off --disable-version-check --quiet --config tools/guard/rules/semgrep --sarif --output {out} {root}", "parse": "sarif", "requires": ["semgrep"], "version": "semgrep --version", "config_files": ["**/.semgrepignore", "tools/guard/rules/semgrep/*.yaml"]}
{"name": "gitleaks", "run": "gitleaks dir {root} --no-banner --redact --exit-code 0 --report-format sarif --report-path {out}", "parse": "sarif", "tier": "fast", "requires": ["gitleaks"], "version": "gitleaks version", "config_files": ["**/.gitleaks.toml"]}
{"name": "vulns", "run": "osv-scanner scan source -r --format sarif --output-file {out} {root}", "parse": "sarif", "ok_exit": [0, 1], "when": ["deps"], "requires": ["osv-scanner"], "version": "osv-scanner --version"}
{"name": "workflows", "run": "zizmor --offline --format sarif {root}/.github/workflows", "parse": "sarif", "ok_exit": [0, 10, 11, 12, 13, 14], "when": ["ci"], "requires": ["zizmor"], "version": "zizmor --version"}
{"name": "duplication", "run": "jscpd --silent --reporters sarif --output {tmp}/jscpd {root}", "input": "{tmp}/jscpd/jscpd-sarif.json", "parse": "sarif"}
```

Lizard, the bundled Semgrep rules, gitleaks, zizmor and jscpd (4.2) are *verified*; jscpd reports a clone once, on the file where it was found; osv-scanner needs network access to its database. Semgrep rule ids carry the config path as a prefix (`tools.guard.rules.semgrep.gr.py.…`); keep the `--config` path relative and stable, or every key changes. Registry packs (`p/python`, `p/owasp-top-ten`) are fetched at run time, so vendor them into the repository at a fixed version instead. The built-in guards (`secrets`, `suppressions`, `size`, `test-changes`, `deps`, `migrations`) cover every language with no tool.

The SARIF adapter keys findings by file and rule and counts them, so a finding moving within a file never looks new. Results with in-source suppressions or `baselineState: absent` are skipped; the `suppressions` guard counts the suppressions themselves.

## JavaScript / TypeScript

```json
{"name": "eslint", "run": "cd {root} && npx --no-install eslint -f json .", "parse": "eslint", "tier": "fast", "version": "npx --no-install eslint --version", "config_files": ["**/eslint.config.*", "**/.eslintrc*"]}
{"name": "typecheck", "run": "cd {root} && npx --no-install tsc --noEmit --pretty false -p .", "parse": "tsc", "version": "npx --no-install tsc --version", "config_files": ["**/tsconfig*.json"]}
{"name": "tests", "run": "cd {root} && npx --no-install vitest run --reporter=junit --outputFile={out} --coverage --coverage.reporter=lcov --coverage.reportsDirectory={tmp}/cov --coverage.all", "parse": "junit", "timeout": 1800}
{"name": "diff-coverage", "builtin": "diff-coverage", "input": "{tmp}/cov/lcov.info", "min": {"logic": 80}}
{"name": "mutation", "builtin": "mutation", "tier": "strict", "run": "npx --no-install stryker run --reporters json", "input": "reports/mutation/mutation.json", "min_score": 60, "timeout": 3600}
{"name": "api", "builtin": "snapshot", "run": "node tools/guard/js/api-surface.mjs --root {root} src/index.js", "when": ["public-api"]}
```

- Jest: add `jest-junit` and run `JEST_JUNIT_OUTPUT_FILE={out} npx jest --ci --reporters=default --reporters=jest-junit --coverage --coverageReporters=lcov --coverageDirectory={tmp}/cov`. Node's runner: `node --test --test-reporter=junit --test-reporter-destination={out}`. Mocha: `mocha-junit-reporter`.
- Stability and security depth: typescript-eslint `no-floating-promises` and `no-misused-promises`, `eslint-plugin-security`, `eslint-plugin-n` (`no-sync`). Dead code: knip (`--reporter json` through a small converter, or the JS dead-code detector). Cycles and layering: dependency-cruiser, or the JS cycles/architecture detectors. Bundle budget: `{"builtin": "metric", "run": "node -e \"console.log(require('fs').statSync('dist/main.js').size)\"", "budget": {"pct": 5}}` after a build guard.
- Lockfile: `{"name": "lockfile", "run": "npm ci --ignore-scripts --dry-run", "parse": "exit", "when": ["deps"]}` (*verified* to fail on a mismatch); pnpm `pnpm install --frozen-lockfile --lockfile-only`; yarn `yarn install --immutable --mode=skip-build`.
- Conventional loading that dead-code and cycle detectors must know about: file-based routes (Next.js, Nuxt, SvelteKit, Remix), config files loaded by tools (`*.config.*`), `React.lazy(() => import('…'))`, test helpers that load modules by string path.
- Reference detectors for what no tool covers: `examples/javascript/` (complexity with helper add-back, duplication, dead code, test shape, N+1 / loop shape, cycles, architecture, API surface). The tests cover them, and they emit `guard-ratchet/detector@2`; copy them into `tools/guard/js/` and adjust the constants in their README. They parse JavaScript only (`.js`, `.jsx`, `.mjs`, `.cjs`) and skip directories named `node_modules`, `vendor`, `generated`, `dist`, `coverage`, `build`, `test-results` and `data`; TypeScript files are not read, so in a TypeScript code base use the tools above (typescript-eslint, knip, dependency-cruiser) instead.

## Python

```json
{"name": "ruff", "run": "cd {root} && ruff check --output-format sarif --output-file {out} .", "parse": "sarif", "tier": "fast", "requires": ["ruff"], "version": "ruff --version", "config_files": ["**/ruff.toml", "**/.ruff.toml", "**/pyproject.toml"]}
{"name": "mypy", "run": "cd {root} && mypy --no-error-summary --show-error-codes .", "parse": "mypy", "requires": ["mypy"], "version": "mypy --version", "config_files": ["**/mypy.ini", "**/pyproject.toml", "**/setup.cfg"]}
{"name": "tests", "run": "cd {root} && python3 -m pytest -q -p no:cacheprovider --junitxml={out} --cov=src --cov-report=xml:{tmp}/coverage.xml", "parse": "junit", "timeout": 1800}
{"name": "diff-coverage", "builtin": "diff-coverage", "input": "{tmp}/coverage.xml", "min": {"logic": 80}}
{"name": "api", "builtin": "snapshot", "run": "python3 tools/guard/guard.py pyapi {root}/src/mypkg", "when": ["public-api"]}
```

ruff (SARIF), pytest + pytest-cov and `pyapi` are *verified*. Use the project's interpreter (`.venv/bin/python`), because the base worktree links `.venv` in. Useful ruff families beyond the defaults: `S` (bandit rules), `BLE`, `ASYNC`, `SIM115`, `PERF`, `PT` (pytest style). `mypy --strict` backlogs ratchet per file and error code. Dead code: vulture (`--min-confidence 100` first; check its false positives on this repository before lowering it). Layering: import-linter as an `exit` guard. Mutation: mutmut or cosmic-ray, exported to the mutation-testing-elements JSON if possible; otherwise run them as a strict-tier `exit` guard. Migrations: `python manage.py makemigrations --check --dry-run` or `alembic check` as `exit` guards with `when: ["model", "migration"]`. Lockfiles: `uv lock --check`, `poetry check --lock`.

## Go

```json
{"name": "vet", "run": "cd {root} && go vet ./... 2>&1", "parse": "gcc", "ok_exit": [0, 1], "tier": "fast", "version": "go version"}
{"name": "lint", "run": "cd {root} && golangci-lint run --output.sarif.path={out} ./...", "parse": "sarif", "ok_exit": [0, 1], "version": "golangci-lint --version", "config_files": ["**/.golangci.y*ml"]}
{"name": "tests", "run": "cd {root} && gotestsum --junitfile {out} -- -race -coverprofile={tmp}/go.cover ./...", "parse": "junit", "timeout": 1800}
{"name": "diff-coverage", "builtin": "diff-coverage", "input": "{tmp}/go.cover", "min": {"logic": 80}}
{"name": "modtidy", "run": "cd {root} && go mod tidy -diff", "parse": "exit", "when": ["deps"]}
```

`go mod tidy -diff` is *verified* to fail when go.mod/go.sum are out of date, and the golangci-lint (2.x) entry is *verified*. The Go coverprofile is mapped to repository paths through the module path in `go.mod`. golangci-lint linters that matter for agents: `errcheck`, `bodyclose`, `noctx`, `sqlclosecheck`, `contextcheck`, `gosec`, `staticcheck` (`U1000` for dead code). Package cycles are a compile error, so no cycle guard; layering via `depguard`. API: `gorelease` or `apidiff` against `{base}`.

## Rust

`cargo check --locked --all-targets` and `cargo test` as `exit` guards. Clippy as SARIF through `clippy-sarif` (`cargo clippy --message-format=json | clippy-sarif`). Tests: cargo-nextest with a JUnit profile. Coverage: `cargo llvm-cov --lcov --output-path {tmp}/lcov.info`. Mutation: cargo-mutants `--in-diff`. API: cargo-semver-checks against the base. `#[allow(…)]` and `#[ignore]` are counted by the suppressions guard.

## Java / Kotlin

Build and tests through Gradle or Maven as `exit`, results from `build/test-results/**/*.xml` or `target/surefire-reports/*.xml` with `input` and `parse: junit`. Coverage: JaCoCo XML (`build/reports/jacoco/test/jacocoTestReport.xml`). Static analysis: SpotBugs (+ find-sec-bugs), PMD, detekt and ktlint all write SARIF. Architecture: ArchUnit as tests. Mutation: PIT with the mutation-testing-elements report plugin. API: japicmp or revapi.

## C# / .NET

`dotnet build -warnaserror` (or SARIF via `-p:ErrorLog=…,version=2.1`) and `dotnet test --logger "junit;LogFilePath={out}"` (JunitXml.TestLogger). Coverage: coverlet, Cobertura format. Mutation: Stryker.NET (mutation-testing-elements JSON). `#pragma warning disable`, `[SuppressMessage]` and `[Fact(Skip = …)]` are counted by the suppressions guard. Lockfile: `RestorePackagesWithLockFile` + `dotnet restore --locked-mode`.

## Ruby

RuboCop (`--format json` through a converter, or SARIF via `code-scanning-rubocop`), Brakeman (`-f sarif`), RSpec with `rspec_junit_formatter`, SimpleCov with the LCOV formatter, `bundle-audit` as an `exit` guard. Rails migrations sit under `db/migrate/`, which the migrations guard recognizes.

## PHP

PHPStan or Psalm (SARIF or checkstyle through a converter, with baselines replaced by the ratchet), PHPUnit `--log-junit {out}` and `--coverage-cobertura {tmp}/cobertura.xml`, Infection for mutation (mutation-testing-elements JSON), `composer validate --strict` and `composer audit` as `exit` guards.

## Swift / Objective-C, Dart / Flutter, Elixir, C / C++

- Swift: SwiftLint (`--reporter sarif`), `xcodebuild test` with `xcresult` converted to JUnit (xcbeautify or trainer), coverage via `xccov` converted to LCOV.
- Dart / Flutter: `dart analyze --format=json` through a converter, `flutter test --machine` with `junitreport`, `flutter test --coverage` (LCOV). Generated `*.g.dart` and `*.freezed.dart` files are classified as generated.
- Elixir: Credo (`--format sarif`), `mix test` with `junit_formatter`, `mix xref graph --format cycles` for cycles.
- C / C++: clang-tidy and cppcheck (SARIF or gcc-style text via `parse: gcc`), CTest `--output-junit`, gcovr `--cobertura`, `include-what-you-use` for fan-out. Compiler warnings ratchet per file with `-Wall` output and `parse: gcc`.

## Any other language

Look for, in order: the language's mainstream linter and whether it writes SARIF, JSON or compiler-style text; a test runner or reporter that writes JUnit; a coverage tool that writes LCOV or Cobertura. Lizard and Semgrep (via its generic mode) cover complexity and patterns for most languages. Write a detector only for what is left (`detector-contract.md`).
