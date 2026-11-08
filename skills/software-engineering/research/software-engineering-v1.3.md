# v1.3 design rationale (maintainer only)

**Scope:** v1.3 responds to 2025–2026 evidence on why agent-written code becomes hard to understand and change. The main finding that constrains this Skill: in SlopCodeBench, explicit quality instructions cut initial verbosity and erosion by up to a third but did not change how fast code degraded across later iterations. A SKILL.md is such an instruction. So v1.3 does not try to make the first version cleaner; it adds checks that run at every change against the pre-change state, which is the only point where a prompt can act on each iteration. Durable enforcement belongs in the repository's lint or CI, not here.

## What changed from v1.2

| Rule | Change | Evidence | Possible regression | Eval |
|---|---|---|---|---|
| 2 | List sites that must change in step | MDPI *Information* 17(9):918 (2026): incomplete cross-location edits were 23 of 34 Copilot-specific failures; defects cluster where correctness depends on code outside the current file. BTH survey: "context blindness and scope drift" was the most frequent open-text theme | Extra search on trivial edits | P12 |
| 4 | Search for an existing helper before adding one | BTH survey; interview data in arXiv:2607.10856 (new utilities proliferate) | None expected beyond a search | P3, P11 |
| 4 | Restructure a touched unit instead of appending another branch or near-copy, including earlier agent code | SlopCodeBench v2 (arXiv:2603.24755): erosion rose in 77% and verbosity in 75.5% of trajectories; agent code 2.0× erosion and 2.3× verbosity vs 473 human repos; failure forms are if/else ladders and growing god functions. Interviews: agents avoid changing structure "even if it wrote that structure itself" | Over-refactoring on a one-line change; scoped to touched units | P11, sequential test |
| 4 | Record rationale and rejected alternative for non-obvious choices | Storey (arXiv:2603.22106): intent debt, the unrecorded design reasons that humans and agents both need | Comment noise; constrained to the project's authoritative location | P8 |
| 10 | Compare touched units with pre-change state; delete superseded path and orphaned helpers | SlopCodeBench (degradation is a per-step slope); arXiv:2607.10856 (old implementation left beside the new one) | Deleting a path that still has callers; rule 7 still requires checking callers | N11 |

## Considered and excluded

- **Comprehension scaffolding (explain or teach instead of implement).** Shen & Tamkin (arXiv:2601.20245) and Ahmad (arXiv:2604.13277) show it protects human learning, but the interaction mode is chosen by the user and SOUL, not by an engineering standard.
- **Report requirements such as "explain every change".** SOUL owns reporting.
- **Length ceilings or mandatory refactor checkpoints.** Still excluded for the reasons in v1.2; SlopCodeBench's erosion metric is relative concentration, not an absolute length.
- **GitClear and the 12-turn iteration study.** Vendor data and an unverified secondary summary; not used as grounds for any rule.

## Pilot (2026-11-08)

Directional only: one run per condition, v1.3 against v1.2, same model and brief, fresh agent per task.

**Single-turn, four fixtures** (extend an agent-written if/elif exporter, replace a config format, add a field across five sites, an architecture review of duplicated pricing). Both versions passed all 27 programmatic checks; tokens and time were within noise (+103 tokens, +3 s). The cases did not discriminate: on a first small change both versions already restructure, delete the old parser, and update every site. They do show no regression on routine work.

**Sequential, five linked steps** on a notifier (Slack, SMS, retry, quiet hours, webhook), each step revealed only at its turn and checked by hidden accumulated acceptance tests:

| Step | v1.3 max CC | v1.2 max CC | v1.3 erosion | v1.2 erosion |
|---|---|---|---|---|
| 1 | 4 | 4 | 0.00 | 0.00 |
| 2 | 7 | 7 | 0.00 | 0.00 |
| 3 | 7 | 7 | 0.00 | 0.00 |
| 4 | 9 | 9 | 0.00 | 0.00 |
| 5 | 5 | 12 | 0.00 | 0.69 |

Both passed 15/15 hidden checks at step 5 with the same SLOC (74). At step 5 the v1.3 agent split the four-channel if-chain into per-channel handlers and a dispatch table, citing the existing ladder; the v1.2 agent appended a fourth branch and `send_alert` reached CC 12. Erosion here is the share of CC × √length in functions with CC > 10. Duplicate share stayed 0 for both. One trajectory cannot separate the rule's effect from run-to-run variance; repeated paired trajectories are still needed. The rule 2/4/10 wording was tightened (no change in meaning) between steps 2 and 3 of the v1.3 run.

**Historical replay on a large real repository (casim, ~600 Python files, strict types and ratchet guards).** Three real past commits were replayed: each agent got the parent commit in its own worktree and the original request, and had to pass the project's full `make check`. Requests: merge `xlsx export` into `doc export` (17b592c), add `company get --local` plus homophone candidates (cca9e1f), sheet-aware outline and `--sheet` for multi-sheet workbooks (f7c6b8a). All six runs passed `make check`, so the comparison used a blind reviewer per task who saw two diffs labelled A/B and the base commit, and judged six criteria.

| Task | Overall (blind) | "Structure left for the next change" | Why v1.3 lost, if it did |
|---|---|---|---|
| merge export commands | v1.3 (medium) | v1.3 | — |
| `company get --local` | v1.2 (medium) | v1.3 | reviewer penalized a new third-party dependency; the owner considers that acceptable |
| multi-sheet workbook, run 1 | v1.2 (medium-high) | v1.3 | v1.3 skipped the SCHEMA documents the project requires to change with the code |
| multi-sheet workbook, run 2 (after rule 2 named contract documents) | v1.2 (slight, medium) | v1.3 | v1.2 made the JSON keep-guarantee mechanical; v1.3 relied on list size |

v1.3 won the structure criterion in all four comparisons, which is the behavior the new rules target. Its losses came from places the rules did not cover; the first (contract documents as in-step sites) led to the rule 2 wording now in this version and was fixed on rerun. Mechanical metrics (files touched, lines, cyclomatic growth in touched files, guard baselines, guard-allow markers) were close in every pair; casim's own ratchet guards bound both versions, consistent with the view that durable enforcement belongs in CI. Token cost was within ±10% per pair. The run-2 workbook agent used a SKILL.md whose rule 4 briefly carried a clause against new third-party dependencies, reverted at the owner's request; it is unlikely to have affected that task. One run per condition per task: directional, not a measured improvement.
