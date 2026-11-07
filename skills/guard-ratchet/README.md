# guard-ratchet

[Simplified Chinese](README.zh-CN.md)

An agent skill that lets an AI coding assistant add "only get better" source guards to any repository.

Existing problems do not have to be fixed on day one; they are recorded in a baseline. After that, new problems, existing problems getting worse, and entries left in the baseline after being fixed all fail lint/CI. Code decay almost never comes from a single change. A ratchet turns every "just a little more" into an explicit decision: fix it, or update the baseline with a written reason in the commit.

## Guards covered

| Guard | What it checks |
|---|---|
| Cyclomatic complexity | Function complexity above the threshold; functions already above it may only decrease |
| Size | File length, function length, number of definitions, number of imports |
| Test shape | No assertion, committed `.only`, hardcoded-result assertions, long fixed waits, permanent skips |
| Dead code | Unreferenced files, unreferenced exports |
| Duplication | Runs of statements that are identical after identifiers are stripped (plain call sequences must match verbatim) |
| Runtime shape | Per-row queries in a loop (N+1), three-level nested loops, SELECT without WHERE/LIMIT |
| Circular dependencies | Modules referring to each other at load time |
| Architecture boundaries | Forbidden cross-layer dependencies, cross-module internal/deep imports |

The skill does not enable everything at once. It picks guards based on the repository: no database means no N+1 guard; Go already forbids package cycles at compile time, so no circular-dependency guard.

## Design

Two layers:

- **Ratchet** (repository-independent): how findings are compared to the baseline, what counts as a failure, how the baseline is updated. Fixed by the spec `references/contract.md`, the reference implementation `scripts/ratchet.py` (Python standard library, no dependencies), and the conformance cases `conformance/cases.json`.
- **Detectors** (language- and repository-dependent): chosen by the agent in order — existing tooling in the repo → mature off-the-shelf tools → a custom detector built with the language's parser.

Detectors emit findings as `{rule, key, count}`. Custom detectors must also satisfy the Detector Contract, proving scan scope, coverage, keys, and failure behavior are trustworthy. Prefer reusing `ratchet.py` for comparison; if Python is unavailable, rewrite it in the repository's main language, provided it passes all conformance cases.

Each rule has three levels: **hard rules** (fail immediately, never baselined), **baseline rules** (existing findings recorded, may only decrease), and **advisory** (optional, printed but not failing — for near-threshold warnings or uncertain signals).

## Install

Install just this skill, globally:

```bash
npx skills add n0ctx/skills --skill guard-ratchet -g
```

Or link it from a local clone:

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
~/Projects/skills/scripts/link.sh --skill guard-ratchet --agent all
```

Full flags, updates and uninstall: [repo README](../../README.md).

For agents without skill support, have them read `SKILL.md` first and follow the process; the file contains no tool-specific instructions.

## Usage

Describe the need; the skill name is not required:

- "Add checks to make lint: function complexity must stay under 10, no unused modules, no per-row queries in loops. Record existing problems first; from now on they may only decrease."
- "Add copy-paste and circular-dependency checks to npm run lint, without adding dependencies. A colleague has uncommitted changes in src/report.js — don't let them into the baseline."
- "Go project: no new functions above complexity 15, and existing ones must not get more complex."

The agent follows the process in `SKILL.md`: understand the repo → choose guards → choose detectors → define detector invariants → implement and verify detectors → generate the baseline → wire into lint/CI → verify on the real repo → report.

Using the reference implementation standalone:

```bash
python3 scripts/ratchet.py conformance                      # run conformance cases
my-detector | python3 scripts/ratchet.py check  --findings - --baseline guards/complexity.json
my-detector | python3 scripts/ratchet.py update --findings - --baseline guards/complexity.json
```

## Layout

```
SKILL.md                      Process and acceptance criteria (agent entry point)
references/
  contract.md                 Ratchet semantics, finding and baseline formats, CLI conventions
  detector-contract.md        Correctness and coverage requirements for custom detectors
  guard-catalog.md            Signals, key design, default thresholds, common false positives
  language-recipes.md         Parsers and off-the-shelf tools per language
  pitfalls.md                 Pitfalls from real deployments
scripts/ratchet.py            Ratchet reference implementation
conformance/cases.json        Ratchet conformance cases
examples/javascript/
  check-architecture.mjs     Reference implementation for simple path-based architecture rules
  README.md                  JavaScript reference implementation notes and Detector Contract test types
```

## Evaluation

Claude Sonnet 5 was used to compare "with skill" vs "without skill" on three small repositories, one run per configuration. Deliverables were checked programmatically (inject violations into a repo copy and rerun lint):

| Repo | With skill | Without skill |
|---|---|---|
| Python: complexity, dead code, N+1 | 9/9 | 7/9 |
| Node: duplication, circular dependencies, colleague's uncommitted changes in the worktree | 9/9 | 6/9 |
| Go: complexity, N+1 | 8/8 | 6/8 |

Both sides produced working guards. The gap concentrated in: whether a fixed-but-not-removed baseline entry is caught (3/3 vs 0/3), whether the guards themselves have tests (3/3 vs 0/3), and whether deduplication counts each occurrence. The skill took about 3x longer. Small sample; indicative only.

These are first-version results. Later versions added "verify only in a temporary copy, never touch someone else's worktree", "advisory findings", and "prefer reusing ratchet.py, read reference files by stage"; no re-evaluation was run.

## License

MIT, see [LICENSE](LICENSE).

## Install as a Claude Code plugin

```
/plugin install guard-ratchet --marketplace n0ctx/skills
```
