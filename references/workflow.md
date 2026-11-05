# Staged design & build workflow

Applies to complex tasks (multi-screen, from scratch, bespoke assets, finished-product quality). Medium tasks compress the stages; simple tasks skip this file.

## Why stages

Building all screens at once spreads attention evenly: everything works, nothing looks finished. The alternative: set direction, finish one block to production quality, use it to prove the direction and derive rules, then bring everything else up to it.

Stages are quality gates with visible pass/fail criteria, not report checkpoints. Design dimensions are NOT build order: color, type, shape, material are decided together within a stage, never "all colors then all fonts."

## Compression by task level

- **Complex**: all six stages + persistent design record.
- **Medium**: direction set inline in chat (still writes the record, minus progress log); composition+sample merged into "focal area first"; extension still holds the sample's quality bar; polish+acceptance merged into one review round.
- **Single page carrying the whole identity** (e.g. an opening screen): stages 1–3 in full.

## Stage overview

| # | Stage | Output | Pass gate |
| --- | --- | --- | --- |
| 1 | Direction | Design record v1 | Can state memory point + why it belongs to this work; survives the similar-prompt test |
| 2 | Composition | Grayscale page with real content | Thumbnail shows clear hierarchy; longest content fits; key actions findable |
| 3 | Core sample | One region at delivery quality | Looks finished to an outsider; reusable rules extracted into the record |
| 4 | Module extension | Modules one by one | Each passes side-by-side comparison with the sample |
| 5 | Polish | Cross-module fixes | Consistency + detail checks clean |
| 6 | Acceptance | Verified in real environment | Main flows, target widths, failure fallbacks all tested |

Do not wait for user confirmation between stages. Ask only at stage 1 when two reasonable, incompatible interpretations of the work's positioning exist.

## Stage details

### Stage 1 — Direction

Answer four things, write them into the record:

1. **Interface identity**: what object/system is this in-story, made by whom, read by whom (see design-knowledge.md §1).
2. **Memory point**: the one image or feel the user should remember after closing the page; must come from this work's specific setting.
3. **Art direction**: color roles, type voices, shape/line grammar, light & material, image plan, motion character — decided together, cross-referenced.
4. **Exclusions**: the genre formulas and generic defaults this specific work must avoid. This is a per-work list, not a global ban list.

**Similar-prompt test**: would another ordinary request in the same genre produce nearly the same design? If yes, the direction is a genre average — go back to characters, places, events, props for differentiation.

**Asset plan** (same stage): list every concrete-art item (key visual, characters, scenes, key objects) with purpose, ratio, crop, transparency needs, and source (existing → AI → web). Write the single shared style description (medium, brushwork, light direction, palette, clarity) — every later generation request reuses it verbatim. Prep sample assets only; no batch production. Verify availability before committing: if no AI tool and no licensed web assets fit, choose a direction the collectible assets can actually support, or tell the user now.

### Stage 2 — Composition

- Build all major regions with real content: actual-length text, longest names/numbers, empty states, multi-item lists. Image slots get size/crop-correct placeholders (color blocks or quick concept sketches) — they validate composition only.
- Handle only position, area, value masses, reading order, key-action placement. No decoration or material yet.
- Place illustration placeholders at final area and layer: where is the full-bleed base, where does the character cross panels. Do not pre-shrink art into a top banner.
- Render at target widths, including narrow/embedded, and screenshot.
- **Gate**: thumbnail/squint shows 2–3 value masses with the focal point in the planned place; reading order matches importance; no overflow on longest content; primary action needs no searching.

If composition fails, do not proceed. Detail cannot rescue bad big relationships.

### Stage 3 — Core sample

**Pick the region** that best represents the work's identity AND is hardest — usually where key visual meets primary reading/operation (opening + first interactive panel, or one panel containing all states). Never the easiest corner.

**Finish to delivery quality**:
- All concrete art replaced with final illustration assets (generated or collected), cropped, graded, edge-blended. No code-drawn scenes/people/objects remain.
- Type: fonts, weights, line-height, tracking set; long Chinese text actually typeset.
- Material, light, borders, ornament per the art direction.
- Full interaction states: hover, focus, active, disabled, loading, empty, selected.
- Motion, target-width adaptation, Chinese line-breaking handled.

**Gate**:
- An outsider seeing a screenshot would assume it's a finished product, not programmer-made game UI.
- No element in frame is visibly cruder than the rest.
- Reads as a picture at thumbnail size (mostly illustration, not dark panels + text); no collage of boxed images.
- Clearly belongs to this work, not any same-genre work.
- Readability and operation not sacrificed.

**Extract rules**: after the sample passes, derive reusable rules from the actual artifact and write them into the record's token registry: color variables + roles, type scale, line widths, radius/cut grammar, shadow & light direction, material usage, motion durations + easing. Rules extracted from a finished artifact beat rules invented upfront. **Then freeze the registry** (anti-drift rule 2).

**Rollback**: if two fix rounds still fail to look finished, diagnose. If direction or assets can't support it, return to stage 1 and tell the user. Do not silently degrade to plain styling, and do not polish code-drawn art as a substitute for missing assets.

### Stage 4 — Module extension

Group by function + visual relation (opening & onboarding, main play screen, archive tabs, modals/toasts). One module at a time:

1. **Local design**: what in-world format this module's info takes. Reuse the sample's carrier and grammar; differentiate via layout, typography, assets — do not invent a new prop per module. Vary composition with content meaning; don't apply one card layout everywhere.
2. **Implement.**
3. **Screenshot and compare side-by-side with the sample**: same world, same quality bar.
4. **Fix, then next module.**

**Module pass criteria**: no default components or browser-native styling; no placeholders or code-drawn concrete art; full states; matches sample quality bar.

**Watch for three drifts**:
- New colors/radii/shadows sneaking in (check against the registry).
- All modules converging to one layout.
- Later modules getting plainer (the classic opening-gorgeous, body-plain collapse).

If a module exposes a gap in the language (sample didn't cover tables/long lists), extend the registry in the record first — and fix the sample if needed — before continuing.

### Stage 5 — Polish

Screenshot all screens + key states side by side, four passes:

1. **Consistency**: light direction, line width, radius/cut, color temperature, asset style & sharpness, type roles.
2. **Detail**: alignment, border junctions, image edges, text-image spacing, punctuation/wrapping, scrollbars, focus rings, selection color, form controls.
3. **Deletion**: remove ornaments that carry no info and serve no mood; remove props/graphic visibly cruder than the rest. Refinement comes from restraint, not quantity.
4. **Motion & feedback**: consistent rhythm; no missing or excessive animation.

Composition- or direction-level problems found here go back to stage 2/1 — don't paper over them with detail.

### Stage 6 — Acceptance

- Test in the real runtime; if embedded in chat/host page, test embedded, not standalone.
- Walk main flows at target widths.
- Check font/image load-failure fallbacks, console errors, re-render performance.
- No leftover placeholders. If an asset truly can't be obtained, list it in delivery with the required generation spec.
- With subagent + vision available, have a fresh-context reviewer look only at screenshots and answer: "does this look like a production with dedicated art polish?" plus their three roughest spots. Do NOT let the reviewer score by counting metaphors/props — that rewards prop-stacking. Self-review runs lenient; independent review catches what habit hides.

## Visual review method

Screenshot-based, largest first, per round:

1. **First glance** (thumbnail ~1s): where does the eye land; is it the planned focus; is there something memorable and specific to this work.
2. **Squint**: 2–3 value masses, hierarchy holds, density varies; mostly illustration vs mostly dark panels.
3. **Cover the title**: still this work, or any same-genre template.
4. **Side-by-side**: one art direction across regions (light, line, material, style, temperature).
5. **Actual size**: Chinese body type size/contrast/line-length/leading/mixed CJK-Latin.
6. **Edges**: alignment, overflow, image edges, mask transitions, browser-native chrome, empty/loading states.
7. **Interaction**: hover/focus/active/disabled/loading feedback and motion timing.
8. **Target width**: narrow/embedded layout, touch size, no clipped text.

Priority: direction > composition > core art > consistency > readability > detail. Fix only the top 1–3 issues per round; re-screenshot. Max two rounds per stage.

Before each fix session, save a rollback point (commit/backup). If a fix makes things worse, roll back; don't stack fixes on a bad result.

If the main model can't see images, reuse a vision tool or delegate to a vision-capable subagent; report only what was actually verified.

## Rollback rules

| Trigger | Return to |
| --- | --- |
| Sample still not finished after two rounds, cause = direction/assets | Stage 1 |
| Multiple modules don't fit composition or info hierarchy | Stage 2 |
| Module needs language the sample didn't cover | Extend record; update sample if needed |
| Polish finds hierarchy/focus errors | Stage 2 |
| Same issue fixed twice without improvement | Stop; re-diagnose cause; no more same-class fixes |

Rollback redoes only the affected part; finished parts stay.

## Design record

For any cross-session or multi-module task, keep one short record next to the frontend code (or in the project's existing design doc). Its job is continuity of intent across stages and sessions, not a user-facing report. One page max; every line checkable yes/no; rewrite in place when rules change — no changelog.

```markdown
# <Work> Design Record

## Concept
- Interface identity: <object/system>, made by <whom>, read by <whom>
- Memory point: <one sentence>
- Pillars: <2–3 checkable principles>
- Exclusions: <genre formulas & defaults this work avoids>

## Art direction (frozen after sample passes)
- Shared style description: <medium / brushwork / light direction / palette / clarity>
- Color roles: <bg / surface / text / accent / state + accent usage limits>
- Type voices: <display / body / data / in-world>
- Shape & line: <line widths, radius/cut levels, ornament motifs>
- Light & material: <light direction, materials and where used>
- Image: <asset list with source, license, treatment; placeholders remaining>
- Motion: <character, duration range, easing>

## Token registry (the only allowed values; frozen after stage 3)
- colors: ...
- radii: ...
- line-widths: ...
- type scale: ...
- spacing scale: ...
- shadows: ...
- motion durations/easing: ...

## Progress
- Sample: <region, status, screenshot path>
- Modules: <name — done / in progress / todo + known issues>
```

## Cost control

- Stages are gates, not report points. Proceed continuously; no per-stage reports or waiting.
- Screenshots serve the current decision only; reuse one browser session.
- Asset generation/collection in batches per the asset plan: sample first, then per module. No batch decorative art unrelated to composition.
- No new build tooling, services, or dependencies for this process.
