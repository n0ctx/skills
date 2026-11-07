# JavaScript reference implementation

[Simplified Chinese](README.zh-CN.md)

Six guards deployed in a real repository (Express backend + React frontend + SQLite), plus a minimal architecture-boundary reference implementation. Parsing uses espree; fixture tests use Node's built-in `node:test`. It does not depend on `scripts/ratchet.py` — ratchet semantics are implemented in `guard-common.mjs`.

When writing custom detectors, use these as a reference for AST traversal, key design, and fixture tests. Do not copy them wholesale. The constants below belong to the original repository; replace each one with the current repository's specifics before deploying:

| File | Constants | Meaning |
|---|---|---|
| guard-common.mjs | `CODE_SUFFIXES`, `SKIP_DIRS` | File extensions to scan; excluded dependency, generated, build, coverage, and data directories |
| check-complexity.mjs | `CODE_SUFFIXES`, `SKIP_DIRS` | A separate copy of scan extensions and exclusions maintained by the complexity guard; verify against guard-common.mjs |
| check-complexity.mjs | `MIN_FUNCTION_COUNT` | Minimum function count, to detect a scan that silently finds nothing |
| check-duplication.mjs / check-perf-shape.mjs | `SCAN_DIRS` | Production source directories |
| check-perf-shape.mjs | `QUERY_DIR`, `DB_MODULE` | Query-layer directory (used to spot N+1 in business code); DB connection module (tells whether query-layer functions really hit the database) |
| check-perf-shape.mjs | `SQL_DIRS`, `SQL_EXEMPT` | Business-layer directories checked for unconditional SELECT, and their exemptions |
| check-tests.mjs | `SCAN_DIRS`, `E2E_DIR`, `BACKEND_TEST_SCRIPTS` | Test directories, e2e directory, test commands that must exclude the e2e directory |
| check-dead-code.mjs | `ENTRY_FILES`, `HTML_ENTRIES`, `HOOK_FILE_RE` | Program entry points, HTML entry points, plugins loaded by directory |
| check-dead-code.mjs | `CONVENTION_ENTRIES`, `PUBLIC_API` | Files loaded by path string or kept for copying; agreed public exports (not reported one by one) |
| import-graph.mjs | `ROOT_IMPORTERS` | Helper functions in tests that load modules by string path |
| check-architecture.mjs | `ARCH_RULES` | Architecture boundary rules. `frontend/`, `backend/routes/`, `backend/db/`, and `features/` are example directories |

| File | Contents |
|---|---|
| guard-common.mjs | Traversal, parsing, arguments, baseline read/write and comparison, the `guard-allow` intentional-retention marker |
| import-graph.mjs | In-repo reference graph (shared by dead code, circular dependencies, and architecture boundaries); reports deterministic references it cannot resolve |
| guard-fixture.mjs | Fixture test helpers: temporary repos, file read/write, running guards |
| check-complexity.mjs | Cyclomatic complexity (numeric baseline) |
| check-duplication.mjs | Duplicate runs of statement token sequences (identifiers stripped) |
| check-dead-code.mjs | Unreferenced files / unreferenced exports |
| check-tests.mjs | Test shape: no assertion, `.only`, hardcoded assertions, long waits, playwright placement, repeated launches, skips |
| check-perf-shape.mjs | Three-level loops, queries inside loops (propagating query-layer effects by db-read / db-write), unconditional SELECT |
| check-cycles.mjs | Circular dependencies in static imports (hard rule) |
| check-architecture.mjs | Path-rule architecture boundaries. Hard rules by default; `--baseline-mode` switches to baseline comparison |
| *.test.mjs | Fixture tests for detector correctness and ratchet correctness; see `references/detector-contract.md` section 6 for coverage |

The original repository also had a size guard (file tokens, function length, etc.); it was omitted here because of its size. See `references/guard-catalog.md` section 2 for the approach.
