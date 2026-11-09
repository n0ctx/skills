---
name: software-architecture
description: "Use when designing or changing system structure, including implementation tasks involving new subsystems, responsibility or state ownership, module boundaries, dependency direction, structural refactoring, or migrations. Also use for architecture-only discussion, review, and trade-off analysis. Not for changes confined to existing boundaries."
version: 1.1.3
metadata:
  hermes:
    category: development
    tags: [architecture, system-design, boundaries, tradeoffs, migration, decisions]
---
# Software Architecture

Decide system structure and trade-offs. When the task includes writing, modifying, or refactoring code, also load `software-engineering`, unless it is already active. If both structural decisions and code changes are apparent from the request, apply both skills from the outset rather than finishing the design first. Loading either skill does not replace the other. A design-only or review-only request does not authorize code changes.

## When to use

Use for a new subsystem, a change to responsibility, state ownership, or dependency direction, restructuring a live system (including implementing the restructuring), a comparison of structural options, or an architecture recommendation that does not require code.

Do not use for a clear local bug, a configuration or CLI change, or a feature that fits the current module boundaries.

An architecture question may end with a recommendation not to restructure.

## Decision discipline

1. **Start from architectural drivers, not patterns.** Identify the few functional flows, constraints, and quality attributes that can change this decision (reliability, changeability, latency, security, cost, team capacity). When drivers conflict, rank them. State a consequential quality claim as a scenario: under what condition, what must happen, and what counts as success. If a number or requirement is not in the drivers or the repository, label it an assumption. Do not turn it into a requirement.

2. **Ground the current system.** In an existing codebase, inspect the relevant entry points, runtime and data flows, owners, real dependencies, deployment shape, and previous decisions before prescribing structure. Separate verified structure from documents, intended structure, and guesses. An old diagram is not proof. Code that grew through many generated changes may reflect accretion rather than any decision: do not infer intent from its current shape, and treat parallel implementations of one responsibility as evidence of a missing owner rather than a design to preserve. In greenfield work, identify the smallest deployable structure that meets the known drivers before adding optional surfaces.

3. **Draw boundaries around ownership and change.** For each proposed component or service, name its responsibility, authoritative state owner, inbound and outbound contracts, and allowed dependencies. Trace one important end-to-end flow and its failure path across those boundaries. Split by a coherent business or operational responsibility, not by folder size, pattern fashion, or imagined reuse. Keep related changes together unless a ranked driver requires separation.

4. **Compare real alternatives against the same drivers.** Include retaining or strengthening the current structure when that option is credible. Consider an in-process boundary before a separately deployed one. Compare only plausible options, and only on the dimensions that decide: correctness, coupling, operational burden, cost, migration risk, reversibility. State what is sacrificed, name the assumption that would flip the ranking, and recommend one approach. Do not invent extra alternatives to fill a list. Do not claim that one structure maximizes every quality attribute.

5. **Test the choice at its weak point.** Run the few scenarios that could reverse it: growth, failure, conflicting writes, a security boundary, or a future change, whichever the drivers make relevant. Check that ownership, recovery, and the critical contract still hold. If an assumption could reverse the ranking, name the cheapest check that could falsify it: a targeted prototype, a representative load test, a dependency check, or an independent review. A plausible diagram is not that check.

6. **Treat evolution as a design constraint.** When changing a live system, account for compatibility, sequencing, cutover, data ownership during transition, rollback limits, and retirement of the old path. For a split, merge, rewrite, or migration, read [existing-system evolution](references/existing-system-evolution.md). A target structure without a feasible transition is incomplete.

7. **Do not treat a proposal as an accepted decision.** If the task asks for a durable record, write it in the repository's existing decision location, with status proposed unless the decision-maker has accepted it. Make the record discoverable from where agents and new contributors load project context, for example a one-line pointer in the repository's existing agent instruction file, because a record nobody loads does not stop the next change from undoing the decision. Add an enforceable check only when existing lint, types, tests, or CI can fail a specific boundary violation. Do not add a policy file or CI job to formalize a diagram. Read [decision records and fitness](references/decision-records-and-fitness.md) only for an ADR, a cross-session handoff, or an enforceable guardrail.

## Conditional depth

- If the design crosses independent failure domains, uses asynchronous events, shares durable state across processes, or depends on delivery or consistency behavior, read [distributed state and failure](references/distributed-state-and-failure.md). Do not read it for ordinary in-process modules.
- Read a reference only when its trigger matches. An uncomplicated trade-off needs none.
- Do not impose microservices, DDD, Clean Architecture, CQRS, event sourcing, ADRs, diagrams, spikes, or a full design document as ceremony.

## Result

Separate **observed**, **assumed**, and **proposed**. State the recommendation, the trade-off that decided it, and the assumption that would reverse it. If the system already exists, state a viable transition. If the recommendation changes a boundary, name the owner, the contract, and one failure path. Do not claim an architectural property without a check that could fail.
