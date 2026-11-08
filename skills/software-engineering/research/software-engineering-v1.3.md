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
