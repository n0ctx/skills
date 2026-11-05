---
name: tavern-aesthetic
description: Use for tavern-style page and frontend design.
---

# Tavern Aesthetic — Immersive Narrative Frontend Design

## What this skill produces

A working UI that reads as an artifact from the story world — not a re-skinned dashboard and not a pile of generic game-HUD props. The bar is the polished front-end card: one glance identifies the work, every surface shares one art direction, details are finished, and interaction feels natural.

Polish ≠ complexity. Polish means every visible choice is intentional and every visible region meets the same quality bar.

This skill covers visual design and implementation method. It does not depend on SillyTavern, any helper plugin, MVU, or any framework. Reuse the project's existing stack, components, assets, and interaction patterns. If the user asks for a design only, do not touch code.

## References (read on demand, never all upfront)

- `references/design-knowledge.md` — decision guide by dimension (narrative identity, color, type, shape, light/material, image, layout, components, motion, adaptation) plus failure-mode tables. Consult the section matching the decision at hand.
- `references/workflow.md` — staged process, pass/fail gates, review method, rollback rules, design-record template. Read before any medium or complex task.
- `references/asset-sources.md` — sources and license checks for illustration, texture, icon, font. Read when collecting assets online.
- `references/research.md` — evidence and limitations behind this skill. Not needed for execution.

## Task levels

Judge by design difficulty, not code volume:

- **Simple**: one component, a detail fix, a small feature inside an existing visual language. Reuse the language; screenshot-check once after implementing.
- **Medium**: a single page/panel or one redesign of an existing screen. Do a brief direction-setting, build the focal area first, then complete the page; 1–2 review rounds.
- **Complex**: multi-screen flow, gamified system, build from scratch, needs a bespoke key visual, or the user asks for finished-product quality. Run the six stages in `workflow.md` and keep a design record.

## Anti-drift rules (binding)

These exist because multi-turn execution drifts. Follow them literally:

1. **Design record is the single source of truth.** For medium and complex tasks, create it (template in `workflow.md`) at direction-setting time and re-read it at the start of every subsequent turn/module. Any new color, radius, font, or motion value must be added to the record's token registry before use. If a value is not in the registry, it is not allowed in code.
2. **Freeze the token registry after the core sample passes.** Later modules may only reuse registered tokens. New tokens require an explicit note in the record explaining why the existing set cannot express the need.
3. **Every module is screenshot-compared side-by-side with the core sample before moving on.** No exceptions; verbal comparison is not enough.
4. **Max two fix rounds per stage.** If still failing, roll back and diagnose per the rollback table in `workflow.md` instead of layering more fixes.
5. **One active direction at a time.** Do not keep alternative directions alive across turns. Pick one, record it, discard the rest.

## Core principles

1. **Design for the work, not for the genre.**
   - First answer: what object or system is this UI inside the story, who made it, who reads it, when.
   - Then pick one memory point that belongs to this specific work.
   - Visual identity comes from concrete characters, places, era, factions, events, props. Genre formulas (post-apoc = black/yellow radar; cultivation = ink-green + gold) are only starting points and must be made specific.
   - Self-test: hand the same genre's generic request to an agent — if it would produce nearly the same UI, the direction is not specific enough.
   - Compare a few directions internally, deliver exactly one. Do not list options to the user for routine tasks.
2. **One concept governs every design decision.**
   - Color comes from materials and light sources; type from writing/printing methods; shape from craft; motion from the object's physical actions.
   - Related dimensions are decided together, not sequentially ("all colors first, then all fonts" is wrong).
   - For any element you must be able to state which part of the concept it expresses.
3. **Concrete art uses illustration assets; code-drawn art is placeholder only.**
   - People, scenes, objects: final version uses illustration assets. Source order: existing project assets → AI generation → licensed web collection.
   - CSS/SVG-drawn scenes, people, objects are allowed only for composition/concept validation and must be replaced before delivery (no later than the core-sample stage for complex tasks). They read as programmer-art and drag the whole UI down.
   - Code owns the interface itself: layout, typography, borders, textures, ornamental patterns, icons, abstract and data graphics.
4. **Illustration leads the composition.**
   - The illustration sets the layout's center of gravity; text and components arrange around it. Never shrink it into a top banner or a card thumbnail.
   - Every main screen must read as a picture: squinting, the screen should be mostly illustration, not dark panels + thin lines + text.
   - Art presence continues into functional pages (illustration as low-contrast layer under panels, character crossing panel edges, scene shifting with time/location). "Gorgeous opening, then plain dark form pages" is the most common quality collapse.
   - One hero image per screen. Secondary images blend into the same picture or form a uniformly treated set; never line up differently-sourced images in boxes side by side.
5. **Information adopts in-world formats, with prop restraint.**
   - Information uses the world's native formats and vocabulary (ledger columns, roster layout, in-world verbs/nouns) and reveals at narrative pace.
   - One primary carrier for the whole UI. Do not give every module a different CSS-simulated prop (tape notes, crooked stamps, tags, abacus beads) — stacked props look cheap.
   - Restrain props and ornaments, not pictures and color. Space freed from props goes to illustration and typography, not to dark text forms.
   - Not everything is "label: value" + progress bar. Flow pages (onboarding, settings) are not forms; key options can carry illustrations.
6. **One uniform quality bar.**
   - Effort may be uneven: the focal area gets the best assets and most detail.
   - No visible region may fall below the bar. Anything drawn must match overall precision; if it can't, replace with illustration or express it via typography/abstract graphics.
   - To cut cost, simplify within the same language — never fall back to default components, browser-native styling, or placeholder imagery.
7. **Reading and operating come first.**
   - Chinese body text: ≥14px (15–17px typical), line-height 1.6–1.9, line length ~20–40 chars, body contrast ≥4.5:1.
   - Mood is carried by color temperature, light, material, motion; text and numbers stay crisp.
   - No tiny text, low contrast, or meaningless English as "premium" shorthand.
   - Images and textures never sit on top of body text or click targets.
   - Full interaction states, keyboard operable, adapted to target width.
8. **Defaults must be chosen, not inherited.** Keep a default font, palette, component-library style, or browser scrollbar/focus-ring only if deliberately selected. The common AI game-UI kit (beige paper + dark slate, red crooked stamp, small tags, hex step nodes, radar chart) is also a default. Swapping one trendy default for another is still a default.
9. **Engineering restraint.** Reuse existing code, deps, and assets. Generate/collect assets per the asset plan only. No new heavy dependencies, no asset pipeline, no backend refactor.

## Execution flow

### 1. Understand the scene

Confirm: genre; character/world specifics; target mood; page purpose; core info and actions; target device; host environment (e.g. embedded in chat).
Review existing code and assets. User references: extract the art technique, not the picture. Proceed without asking when no critical ambiguity exists.

### 2. Set direction (all medium+ tasks)

Write into the design record:
- Interface identity: what object/system, made by whom, read by whom.
- Memory point: one sentence, must come from this work's specifics.
- Art direction: medium, brushwork, light direction, palette, clarity — one shared style description reused verbatim in every later generation request.
- Exclusion list: the genre formulas and defaults this work must avoid.
- Asset plan: every concrete-art item with purpose, ratio, crop, transparency, source (existing → AI → web). Verify sources actually exist before committing; if neither AI nor licensed web assets can support the direction, say so now.

### 3. Build

Per task level:
- Simple: implement, screenshot, fix worst 1–3 issues, done.
- Medium: focal area to full quality → complete the page → one combined review pass.
- Complex: follow the six stages in `workflow.md` (direction → composition → core sample → module-by-module extension → polish → acceptance). Stages are quality gates, not report checkpoints; proceed continuously. On systemic problems, go back to the relevant stage and redo only the affected part.

During build:
- Reuse project code and interaction patterns.
- Decorative fonts for titles only; verify CJK glyph coverage and set fallback stacks.
- All states: hover, focus, active, selected, disabled, loading, empty, error — visually consistent.
- Motion serves interaction and mood; same duration/easing family across the work; respect `prefers-reduced-motion`.

### 4. Integrate assets

- Place the hero image first, then arrange supporting info.
- Unify assets via crop, mask, color grading, grain, edge blending, unified light direction; leave quiet zones for text.
- Mixed-source styles conflict → grade to match; still conflicting → replace, don't force.
- Assets are local project files, not hotlinked URLs. Honor licenses/attribution.

## Visual review (screenshot-based, largest issues first)

1. **First glance** (thumbnail, ~1s): where does the eye land; is it the planned focal point; is there something worth remembering.
2. **Squint**: value structure reads in 2–3 masses; is the screen mostly illustration or mostly dark panels.
3. **Cover the title**: still recognizable as this work, not any same-genre template.
4. **Side-by-side**: all regions look like one art direction (light, line, material, palette, type).
5. **Actual size**: Chinese body text comfortable.
6. **Edges**: alignment, overflow, browser-native chrome, empty states, no leftover code-drawn art or placeholders.
7. **Interaction**: states and motion.
8. **Target width**: narrow/embedded layout.

Fix priority: direction > composition > core art > consistency > readability > detail. Fix only the top 1–3 issues per round; re-screenshot after each round. Max two rounds per stage; keep a rollback point before each fix session.

Diagnose the cause class before fixing: missing core art / weak concept identity / weak composition hierarchy / style conflict / readability or layout error. Each has a different fix.

If the main model cannot see images, reuse an existing vision tool or delegate review to a vision-capable subagent. Report only what was actually verified.

## Acceptance checklist (all must be yes)

1. Is there a memorable first-glance element that comes from this work's own content?
2. With the title covered, would this UI still not be confusable with a same-genre template?
3. Does the most important visual area use illustration assets at a precision matching its status — no code-drawn figures, no obviously cruder element in frame?
4. Do assets, type, components, and background read as one production? Is the plainest region still pictorial and on the same quality bar?
5. Is the page clear, operable, adapted to target width, with function never sacrificed to visuals?

## Delivery

- Deliver runnable results first.
- Complex tasks: briefly state core art concept, assets actually used (with license notes), main fixes made during review, verification results, and anything still placeholder.
- Simple tasks: state key changes only.
- No long design documents to the user. The design record exists for cross-stage/cross-session continuity, not as a user report.
