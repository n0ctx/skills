# Detector contract

A detector is a program a guard runs to measure something no existing tool measures. The runner owns baselines, thresholds, exceptions and locks. A detector only has to produce trustworthy measurements, in this format, and fail closed when it cannot.

## Output: `guard-ratchet/detector@2`

The detector prints one JSON document to stdout (or to `{out}`) and exits 0 whenever the scan ran, even if it found problems. Exit 2 means bad arguments; any other non-zero exit is a crash.

```json
{
  "schema": "guard-ratchet/detector@2",
  "guard": "complexity",
  "tool": {"name": "check-complexity.mjs", "version": "2.0.0"},
  "coverage": {"planned": 412, "scanned": 412, "unit": "files", "functions": 3810},
  "parse_failures": [],
  "unsupported": [{"path": "src/plugins.js", "message": "cannot resolve import('./missing.js')"}],
  "hard": [{"rule": "focused-test", "key": "tests/a.test.js#suite>case", "path": "tests/a.test.js", "line": 3,
            "message": "test.only stops the rest of the file from running"}],
  "advisory": [{"rule": "guard-allow", "key": "src/a.js#mirror of server code", "path": "src/a.js", "line": 10,
                "message": "mirror of server code"}],
  "findings": [{"rule": "dead-export", "key": "src/a.js#foo", "count": 1, "path": "src/a.js", "line": 10}],
  "metrics": [{"metric": "fn-complexity", "key": "src/a.js#parse", "path": "src/a.js", "line": 12, "value": 41}]
}
```

- `findings` are ratchet items. The guard's `mode`/`modes` in the policy may turn a rule into `hard`, `budget` or `advisory`, so emit everything that could be baselined here.
- `hard` is only for items that are never acceptable whatever the policy says (focused tests, tests without assertions, malformed suppression markers).
- `metrics` are raw values for every entity, not only those above some limit: the runner applies the threshold for the file's kind and language. Do not hard-code thresholds in a detector, because a threshold inside the detector cannot adapt to code kinds and escapes the policy lock.
- `path` (repo-relative, `/`-separated) and `line` are evidence. The runner uses `path` to classify the code kind and to drop generated, vendored and excluded files. `line` never goes into a key.
- The runner treats `parse_failures`, `unsupported`, `scanned < planned`, and `scanned` below `coverage.min` (optional) as integrity failures. Report them; never drop the file silently.
- Version 1 output (`{guard, scanned, min_scanned, parse_failures, hard: [strings], findings}`) is still accepted.

## Invariants

**Deterministic.** The same code, configuration and detector version give the same document, byte for byte. Sort files by repo-relative path and items by key. Do not depend on traversal order, time, randomness, absolute paths or parallel completion order.

**Fail closed.** A parse failure, an unreadable required configuration, a dependency graph that cannot be built, or a deterministic in-repo reference that cannot be resolved is reported (as `parse_failures` or `unsupported`), never turned into "0 findings". Inputs that static analysis cannot determine (`import(variable)`, reflection, DI containers) may be documented limitations instead.

**Coverage you can check.** Count planned units before parsing and successful ones after, plus the entity counts that matter for this detector (functions, modules, edges, test cases). The runner records `scanned` in the baseline and fails when a later scan is more than 5% smaller, which catches a path typo or a broken walker that would otherwise look like an improvement.

**Stable keys.** Unrelated edits must not change existing keys: inserting lines, reformatting, adding a function before another one. Use the repo-relative path plus a symbol name, or a hash of normalized content. For anonymous functions use "outer function > call name". Number genuine same-name collisions within one file `~2`, `~3` in order of appearance, so an addition elsewhere does not renumber them. Report one problem once: a large duplicate block that contains a smaller one is one finding; a module dependency is one finding per module pair, however many imports there are.

**Explicit scope.** State in one readable constant which directories are scanned and which are excluded, how tests are told apart from production code, how generated and vendored code are recognized, and which path aliases and framework loading conventions are resolved. `node_modules`, `vendor`, build output, coverage output and generated code never count as source.

**Anti-gaming built into the measure.** Prefer measures that a cosmetic change cannot game. The JavaScript complexity detector adds the decisions of a private helper that has exactly one caller back to that caller, so cutting branches into a helper does not lower the score. Its size measures count only named functions and classes, so extracting small functions does not inflate a definition count.

## Fixture tests

Prove the detector, not the ratchet (the runner's ratchet is already tested):

- positive: a real violation is reported, with the expected key and value;
- negative: clearly legitimate code nearby is not reported;
- boundary: values at and just past what distinguishes them, allowed and forbidden graph edges, scope inclusions and exclusions;
- key stability: inserting unrelated code or modules does not change existing keys;
- parse failure lands in `parse_failures`; an empty scan reports `planned: 0`;
- determinism: two runs print identical output.

When the detector wraps a mature tool, test the conversion, key normalization, coverage reporting and failure propagation, not the tool's own algorithm.

## Checklist

- [ ] Prints `guard-ratchet/detector@2`, exits 0 on a completed scan
- [ ] Deterministic ordering
- [ ] Fails closed with `parse_failures` / `unsupported`
- [ ] Reports `coverage.planned` and `coverage.scanned`
- [ ] Keys without line numbers, stable under unrelated edits
- [ ] Raw metrics, no thresholds inside the detector
- [ ] Scope stated in one constant
- [ ] Fixture tests for each item above
