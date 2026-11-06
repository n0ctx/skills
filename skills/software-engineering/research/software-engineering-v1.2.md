# v1.2 design rationale (maintainer only)

**Scope:** A versioned engineering Skill should improve a working coding agent's decisions, not re-teach SOLID/KISS, standard testing categories, or language syntax. Current model-specific behavior improvements are *hypotheses* until measured with the intended model and harness.

## What changed from v1.1

| Decision | Why it might help | Possible failure/regression | How to test |
|---|---|---|---|
| Put a concrete input → owner/state → side effect → output mental model in core | Prevent feature work that edits one layer without integrating callers/results | Extra exploration on trivial edits | P1, N10, C-minus-method |
| Demand an explicit local contract only for new interfaces/state | Prevent multiple state owners and ambiguous error semantics | Overdesign ceremony, needless interfaces | P2/P3; inspect actual artifacts |
| Prefer coherent working slices over scaffolding-first | Expose integration problems earlier | May hinder necessary foundation-first changes | P1/P4 plus a foundation-required counterexample |
| Merge positive construction with existing guardrails | Avoid Skill becoming just a checklist of prohibitions | Larger initial prompt harms simple tasks | A/B/C; tokens and tools |
| Keep only diagnosis and high-risk references | Different triggers make selective reads plausible | Misrouting, never-read useful details | Reference-routing audit and inlined condition |
| No general architecture file yet | Prevent a never-used reference and avoid splitting responsibilities prematurely | Some nontrivial design tasks may need extra guidance | P9 and architecture task audits |
| Root `engineering-skills/skills/` with independently discoverable Skills | Future Software Architecture Skill can be added without a global mega-Skill | Prior root-clone installation breaks | Installation and shadowing smoke tests |

## Sources used for format and claims

- [Original n0ctx/software-engineering](https://github.com/n0ctx/software-engineering) — authoritative published v1.0 baseline; the v1.1 local candidate was used to retain later maintenance and reference-routing changes.
- [Hermes Agent — Skills System](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md) — external skill directories, duplicate name precedence, and skill loading behavior.
- [Agent Skills specification](https://agentskills.io/specification) — independent `SKILL.md` packages and progressive disclosure.
- [Microsoft Agent Framework, skills](https://learn.microsoft.com/en-us/agent-framework/agents/skills) — examples of independent subdirectory discovery and optional references.
- [SWE-Skills-Bench](https://arxiv.org/abs/2603.15401), [SWE-Maintain](https://arxiv.org/abs/2610.14768) — motivate restrained instructions and testing maintainability across successive agent changes; neither proves these specific rules help.

## Exclusions

- No architecture framework, speculative architecture reference, or placeholder skill.
- No universal function/file-length ceiling, naming syntax, or prescribed asymptotic bound. The repository's own lint/static rules and actual load patterns are the stronger authority.
- No mandatory planning/TDD/worktrees/subagents/full-test-suite on routine changes.
- No new global identity, task authority, reporting contract, or workflow router: those belong to SOUL or harness/project configuration.
- No auto-edit of the user's hosted GitHub repo; deliver as a candidate snapshot with explicit migration instructions.
