# Diagnosis and recovery — only for uncertain or repeated failures

**Do not load for routine fixes with an evident cause and direct observable check.** Use this when a first fix fails, failure is intermittent, symptoms conflict, performance regresses, or a root cause is not established.

## Decision points
1. **Is the problem still present?** Determine whether the full requested behavior fails on the actual branch, inputs, and environment. A stale ticket, partially fixed issue, and environment-only failure require different responses. No code modification may be correct.
2. **What observation discriminates causes?** Capture expected vs actual behavior and the smallest useful real test, trace, or reproducer. If multiple layers can produce the symptom, identify the boundary that distinguishes them before editing. An error message identifies a symptom, not necessarily its owner.
3. **What would falsify the hypothesis?** Change one causal variable, or inspect a known-good/bad contrast. Do not respond to timeouts, races, and exceptions by adding arbitrary retries, waits, fallbacks, or suppression without evidence about the underlying failure.
4. **Did the attempted fix actually resolve the original signal?** Re-run the original reproducer or check the changed observable behavior. A different green test does not close the loop.
5. **If it failed, what changed in the causal model?** Identify the new observation and revise the hypothesis before further edits. When no reasonably discriminating experiment exists, report the uncertainty rather than simulating progress.

## Special cases
- **Pre-existing failures:** compare an appropriate baseline if practical; do not claim all failures are caused by the current change, or dismiss new ones as pre-existing without evidence.
- **Flaky tests/races:** an isolated green rerun is not a fix. Evaluate repeated behavior and relevant state/order conditions; avoid simply raising retry counts.
- **Performance:** compare equivalent representative workloads and environments; investigate measured bottlenecks, not only code size or synthetic microbenchmarks.
- **Environment failures:** distinguish missing credentials, unavailable services, runtime versions, and wrong working directory from application defects; never alter application semantics to mask an environmental condition.

**Exit:** The original requirement is satisfied, a verified no-op is appropriate, or the remaining blocker is supported by evidence. Do not continue indefinitely to satisfy a self-imposed procedure.
