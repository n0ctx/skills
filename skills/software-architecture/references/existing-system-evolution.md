# Existing-System Evolution

**Read when:** restructuring an existing system, extracting or merging modules or services, migrating a public API, changing state ownership, or replacing an architectural mechanism. Skip for greenfield designs and for feature work inside current boundaries.

## Diagnose the pressure

- Trace the actual change path and dependency direction. Identify what makes a specific change expensive: coupled edits, scattered ownership, conflicting models, or a deployment bottleneck. If change history or incident records exist, use them. Do not infer the pressure from directory names or file length.
- Name the constraint: faster independent changes, isolation, compliance, scaling, reliability, or lower cognitive load. If none of these is concrete, keep the current structure.
- Compare leave as is, strengthen an in-process boundary, and extract a separately deployed boundary only when those are real options. Count deployment, ownership, cross-boundary contracts, tracing, failure handling, and local development cost. Cleaner directories are not a driver.

## Design a feasible transition

1. Identify authoritative data and state ownership before and after, including how writers and readers are routed during the transition.
2. Name the first small end-to-end slice and the observable condition for advancing. Separate irreversible data transforms from reversible traffic routing.
3. If old and new paths coexist, state how compatibility and consistency are maintained, how divergence is detected, and when the old path is removed. Do not leave permanent dual writers as a migration convenience.
4. For each consequential boundary, define cutover, what is monitored, and whether recovery is rollback or roll-forward. Do not promise rollback after irreversible writes, destructive schema changes, or external side effects.
5. Keep contracts and regression checks across the migration. Do not change behavior and structure in the same step unless both are necessary and the step is testable.

## Challenge the new structure

Run one realistic next change through the proposed design: which modules, owners, data transformations, and deployments must change? If the new structure moves that cost into adapters, duplicated schemas, network calls, or operational handoffs without reducing it, reconsider the split.
