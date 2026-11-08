# v1.1 design rationale (maintainer only)

| Change | Evidence | Possible regression |
|---|---|---|
| Rule 2: accreted structure is not evidence of a decision; parallel implementations of one responsibility point to a missing owner | SlopCodeBench v2 (arXiv:2603.24755): agent trajectories accumulate duplication and erosion without design discipline. Storey (arXiv:2603.22106): intent debt, where the reasons for a structure are never recorded | Dismissing real but undocumented decisions; the rule asks not to infer intent, not to assume there was none |
| Rule 7: make the record discoverable from where agents load project context | BTH maintainability survey (N=31): over three quarters of respondents moved from correcting agents case by case to standing steering files holding conventions and architecture decisions | Editing an agent instruction file the user did not expect; limited to a pointer in an existing file, only when a durable record was requested |
| Fitness reference: prefer baseline-ratchet checks for erosion | SlopCodeBench: quality prompts lowered the starting point but not the degradation rate. Sun et al. (arXiv:2511.10271, JSS 2026): prompt-based control of non-functional quality is unstable | CI friction; the existing rule against blocking unrelated work still applies |
