# guard-ratchet

An agent skill that installs executable quality guards in a repository, so that a coding agent working without line-by-line human review cannot quietly make the code worse, weaken the tests, or loosen the guards themselves.

Existing problems are recorded in a baseline instead of being fixed on day one. After that a check fails on new problems, on existing ones getting worse, on improvements not recorded, and on any change that loosens the rules, a baseline or the scan scope. What a machine cannot judge reliably is reported as evidence for a human, never dressed up as a pass or a failure.

## What it guards

| Area | Blocks | Reports for review |
|---|---|---|
| Code shape | complexity, function length and file size above limits that depend on code kind (logic, UI, model, test, script, generated) and language; duplication (jscpd), dead code, cycles and architecture boundaries through each ecosystem's tools or the JavaScript reference detectors | near-limit functions |
| Lint, types, SAST | new findings per file and rule from any SARIF/ESLint/compiler-style tool (ruff, ESLint, tsc, mypy, golangci-lint, clippy, Semgrep, ...), plus a bundled Semgrep pack for Python and JavaScript/TypeScript covering injection, unsafe deserialization, disabled TLS, unbounded retries, swallowed errors, missing timeouts, blocking calls in async code | low-confidence levels |
| Test integrity | failing, removed or newly skipped tests (JUnit inventory), shrinking collection, deleted test files or files moved out of the test paths, focused tests, new skips, diff coverage below the minimum, mutation score on changed lines | assertions removed, expectations rewritten alongside implementation, survived mutants, untested changes |
| Secrets and supply chain | credentials in added lines, committed key files, git/URL/path dependencies, unpinned versions, new package indexes, off-registry lockfile hosts, stale lockfiles, new known vulnerabilities (osv-scanner), risky CI workflows (zizmor) | new dependencies, install scripts, aliases, open version ranges |
| Interfaces and data | removed public API (snapshots), breaking schema changes (schema diff tools such as oasdiff or buf, wired as guards), edits to merged migrations, generated code out of date, build and type failures | destructive migration statements |
| Performance | budgets for bundle size, benchmark medians or any metric; N+1 query patterns (JavaScript reference detector) | |
| The guards themselves | raised thresholds, removed or narrowed guards, new excludes, hand-edited baselines, detector, runner or tool-config edits, new suppression comments, code moved into a laxer kind (generated header, `vendor/`, `scripts/`), stale or committed report files | |

Verification is tiered by the change itself: docs-only changes run fast checks; changes to auth, migrations, schemas, public API, dependencies, CI, build or guard configuration, very large changes, and changes that delete tests or weaken assertions run the strict tier. The agent does not choose the tier.

## How it works

```
change (base..working tree) ──> risk tier ──> selected guards ──> tool / built-in ──> adapter
                                                                                        │
  report (text / JSON / Markdown) <── exceptions <── baseline + policy thresholds <─────┘
                                  <── locks: policy, baselines, protected files vs base
```

- **Detectors measure, the policy judges.** Tools run as they are; their output (SARIF, JUnit, LCOV/Cobertura/JaCoCo/Go coverage, ESLint JSON, lizard CSV, compiler text, detector JSON) is normalized into findings and metrics. Thresholds live in one policy file, per code kind and language.
- **Modes per rule**: hard (never baselined), ratchet (may only improve), budget (bounded growth that never accumulates), keep (tests and API may not disappear), advisory.
- **Baselines** carry a rule fingerprint and the scan size. A changed rule, tool version or tool config is a rule change: the baseline is rebuilt by scanning the *base* commit with the new rules, and any finding the new rules stop seeing needs an approved exception. Loosening detection therefore cannot pass as an improvement.
- **Exceptions** are the only way to accept a new problem: each has a reason and an approver, is audited in every report, and can expire.
- **Trusted CI run**: the pull request is judged a second time by the base branch's runner, policy, baselines, detectors and tool configs, so a change cannot rewrite the rules that judge it. Together with CODEOWNERS on the guard files this is what makes the gate binding; `references/trust-model.md` states exactly what each layer guarantees.

The runner is a single Python 3.10+ program with no dependencies (`scripts/guard.py`; Python 3.11+ to analyze TOML manifests). It is copied into the target repository at `tools/guard/`, so CI does not depend on where the skill is installed.

## Install

```bash
npx skills add n0ctx/skills --skill guard-ratchet -g
```

Or from a clone: `~/Projects/skills/scripts/link.sh --skill guard-ratchet --agent all`. Claude Code plugin: `/plugin install guard-ratchet --marketplace n0ctx/skills`. All options: [repo README](../../README.md). Agents without skill support can read `SKILL.md` and follow it; it contains no tool-specific instructions.

## Usage

Describe the outcome; the skill name is not needed:

- "Add quality gates to this repo so the agent can't make it worse. Record what's there today."
- "Stop the agent from deleting or skipping tests to get CI green."
- "Our Go service: block new complexity above 25, new vulnerabilities, and edits to old migrations."

The agent profiles the repository (`guard.py init`), proposes guards that fit the stack, writes `guards/policy.json`, derives baselines from the base commit (`guard.py update`), wires the check into lint and CI (`templates/`), verifies each guard by injecting violations in a temporary copy, and reports which protections are binding and which still need CODEOWNERS or branch protection.

Day to day:

```bash
python3 tools/guard/guard.py check            # exit 0 pass, 1 blocking, 2 config error, 3 incomplete
python3 tools/guard/guard.py update           # record improvements, renames, new tests (never regressions)
python3 tools/guard/guard.py update --rules-changed
python3 tools/guard/guard.py except add --guard G --rule R --key K --reason "..." --approved-by NAME
python3 tools/guard/guard.py risk             # which roles the change touches and why the tier is what it is
python3 tools/guard/guard.py gate feature --merge   # no CI: judge a branch by its own and main's rules, merge if both pass
```

## Layout

```
SKILL.md                    Agent workflow (entry point)
scripts/guard.py            Runner CLI; scripts/guardlib/ holds the implementation
scripts/tests/              Unit, end-to-end and real-tool integration tests
conformance/cases.json      Executable specification of the ratchet comparison
rules/semgrep/              Bundled Semgrep rules with their positive/negative test files
examples/javascript/        Reference detectors (complexity, duplication, dead code, test shape,
                            N+1 / loop shape, cycles, architecture, API surface)
templates/                  GitHub Actions, GitLab CI, CODEOWNERS
references/                 contract, detector contract, policy, guard catalog, recipes per language,
                            trust model, pitfalls
```

## Tests

```bash
python3 -m unittest discover -s scripts/tests          # runner (real-tool tests skip when a tool is missing)
python3 scripts/guard.py conformance                    # ratchet specification
semgrep --metrics=off --test rules/semgrep/             # bundled rules
cd examples/javascript && npm ci && npm test            # reference detectors
```

## Upgrading from 1.x

1.x shipped `scripts/ratchet.py` and detectors that kept their own baselines. In 2.0 the runner owns every baseline. Version 1 detector output and version 1 baselines are still read, and the next `guard.py update` rewrites them as version 2 with a fingerprint. Replace per-guard `ratchet.py check` calls with one `guard.py check`. The JavaScript detectors now print `guard-ratchet/detector@2` and no longer take `--baseline`/`--update-baseline`. Their anonymous-function placeholders are English (`(top-level)`, `(anonymous)`), so rebuild those baselines with `update --rules-changed`.

## License

MIT, see [LICENSE](LICENSE).
