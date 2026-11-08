# Durable Decisions and Architecture Fitness

**Read when:** the task asks for an ADR, a consequential choice must be handed across sessions, or the task asks for an enforceable architectural guardrail. Do not read it for every architecture discussion.

## Which decisions merit recording?

Record a choice when it is hard to reverse, materially changes ownership or contracts, has a non-obvious trade-off, or a later change would reasonably undo it without the rationale. A routine library choice or an obvious local implementation detail does not merit an ADR.

Use the repository's existing ADR, RFC, or architecture-doc convention. Do not invent a second format. Status is proposed unless the decision-maker has accepted the choice. Supersede an earlier decision with a new record or the project's existing lifecycle. Do not silently rewrite history.

## Fallback record

Use this shape only when the repository has no decision-record format:

```markdown
# Decision: <specific structural choice>
Status: Proposed | Accepted | Superseded

## Context and drivers
Which observed problem, constraint, or quality scenario makes this decision necessary?

## Options and decision
Which viable alternatives were compared? Which was selected, and why?

## Consequences
What becomes easier, harder, or riskier? Who bears the cost?

## Validation and revisit trigger
What check would expose a wrong assumption? Under what condition is the decision reconsidered?
```

If the reasoning for a historical decision is unknown, say so. Do not reconstruct a confident justification.

## Make expensive boundaries resistant to drift

- Add a fitness check only for a specific failure that a tool can fail: a forbidden import edge, a dependency cycle, contract schema compatibility, access-control location, an ownership invariant, deployment compatibility, or a measured operational threshold.
- Prefer existing lint, type, test, or CI. Show that a known violating example fails the check. A green command without that negative control is weak evidence.
- Written guidance alone does not stop gradual erosion across many changes; in an iterative-extension benchmark, quality instructions improved the first version but not the rate of later decay. For duplication, complexity concentration, or dead code, prefer a baseline ratchet: record existing violations, fail only on new or worsened ones, and fail when a fixed violation is still listed in the baseline.
- If existing violations are substantial, introduce the check without blocking unrelated work. Do not add custom tooling when the repository already has an equivalent gate.
- Project-specific constraints belong in that repository's docs, tests, or config, not in this skill.
