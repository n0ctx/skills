# JavaScript reference implementation

Six guards deployed in a real repository (Express backend + React frontend + SQLite), plus a minimal architecture-boundary reference detector and a small API-surface producer. That repository context is provenance only: the directory names below (`backend/db/queries/`, `frontend/src/`, ...) come from it. Parsing uses espree; fixture tests use Node's built-in `node:test`; run them here with `npm ci && npm test`.

The detectors are pure measurement tools. Each `check-*.mjs` prints one JSON document to stdout and nothing else. There is no local baseline: baseline files, new/worse/stale comparison, exceptions, per-code-kind thresholds and coverage floors all belong to the central runner `scripts/guard.py`, so exactly one ratchet implementation exists. The detectors do not depend on the runner and can be run on their own.

When writing custom detectors, use these as a reference for AST traversal, key design and fixture tests. Do not copy them wholesale.

## Output contract: `guard-ratchet/detector@2`

```json
{
  "schema": "guard-ratchet/detector@2",
  "guard": "complexity",
  "tool": {"name": "check-complexity.mjs", "version": "2.0.0"},
  "coverage": {"planned": 12, "scanned": 12, "unit": "files", "functions": 340},
  "parse_failures": ["src/bad.js"],
  "unsupported": [{"path": "src/a.js", "message": "cannot resolve static import ./missing.js"}],
  "hard": [{"rule": "focused-test", "key": "tests/a.test.js#suite>case", "path": "tests/a.test.js", "line": 3, "message": "..."}],
  "advisory": [{"rule": "guard-allow", "key": "src/a.js#<reason>", "path": "src/a.js", "line": 10, "message": "<reason>"}],
  "findings": [{"rule": "dead-export", "key": "src/a.js#foo", "count": 1, "path": "src/a.js", "line": 10, "message": "..."}],
  "metrics": [{"metric": "fn-complexity", "key": "src/a.js#parse", "path": "src/a.js", "line": 12, "value": 41}]
}
```

- Exit codes: `0` when the scan ran, even if it found problems; `2` for bad command-line arguments (including the removed `--baseline` and `--update-baseline`); `1` only for an unexpected crash (message on stderr).
- `coverage.planned` is the number of files in scope counted before parsing; `coverage.scanned` is the number parsed successfully; further counters (`functions`, `modules`, `edges`, `test_cases`, `db_read_exports`, `db_write_exports`) are plain numbers. Detectors apply no floor: the runner fails the scan when `parse_failures` or `unsupported` is non-empty or `scanned < planned`, and applies its own floors.
- `key` never contains a line number; `line` is evidence only. Keys are `path#symbol`, `outer>call`, `~2` suffixes for repeats (the placeholders are `(top-level)`, `(anonymous)` and `(default)`), content hashes for duplication, sorted members for cycles, and module pairs for architecture.
- Output is deterministic: every array is sorted by key (then rule), files are visited in repo-relative path order, and nothing depends on the absolute root path.
- `hard` holds only what is never acceptable. `findings` holds everything the runner may baseline. `metrics` are numbers for the runner to threshold. `advisory` is informational.

### Rules per detector

| Detector (`guard`) | hard | findings | metrics |
|---|---|---|---|
| `check-complexity.mjs` (`complexity`) | | | `fn-complexity` for every function, including the add-back of single-call private helpers |
| `check-duplication.mjs` (`duplication`) | `guard-allow-invalid` | `duplicate` (key = content hash, count = occurrences) | |
| `check-dead-code.mjs` (`dead-code`) | `guard-allow-invalid` | `dead-file`, `dead-export` | |
| `check-tests.mjs` (`tests`) | `focused-test`, `test-without-assertion`, `tautological-assertion`, `long-fixed-wait`, `playwright-outside-e2e`, `e2e-in-default-command`, `guard-allow-invalid` | `heavy-setup` (count per file, only when above 1), `skip` | |
| `check-perf-shape.mjs` (`perf-shape`) | `deep-loop`, `guard-allow-invalid` | `loop-query`, `unbounded-select` | |
| `check-cycles.mjs` (`cycles`) | | `cycle` (key = sorted members joined with ` <-> `) | |
| `check-architecture.mjs` (`architecture`) | | `forbidden-dependency`, `internal-api-import` (key = `source -> target`) | |

`guard-allow` markers (`// guard-allow(<guard>): <reason>`, see `guard-common.mjs`) are handled detector-side in `duplication`, `dead-code`, `tests` and `perf-shape`: findings they cover are not emitted, every valid marker is an `advisory` item (rule `guard-allow`), and a malformed or unused marker is a `hard` item (rule `guard-allow-invalid`).

Unresolvable literal in-repo imports, unreadable `package.json` files and a missing `backend/package.json` test script are reported in `unsupported`, never silently ignored.

## `api-surface.mjs`

A producer for the runner's API-snapshot guard:

```
node api-surface.mjs --root <dir> <entry.js>...
```

It prints, one per line and sorted, the public export surface of the entry modules, following `export * from`, `export { x } from` and re-exported imports inside the repository with `import-graph.mjs` resolution:

```
src/index.js#parse(input,{strict=,limit},...rest)    function: names, `x=` default, `...rest`, `{a,b}` / `[a,b]`
src/index.js#Client class                            class, then one line per public member
src/index.js#Client.static create(opts)              `static ` / `get ` / `set ` prefix the member name
src/index.js#VERSION const                           anything else
```

Private (`#x`) members and class fields are not part of the surface; CommonJS `module.exports` is not understood. It fails closed: a parse failure, a missing entry, or a re-export that cannot be followed (unresolved path, external package, a name the target does not export, a re-export cycle) prints a message to stderr and exits `1` instead of printing a smaller surface.

## Constants to replace

The constants below belong to the original repository; replace each one with the current repository's specifics before deploying:

| File | Constants | Meaning |
|---|---|---|
| guard-common.mjs | `CODE_SUFFIXES`, `SKIP_DIRS` | File extensions to scan; excluded dependency, generated, build, coverage and data directories (shared by every detector, including complexity) |
| check-duplication.mjs / check-perf-shape.mjs | `SCAN_DIRS` | Production source directories |
| check-duplication.mjs | `MIN_TOKENS` | Shortest duplicated token run that is reported |
| check-perf-shape.mjs | `QUERY_DIR`, `DB_MODULE` | Query-layer directory (used to spot N+1 in business code); DB connection module (tells whether query-layer functions really hit the database) |
| check-perf-shape.mjs | `SQL_DIRS`, `SQL_EXEMPT` | Business-layer directories checked for unconditional SELECT, and their exemptions |
| check-tests.mjs | `SCAN_DIRS`, `E2E_DIR`, `BACKEND_TEST_SCRIPTS` | Test directories, e2e directory, test commands that must exclude the e2e directory |
| check-tests.mjs | `MAX_DELAY_MS` | Longest fixed wait allowed in non-e2e tests |
| check-dead-code.mjs | `ENTRY_FILES`, `HTML_ENTRIES`, `HOOK_FILE_RE` | Program entry points, HTML entry points, plugins loaded by directory |
| check-dead-code.mjs | `CONVENTION_ENTRIES`, `PUBLIC_API` | Files loaded by path string or kept for copying; agreed public exports (not reported one by one) |
| import-graph.mjs | `ROOT_IMPORTERS` | Helper functions in tests that load modules by string path |
| check-architecture.mjs | `ARCH_RULES` | Architecture boundary rules. `frontend/`, `backend/routes/`, `backend/db/`, and `features/` are example directories |

## Files

| File | Contents |
|---|---|
| guard-common.mjs | Traversal, parsing, arguments, the `emit` helper for detector@2 output, the `guard-allow` intentional-retention marker |
| import-graph.mjs | In-repo reference graph (shared by dead code, circular dependencies, architecture boundaries and the API surface); reports deterministic references it cannot resolve |
| guard-fixture.mjs | Fixture test helpers: temporary repos, file read/write, `run` (raw process) and `scan` (parsed detector@2 document) |
| check-complexity.mjs | Cyclomatic complexity, one `fn-complexity` metric per function |
| check-duplication.mjs | Duplicate runs of statement token sequences (identifiers stripped) |
| check-dead-code.mjs | Unreferenced files / unreferenced exports |
| check-tests.mjs | Test shape: no assertion, `.only`, hard-wired assertions, long waits, playwright placement, repeated launches, skips |
| check-perf-shape.mjs | Three-level loops, queries inside loops (propagating query-layer effects by db-read / db-write), unconditional SELECT |
| check-cycles.mjs | Circular dependencies in static imports |
| check-architecture.mjs | Path-rule architecture boundaries |
| api-surface.mjs | Public export surface of entry modules, for API snapshots |
| *.test.mjs | Fixture tests proving detector correctness against the emitted JSON: positive and negative cases, threshold-free metric values, key stability, parse failures, empty scans, `guard-allow` handling, determinism (`detector-output.test.mjs` covers the contract shared by all detectors); see "Invariants" and "Fixture tests" in `references/detector-contract.md` |

File size needs no detector: the built-in `size` guard covers it for every language, and lizard reports function length (`references/guard-catalog.md`, "Code quality metrics").
