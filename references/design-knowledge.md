# Design knowledge base

Consult the section matching the current decision; never read end-to-end.

- **Setting direction**: §1, §7.
- **Composition**: §3.
- **Building sample / extending**: the dimension you're working on.
- **Review**: §8 failure-mode tables.

Dimensions are lenses for analysis, not build order. Related dimensions are decided together. Examples illustrate reasoning only — never copy their palettes, fonts, props, or numbers as defaults.

## Contents

1. Narrative identity & integration (identity, formats, copy, mood)
2. Visual language (color, type, shape, light/material, image & icons)
3. Space (composition, scale/spacing, density)
4. Information & components (hierarchy, themed components)
5. Interaction & motion
6. Adaptation, host environment, accessibility
7. Cross-dimension coordination & tradeoffs
8. Failure-mode quick reference

---

## 1. Narrative identity & integration

The difference between a polished narrative UI and "a webpage with a genre reskin": the former first answers "what is this UI inside the story" and derives color, type, layout, components, interaction from that answer; the latter starts from a generic layout and adds genre decoration.

### 1.1 Deriving visual identity from the work

Model-chosen directions default to genre averages (post-apoc = black/yellow warning tape; cultivation = ink-green + gold trim; cyberpunk = neon cyan/purple). Escaping defaults means starting from the specific work, not swapping to another fixed style.

1. **List concrete elements**: protagonists' identity, occupation, habits, taste; place and era; tech level; factions and institutions; key props; core conflict; the role the user plays.
2. **Find the in-world carrier**: who records this info, in what material and format, viewed on what occasion.
3. **Write the genre's first reflex, then find a more specific version.** Don't take its opposite — the opposite is usually another default.
4. **Pick one memory point**: a concrete image or feel belonging to this work — the secrecy stamp on a dossier cover, incense burning down each turn, a character's margin notes, a star chart visible only at night.
5. **Derive the language from the memory point**: color from materials & light; type from writing/printing; shape from craft; texture from wear and age; motion from the object's physical action.
6. **Run the similar-prompt test** (§Direction in SKILL.md).

Worked derivations (do not reuse):
- Post-apoc default: black/yellow + radar. If the protagonist maintains an old radio station alone in ruins: a duty log written on the back of equipment manuals — sections switch via frequency dials, signal strength shows outside contact, handwriting degrades with fatigue.
- Court-intrigue default: red + gold border. If the user plays the historian keeping the emperor's daily record: a bound journal — each interaction an entry timestamped by the hour, sensitive entries inked over, the emperor's vermilion annotations as the only accent.

### 1.2 Interface identity & world logic

**Three positionings**:
- **In-world object**: dossier, ledger, letter, phone, terminal, artifact, map, newspaper, medical record, roster. Strongest immersion; the object's form, material, wear, and text format drive everything.
- **System UI**: fate panel, cultivation system, game menu. No physical form, so give it a style source (a faction's taste, a system persona) or it degrades into generic HUD.
- **Hybrid**: system shell + in-world inner pages. Shell handles navigation & consistency; inner pages handle narrative voice.

**Three questions**: who made it, for whom, viewed at what moment. The answers drive visuals: classified government archive → case numbers, clearance levels, official layout, seals; a girl's journal → handwriting, stickers, correction tape; a sect's jade slip → incised characters, warm jade material, glowing wards.

**World-logic consistency**: objects in one UI come from one world/era/tech level. Realistic settings demand stricter logic (a medieval setting with GPS breaks credibility). Allow at most one deliberate anachronism for usability, and make it explicit.

**Depth of fusion varies by task**: narrative reading, character display, low-frequency browsing → deep fusion. High-frequency operation, number comparison, fast decisions → clear structure with light genre grammar. Both depths may coexist in one work.

**Tradeoffs**: in-world objects immerse but constrain layout/interaction; system UIs are free but templated; high-volume/high-frequency info leans system or hybrid; character/world showcase leans in-world.

**Failure signs → fixes**:
- Genre shell around a generic dashboard (terminal skin over card grid) → make inner info use the object's native formats.
- Mixed-world props (parchment panel + neon progress bar) → unify sources, or make the shell/inner relationship explicit.
- Genre feel but no work feel (any same-genre work could reuse it) → redo §1.1.

### 1.3 Information in native formats & reveal pacing

Ask: "in this world, how is this piece of info normally recorded?"

- Finance → ledger columns and totals. Relationships → roster order, forms of address, genealogy. Tasks → commission letter or notice phrasing. Stats → medical form, rating report, fate-chart entries. Location → map, signpost. Time → solar terms, hours, log timestamps.

Native formats come from layout, typography, wording, and illustration assets — not from CSS-simulating physical props one by one.

**Carrier restraint**: one primary carrier for the whole UI; modules differentiate via layout within it. Sequential props (tape notes, tags, abacus beads, stove fire, stamps) read as a theme park and amplify each other's crudeness. Props needing real object-ness use illustration assets; anything below asset precision uses typography instead.

**Narrativized numbers**: pair values with in-world descriptions ("breath unstable" + number). Keep exact digits where decisions depend on them.

**Reveal pacing**: locked/unknown/sealed/archived/burned states are themselves narrative. Use face-down cards, seals, redaction, blur, torn pages for suspense; make reveals ceremonial.

**Legends**: symbolic systems need legends; legends can themselves be in-world documents (manual, index, rulebook).

**Change presentation**: per-turn updates should highlight what changed (delta marks, new entries, struck-through old info); don't re-dump all data every time.

**Failure signs → fixes**: everything is label:value or progress bars → native formats; one prop per module → one carrier, layout differentiation; uniform full data dump → three layers (always-visible / expandable / query); symbols without legend → add legend.

### 1.4 Copy & world vocabulary

- Actions use in-world verbs: open the dossier, sign, archive, burn, cast, place a stone, depart. Meaning must be clear; pair with icon or short note when not.
- Labels use in-world nouns: institution names, ID formats, units, calendars, forms of address.
- Decorative foreign text, numbers, clearance marks must be plausible in-world or encode real info. Meaningless English subtitles, "01/02/03" numbering, all-caps micro-labels, middle-dot strings are template tells.
- Voice matches identity: official documents cold and restrained, diary intimate, system terse, jianghu documents use their argot.

**Failure signs**: generic product copy (OK / Submit / Data Panel); English decoration as premium feel; conflicting voices across modules.

### 1.5 Mood & state expression

- **Two channels**: mood rides color temperature, background light, vignette, material state (clean/dusty/damp/damaged), texture strength, motion speed. Text and numbers stay stable and legible.
- **State-driven variants**: time, weather, location, relationship stage, crisis level can shift palette/background/material — within the same language (same components in a new state, not a new skin).
- **Key moments** earn stronger layout/motion; everyday states stay restrained so emphasis works.

**Failure signs**: mood only via text; crisis = full-screen flashing or red overlays; state variants become entirely different styles.

---

## 2. Visual language

### 2.1 Color

Decide value structure first, hue second: overall light/dark/mid; maximum contrast at the focal point; thumbnail value masses should read the layout.

Decision order: primary color → marks & key type → secondary colors (few, functional only: numbers, states).

- Color originates in the world: the material's own colors (paper, ink, bronze, lacquer, jade, tube light), scene light, faction emblems. Describe colors by concrete material ("damp rice paper", "oxidized copper", "faded cinnabar") — this steers consistency far better than "dark blue" / "gold".
- Accent only for key info and operable elements; smaller area = more effective.
- State colors are variants within the palette, not default red/green/yellow; also differentiate by shape/icon/text.
- Gradients simulate light, material, atmosphere transitions — never "add some effect" to buttons/titles.

**Tradeoff**: fewer colors = more focused identity; state-heavy systems need more differentiation — offload to value, shape, position.

**Failure signs → fixes**: purple-blue gradients + neon glow + translucent dark panels everywhere → return to concrete materials & light sources; gold on every border → gold only at top hierarchy; many colors with no roles → assign each a role, delete the rest; low contrast (dark bg gray text, beige bg pale gold) → body text ≥4.5:1 (WCAG AA).

### 2.2 Type & typography

Type is the UI's voice; Chinese long-form reading still has hard floors.

- **Roles**: display type carries character (titles, nameplates); body type guarantees legibility; data type aligns numerals; in-world type shows the writer (handwriting, typewriter, inscription).
- **2–3 families max.** More requires justification (several distinct "writers" in-world).
- Decorative type for short text only; long body uses a legible hei/serif body face — character comes from color, layout, and display type.
- **Chinese body floors**: ≥14px (15–17px typical); line-height 1.6–1.9; ~20–40 chars per line; no extra body tracking; no synthetic CJK italics (most CJK fonts lack real italics and get mechanically slanted). These are readability floors, not style rules.
- Hierarchy via combined scale+weight+color+whitespace; adjacent levels must differ clearly (avoid 1–2px steps).
- CJK webfonts are huge: load display faces only for titles, or subset; set fallback stacks; verify rare/traditional glyph coverage; layout must not collapse on font-load failure.
- CJK-Latin mixing: coordinate weights and visual sizes; full-width punctuation in Chinese context; `font-variant-numeric: tabular-nums` for number-dense regions.
- Vertical type: titles, nameplates, side labels (short text). Long vertical text: check reading & scroll direction.

**Failure signs → fixes**: all system-default fonts, no voice → at least choose identity fonts for titles and in-world text; decorative font / tiny size / low contrast as "premium" → return to body floors; too many close levels → merge to 3–5 and widen gaps; missing fallbacks (tofu, jarring system fonts) → stack + preview missing-glyph cases.

### 2.3 Shape, line & ornament

One geometric grammar per work, reused globally: radius scale, line widths, corner ornaments at few levels each. The grammar should explain the craft: riveted metal → cut corners; bound paper → right angles and torn edges; jade → soft curves.

- Ornament motifs come from the world: emblems, regional patterns, institution insignia, object silhouettes, star charts. One motif reused at multiple scales (background watermark → divider → list bullet).
- Lines carry structure: separate regions, lead the eye, express hierarchy. One directional line can pull the eye to the focal point.
- Ornament concentrates at boundaries and focal points; reading zones stay clean.

**Failure signs → fixes**: per-module radii/line-widths → unify grammar; every container = rounded rect + 1px border → differentiate by hierarchy and object nature; corner flowers / lace competing with content → keep only structural or identity-bearing ornament; emoji/Unicode symbols as decoration → SVG motifs or genre symbols.

### 2.4 Light, material & depth

Establish one credible physical space: where light comes from, what's on top, what each surface is made of. Variables: light direction & temperature; shadow softness/distance/color, highlights; depth of field/blur; materials (paper, leather, wood, metal, glass, cloth, stone, screen, hologram); transparency, texture strength, wear & age.

- **One light source**: a single direction and temperature; every shadow, highlight, inset, emboss obeys it.
- **Material relationships express depth**: paper stacked on a desk, nameplate riveted to wood, hologram hovering in the dark. Don't give every card the same shadow.
- Shadows carry ambient color: warm light → deep-brown shadows, cold light → deep-blue. Pure black translucency reads dirty.
- **Material implementation**: realistic main surfaces (paper, leather, wood, metal) prefer texture assets; CSS gradients/noise/SVG filters suit secondary surfaces and abstract materials; CSS-simulated realistic objects (tape, wood grain, tin, rivets) read fake at first glance — never as the primary treatment; reduce texture under text.
- Glass/blur only with a concrete reason (the world actually has glass/screens, or the key visual must show through).
- Aging (wear, stains, creases) concentrates at edges/corners; aging level uniform across the UI.

**Tradeoff**: realistic material depends on quality assets. Focal area uses texture assets; outlying areas may approximate the same material in CSS, but the approximation must not read visibly cruder.

**Failure signs → fixes**: every panel = translucent black + blur + glow stroke → pick real materials; contradictory light directions → unify; noise/scanlines/paper grain on text → reduce/remove under text; inconsistent texture resolution/stretch → normalize.

### 2.5 Image & icons

Illustration assets carry the key visual and all concrete art, integrated with the UI; icons share the UI's grammar.

**Division of labor**:

| Illustration assets | Code |
| --- | --- |
| Character portraits/figures, scenes & backgrounds, key objects & items, realistic material textures | Layout & typography, borders & dividers, ornamental patterns, icons, abstract & data graphics, light/color grading overlays, motion |

- The polished-card look comes largely from real illustration. Concrete subjects ship as generated or collected assets.
- CSS/SVG-drawn scenes, people, architecture, objects are far below illustration precision and read as programmer art. Placeholder only; replace before delivery.
- When assets can't be obtained, do NOT fall back to code-drawn art: rebuild the key visual around typography & abstract graphics, or keep an explicitly labeled placeholder and list the missing asset.

**Asset consistency**:
- Write the shared style description first (medium: thick-paint/watercolor/ink/cel/photo; brushwork; light direction; palette; clarity). Reuse verbatim in every generation request; use it as the filter for collected assets.
- Mixed sources: unify via grading, desaturation, shared grain, shared edge treatment; still conflicting → replace.
- One character across images: same face, clothing, style. Too many characters to keep consistent → reduce the count; use silhouettes, partials, or text dossiers.
- Item icons and item illustrations: pick one system, not half illustration + half line icons.

**Composition patterns** (choose by content, combinable):
- **Full-bleed base + floating layers**: illustration covers the whole base; panels float above; gradient masks/quiet underlays keep text contrast; the picture shows through gaps and edges.
- **Hero bleed**: illustration owns most of the first screen; title and key actions sit in its quiet zones.
- **Character-led**: figure placed to one side, crossing panel boundaries, info arranged around it (visual-novel layout).
- **Scene switches with state**: time/location/weather changes the graded base image, so functional pages stay pictorial.
- **Plates in sets**: items/portraits share crop, background, treatment, arranged like a catalog.

**One hero image per screen.** Secondary images blend into the same picture or form a uniformly treated set. Two differently-sourced images boxed side by side = collage.

**Art continues into functional pages**: illustration as a lowered-contrast layer under panels, cropped character partials, objects as section markers, state-switching scenes. Entering functional pages and losing all art is the classic quality collapse.

**Restraint ≠ removing pictures**: space freed from props goes to illustration and typography. A page of dark planes + hairlines + text reads plain no matter how clean.

**Text & image**: reserve quiet zones for text; gradient masks when needed; never cover key faces.

**Icons**: unified stroke width, terminals, corners, weight. Prefer genre symbols (seals, trigrams, constellations, insignia). Generic icon libraries clash with photographic/classical assets — recoloring is usually not enough; beside photos or old paintings prefer item plates, photo crops, or text. No emoji.

**Portraits in archives**: unified crop ratio and treatment (ID photo, old photograph, sketch) matching interface identity.

**Failure signs → fixes**: CSS/SVG block-built scene/figure as final key visual → replace with illustration, or typography-led rebuild; raw asset dropped into a rectangle → crop/mask/grade/blend; flat icons beside realism → unify style or downgrade icon weight; generated images with mismatched styles/lights → regenerate with the shared style description; placeholder avatars/blank cells → designed empty states or more assets; text/buttons baked into images → code-rendered text and controls.

---

## 3. Space

### 3.1 Composition & layout

Start from composition: focal point, major regions, reading path — then place components. Borrow the structure of the carrier object: dossiers have spines and tabs, newspapers have columns and a front page, phones have status bars and apps, maps have legends and scale bars. Object structure naturally produces non-repeating layouts.

- **One primary, several secondary**: one region takes the most area or strongest contrast; avoid equal-sized competitors.
- **Layering & frame-breaking**: characters, seals, notes may cross region borders to break mechanical rigidity — never covering text or actions.
- **Adjacent regions vary in composition**; not every section is "heading + card grid."
- **Functional UIs may be regular**: terminals, tables, consoles — regularity is the language; refinement comes from proportion, type, detail.
- **Flow pages are not forms**: onboarding, character creation, settings → not "left label / right input" tables. One step per screen, each with its own picture; key options (origin, faction, talent) get illustration plates; result reveals earn a visual climax. "One screen" = one complete picture, not forced 100vh; let content height shrink or let illustration fill the space, no large empty dark areas. Inputs stay clearly usable.

**Failure signs → fixes**: centered title + three equal card columns → redistribute area by importance; character-creation page reads as a registration form → rebuild as flow; random tilts "to not look templated" → every grid break needs a reason; wide-screen-only design → recompose at narrow widths, don't just scale down.

### 3.2 Scale & spacing

- Scale contrast must be obvious: focal elements clearly larger; even sizing makes everything equally important.
- Spacing on a ratio scale; intra-group distance clearly smaller than inter-group.
- Body column width follows line length, not screen width.
- Whitespace allocated unevenly: generous around the focal point, compact in data zones.
- Design at the actual available width — embedded chat panes are far narrower than the browser window.

**Failure signs**: all spacing equal; content touching edges; heading closer to the section above than to its own content.

### 3.3 Information density

- Contrast dense vs sparse: hero/narrative areas airy, data areas compact, clearly separated.
- Progressive disclosure in three layers: always-visible (every turn), expandable (occasionally), query (archives/history). Per-turn UIs especially need restraint.
- Density matches the object: ledgers and terminals are dense; invitations and poem cards are sparse.
- Too much info → cut or fold first; never shrink type to fit.

**Failure signs**: status bar crammed with a dozen stats plus long psychological prose; uniform density; filling every cell to look rich.

---

## 4. Information & components

### 4.1 Hierarchy

- Assign 1 focal point, 2–3 secondary, the rest background.
- Emphasize by combining 2–3 of scale/contrast/color/position/whitespace/motion — not everything bold and bright.
- Emphasis budget: the more emphasized elements, the less any emphasis works.
- Primary action most prominent; secondary actions lower weight but discoverable.
- Hierarchy operates at two levels: within modules and between modules.

**Failure signs**: all headings equally loud; ornament outshines information; key actions buried in decoration.

### 4.2 Themed components

Component family (buttons, tabs, inputs, switches, progress, modals, toasts, list items) shares one grammar of shape, line, material, states.

- Theming comes from the family grammar + type + wording — not from making every component a physical prop. Hit areas, current state, action meaning must be unambiguous; common controls stay where users expect.
- **Props: few and precise.** At most one or two key components get physical object form (a signature seal on confirm, spine tabs for main nav) — at asset-level precision (illustration or refined graphic), else make them restrained themed standard components.
- Full state set: default, hover, focus, active, selected, disabled, loading, empty, error. Themed states as refined as defaults.
- Native controls (selects, scrollbars, sliders, checkboxes, text selection, focus rings) join the family while keeping accessibility.

**Failure signs → fixes**: browser-default button inside genre shell → unify to family; over-themed, can't tell what's clickable → keep hover change, cursor, relief/shadow affordances; stamp-after-tag-after-note props all at draft precision → collapse to one carrier + one or two refined props; default state only → complete the state set.

---

## 5. Interaction & motion

### 5.1 Feedback as world action

- Immediate visual response on click.
- Waiting states have in-world expression plus clear status text (ink blooming, signal searching, incense burning).
- World actions: page turns, stamping, drawing lots, dial turning, scroll unfurling — converted into transitions and feedback. Actions stay short; never block repeated operation.
- State changes visible: selected/done/disabled/new each have a clear, consistent look.
- Errors & empty states phrased in-world, with an actionable next step.
- Keyboard & touch: everything keyboard-operable with visible focus; touch targets large enough.

**Failure signs**: no hover/active feedback; static waiting with no indication; themed actions so long they annoy on repetition.

### 5.2 Motion

Character from the world: mechanical → hard cuts/stepped; paper → fold/light drop; ink → bloom/fade; sci-fi → scan/unfold; uncanny → flicker/lag. One duration/easing family per work. Entrance choreography staggers in reading order toward the focal point. Looping animation (blink, particles, scanlines) fatigues and distracts — push to edges/low contrast, reduce amplitude, respect `prefers-reduced-motion`. Performance: prefer transform/opacity; large blurs/filter animation/particles stutter on mobile or multiple simultaneous renders.

**Failure signs**: everything fades in identically; floating glow pulses everywhere; inconsistent durations; animation blocks interaction.

---

## 6. Adaptation, host & accessibility

- **Narrow-width first**: narrative UIs often live in chat panes or phones (~360px). Recompose (stack, tabs, fold) at narrow widths — keep focal point and key visual; don't scale down proportionally.
- **Embedded host**: viewport units may measure the iframe, not the window; let height follow content, avoid `vh`/parent-height dependencies; verify fullscreen/height-coupled layouts in place. The same UI may render in many messages: control image weight, animation, script count; consider read-only snapshots for old messages. UI renders after text finishes streaming — design a load transition consistent with the work, no blank/flash. Scope styles; don't rely on globals. The UI persists across the whole conversation, not just the opening. Model-generated dynamic content: model outputs structured data only, fixed template renders — stable style, fewer errors, less context. Local/stable asset & font URLs with failure fallbacks.
- **Accessibility**: body contrast passes; states not by color alone; keyboard operable with visible focus; alt text on meaningful images; respects reduced-motion.

**Failure signs**: desktop-only checks; clipped text or horizontal scroll on phone; jank from repeated renders; hotlinked temporary image URLs.

---

## 7. Cross-dimension coordination & tradeoffs

1. One concept governs all choices — every element must state its part of the concept; else change or delete it.
2. Physical setting consistency: shape, light, material, temperature, aging from one world.
3. Style-strength budget: intensity concentrates at focal points, shell, key moments; reading/operating zones stay quiet; one bold move beats ten.
4. Fusion depth varies by task (narrative deep, high-frequency clear).
5. Shell unified, inner pages vary with content.
6. Mood on the sensory channel, info on the clear channel.
7. Uniform quality bar: uneven investment allowed, no region below the bar; cost cuts simplify within the language, never revert to defaults.
8. Uniform precision: anything concrete in frame matches overall precision; a crude prop drags down refined typography around it — re-express via type/abstract graphics or use assets.
9. Few ideas, executed precisely: perceived finish comes from a few elements done well, not metaphor count. One carrier + precise typography beats ten draft-precision props. Restraint applies to props/ornament, not illustration/color.
10. Defaults must be chosen.

Conflict priority: readable & operable (floor) > work identity > overall unity > local effect > implementation convenience.

| Conflict | Resolution |
| --- | --- |
| Decorative type vs body legibility | Display type for titles; legible body face; character via color/layout/in-world type |
| Immersion vs operation efficiency | Lower fusion depth in high-frequency zones; keep shape grammar + palette |
| Visual effect vs performance | Cut looping motion & large filters on mobile/multi-render; keep static texture |
| Art investment vs cost | Focal area bespoke assets; periphery approximates same material in CSS; never default components |
| Concrete representation vs missing assets | Typography/abstract rebuild, or clearly labeled placeholder + listed missing assets; never code-drawn substitutes |
| Realistic material vs text contrast | Reduce texture under text, or add a quiet underlay |

---

## 8. Failure-mode quick reference

| Symptom | Cause | Fix |
| --- | --- | --- |
| Right genre mood, no work-specific memory point | Genre-average starting point | Re-derive per §1.1; run similar-prompt test |
| Several screens identical except palette | Generic skeleton + reskin | Rebuild structure from native info formats + carrier object |
| Gorgeous opening, plain dark form pages after | Art budget spent on first screen only | Continue key visual into functional pages; uniform quality bar |
| Genre shell, generic cards/progress bars inside | Shell only | Inner info in the object's native formats |
| Old default swapped for a new trendy one | Ban-list instead of judgment | Derive from the work, not from "another pretty style" |
| Uniform dense small text | No info layering | Cut, layer disclosure, widen hierarchy |
| Neon glow / glass blur / gradients everywhere | Effects substituting material & light | Pick real materials + one light source; effects only where motivated |
| Texture/scanlines/noise over body text | No style-strength budget | Reduce/remove under text |
| Mismatched asset styles/sharpness/light | Assets collaged raw | Unify grading, grain, edges, light direction |
| Key visual is placeholder, blank cell, or glued-on image | No asset plan | Fix asset sources; design empty states |
| Emoji icons, mixed icon sets | Icons outside the language | Unify stroke/style, or switch to genre symbols |
| Browser-default scrollbar/focus/select sticking out | Undecided defaults | Pull into the component family |
| Meaningless English subtitles, numbering, all-caps micro-labels | Template decoration | Delete, or replace with in-world text encoding real info |
| Per-turn generated UI style keeps changing | No fixed template | Model outputs data only; fixed template renders |
| UI appears only at the opening | First-experience-only design | Design the persistent interface across the conversation |
| Locally refined, overall reads like multiple projects | Per-module design | Unify via sample + record; side-by-side module checks |

### The AI hand-made game-UI kit

Model-generated game UIs have a signature crudeness: an idea everywhere, draft precision everywhere. Any single item below is forgivable; in groups they produce the look.

| Tell | Fix |
| --- | --- |
| CSS/SVG block-built scenes/architecture/landscapes/figure silhouettes as final key visual | Replace with illustration; if unavailable, typography-led key visual |
| One simulated prop per module: tape notes, crooked red stamps, tags, abacus beads, stove fire, wooden plaques | Collapse to one carrier; one or two refined key props |
| Default kit: beige paper + dark slate panels, "URGENT / LOW-GRADE" crooked stamps, bordered tag strings, Chinese-numeral or hex step nodes, radar charts, corner-bracket badges | Ask per element: does this belong to this work's language? If not, derive a replacement from the language |
| Calligraphy/handwriting used broadly to fake "handwritten feel" | Reserve for genuinely autographic short text; verify the font itself |
| A framed +/- delta tag on every value ("Stamina -20", "XP +4") | Show only where decisions need it; express via typographic hierarchy, not tag strings |
| Many ideas, each at low precision | Halve the ideas; finish the rest to asset precision |

### Over-restraint

Removing props and hand-drawing often leaves a clean but plain UI where no picture speaks.

| Symptom | Fix |
| --- | --- |
| Illustration confined to a top banner; rest is dark panels + hairlines + text | Switch to a picture-led composition (§2.5): illustration as base layer under panels, or owning most of the screen |
| One accent color allowed, everything else one cold gray/dark | Restraint in color ≠ absence of pictures; let illustration carry color and value range |
| Differently-sourced images boxed side by side | One hero image; secondaries blended or a uniform plate set |
| Flow page as left-label/right-input form | One step per screen; illustrated key options; visual climax at reveal |
| Page forced to 100vh with content only in the top half | Height follows content; when full-height is needed, let illustration fill it |
| Generic game icons beside photographic/classical assets | Switch to item plates, photo crops, or text; recoloring alone rarely suffices |
| Same image crop reused across modules when assets run short | Reduce image slots; let typography carry modules without bespoke art; repetition only as deliberate motif |
