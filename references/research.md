# Research basis

Evidence and limitations behind this skill. Not needed for execution; consult only to judge where a rule comes from or whether it applies to a given work.

Research period: October 2026.

## 1. Scope & limitations

**Sources**: open-source front-end cards and status bars on GitHub; Bilibili card showcase/tutorial videos (frame-by-frame review); JS-Slash-Runner docs and source; English communities (GitHub, Chub, SillyTavern docs); narrative-game UI design talks/interviews; comparable AI design skills; art-production process material.

**Biggest limitation**: the community-acknowledged polished cards live in closed Discord communities (Leinaal, Journey) inaccessible at research time; Reddit, Game UI Database, Tieba, Zhihu, Xiaohongshu also inaccessible.

**Consequence**: no polished-card benchmark exists here; public samples informed only medium constraints, common failure modes, and isolated borrowable techniques. "Polished" standards in this skill are reasoned inference from transferable professional method and counter-examples, not direct observation of polished cards. If polished card files/recordings/author notes become available, add them and re-review §2.

## 2. Main conclusions

What separates narrative UI from ordinary web UI, with evidence:

1. **The interface has an identity** — an object or system in the story; color/type/layout/components derive from it. (Fagerholt & Lorentzen's UI taxonomy; the Suzerain card's dossier concept, §3.) → design-knowledge §1.1–1.2.
2. **Information has native formats and reveal pacing** — ledgers, rosters, hexagrams, torn pages; locked/sealed states as narrative. (Disco Elysium thought cabinet face-down; Inscryption symbols + rulebook.) → §1.3.
3. **Text has a voice** — fonts and action vocabulary show "who wrote this." (Pentiment per-class scripts; Suzerain card's "open the dossier / archive / destroy" buttons.) → §1.4, §2.2.
4. **Mood and state drive visual change while information stays legible.** (Her Story lighting; Fagerholt on sensory feedback; Tavo weather status bar day/night palettes.) → §1.5.
5. **Persistent across a conversation, works in narrow widths, repeated renders, streaming output.** (JS-Slash-Runner docs/source; community complaints about "UI only at the opening.") → §6.
6. **Finish comes from a uniform quality bar and staged polish, not one-shot coverage.** (Art-production literature; first-screen-gorgeous/functional-pages-plain counter-cases.) → workflow.md.
7. **Concrete art depends on illustration assets; element precision matters more than idea count.** (Best-looking public-sample parts were all illustration; generation tests in §8.) → SKILL.md principles 3/6; design-knowledge §2.5, §7, §8.

## 3. Public-sample observations (not polished benchmarks)

Descriptions are from actually viewed frames/screenshots. Open-source samples rendered in a local simulated environment with empty/default data, not real play.

**Suzerain V0.54 (author: Beitiao)** — bilibili.com/video/BV1xq8b6vEEH. Political, adapted from the game; ~15k plays, praised as "very finished." Strengths: the whole UI is a classified presidential dossier — wine-red cover, gold serif titles, "open the dossier" button, tabbed dossier inside; finance page as a ledger; personnel page with portraits; in-world action verbs; per-event-type styles; help/index pages. Weaknesses: small dense table text, host-default dark body, mobile unverified.

**A Record of a Mortal's Journey (author: KAI)** — bilibili.com/video/BV1jV5u6xEWV. ~34k plays ("is this even SillyTavern"). Strengths: title screen = full-screen ink landscape + figure illustration with gold calligraphy title, reads like a standalone game. Weaknesses: art vanishes entirely in character-creation and play pages — dark base, small text, stroked boxes, empty cells; huge opening-vs-functional gap.

**Tavo floating weather status bar** — bilibili.com/video/BV1cAUjBKEcW. ~30k plays. Strengths: palette follows in-story time/weather (sakura-purple day, deep-blue night with moon). Weaknesses: structure still avatar + progress bars + text blocks; comment concern about context consumption.

**Status-bar restyle showcase** — bilibili.com/video/BV1qXzsbEzU. Three panels identical in skeleton (level, four stat bars, skill tags), palette-only differentiation, one neon-gradient — the canonical "recolor, not restructure" failure.

**Community comments**: UI only at the opening, nothing after choices (BV1D4QUBSEVr comments); context-consumption and platform-compatibility worries; a hiring post demanding cards that "look good AND look different from each other" (v2ex.com/t/1239036).

**Open-source samples (GitHub, low-star)**: matrix4033/tavern-status-bars — six different components, one card style (1px border, 8px radius, blur), no genre material, empty data → whole block vanishes. QINMO7557/young-marcus-ui — kraft paper/tape/paper clips via CSS vars + pseudo-elements, handwriting font loaded separately, pinned asset versions; but schedule region shows empty lines + "no records", no designed empty state. feihu-lgtm/watchdogs-london — near-black + single accent, self-hosted fonts with license text, reduced-motion support, narrow breakpoints, commit history shows orientation-reflow and font lazy-load fixes. yjlovegy/xinyuanshe-card — loading shell before data ready with timeout prompt; old messages render read-only snapshots. EnitiyFiaz/jiugui-card — mobile floating-window positioning, dynamic viewport units, safe areas, cache fallbacks in commit history. Common pattern: commits cluster around release/logic, little record of visual polish.

**English community**: few in-card custom UIs; mainstream = per-turn improvised HTML (e.g. Stab's EDH Visual Toolkit, github.com/Zorgonatis/Stabs-EDH) or SillyTavern theming. Improvised generation produced wildly divergent panel languages within one work (pink slash labels + green terminal panels) — no persistent direction. Medium constraints: few Chub cards carry HTML tags; SillyTavern sanitizes message HTML; card regex needs user approval.

## 4. Transferable methods from narrative games

| Method | Source | Migration |
| --- | --- | --- |
| Classify UI by "in fiction? in space?"; full diegesis not always more immersive; realistic worlds demand stricter logic; narrative tolerates ambiguity, fast decisions need clarity | Fagerholt & Lorentzon, *Beyond the HUD* (2009), publications.lib.chalmers.se/records/fulltext/111921.pdf | Interface identity first; fusion depth varies by task |
| Primary color → marks/key fonts → few functional secondaries; menus lead the eye with lines; bright primary, dark secondary; every menu animates instantly | Persona 5 UI interviews (personacentral.com) | Color decision order; accent budget; instant feedback |
| Per-culture/class custom scripts, written stroke by stroke; hard fonts unsuitable for heavy text admitted | Pentiment (gamedeveloper.com) | Type as voice; decorative type for short text only |
| Unified OS shell, wildly varied inner pages | Hypnospace Outlaw (filmstories.co.uk) | Unified shell, content-driven inner pages |
| Prefer stylization + legibility; outlines for readable edges; suppress flicker/noise | Return of the Obra Dinn devlog (dukope.com) | Style must not beat legibility |
| Clear-metaphor symbols replace text; rulebook hides narrative clues | Inscryption (gamedeveloper.com) | Symbols + legend; legend can narrate |
| Thoughts face-down by name only; reveal after internalizing; critiqued for color-blindness and small text | Disco Elysium (gamebanshee.com; caniplaythat.com accessibility review) | Reveal pacing; style never beats legibility |
| Dice = energy, clocks = progress, abstract not skeuomorphic; accent only on options | Citizen Sleeper (oldmenrunningtheworld.com) | Symbolized resources; accent on operables only |
| Lighting follows clip mood; whole UI a credible old police PC with one deliberate unreality | Her Story (vice.com) | Mood on sensory channel; one deliberate unreality |

Persona 5 material is English translation of Japanese media, not verbatim quotes.

## 5. Homogenization of AI-generated UI

- Models land on training-data statistical centers (Anthropic: distributional convergence); banning one font/palette shifts to another local optimum (Inter → Space Grotesk). claude.com/resources/articles/improving-frontend-design-through-skills
- Anthropic's official frontend-design skill evolved from "pick an extreme style, ban specific fonts" to listing AI-default style clusters + similar-prompt self-test. github.com/anthropics/skills
- Fix-lists become new kits ("cream base, serif, terracotta") — teach judgment, not replacement lists. github.com/Leonxlnx/taste-skill
- NN/g: multi-tool AI prototypes look similar, flat, interchangeable. nngroup.com/articles/ai-prototyping/
- Start from composition, not components; content that survives removing borders/shadows/radius shouldn't be a card (paraphrase). developers.openai.com/blog/designing-delightful-frontends-with-gpt-5-4
- Unthemed browser-default surfaces (scrollbars, focus rings, selection color) signal assembly over building; don't perfect one corner while the rest sits below the bar. github.com/pbakaus/impeccable

## 6. Production & polish method

| Method | Source | Form in this skill |
| --- | --- | --- |
| Shared art-direction reference or everyone reverts to their own style | gamedeveloper.com/art/five-secrets-of-game-art-direction | Design record, uniform quality bar |
| "Beautiful corner": finish one small block to production to prove direction | ryantreadwell.com/post/beautiful-corners | Core-sample stage |
| Graybox → art pass → polish; check all components side by side; effort by importance | book.leveldesignbook.com/process/env-art | Composition stage; side-by-side; quality bar |
| Prototype/alpha/beta with per-stage finish bars | gameworldobserver.com (Tim Cain) | Stage gates |
| Extract rules from finished assets, not vice versa | blog.makko.ai; designcaitlin.substack.com (UI art bible) | Registry written only after sample passes |
| Independent reviewers against fixed criteria beat self-review; scoring wording shapes output; middle rounds may beat finals — keep snapshots | anthropic.com/engineering/harness-design-long-running-apps | Independent acceptance review; rollback points |
| Agents over-reach or declare done on partial progress; step module by module, verify end to end | anthropic.com/engineering/effective-harnesses-for-long-running-agents | Module-by-module; real-environment acceptance |
| Same issue failing twice → restart, don't stack fixes | code.claude.com/docs/en/best-practices | Rollback rules |

## 7. Medium constraints (JS-Slash-Runner)

From n0vi028.github.io/JS-Slash-Runner-Doc/ and github.com/N0VI028/JS-Slash-Runner.

- UIs render as isolated embedded pages per chat floor; `vh`/`vw` mostly measure the iframe, not the window.
- Iframe height auto-follows `body` content; viewport/parent-height coupling causes mutual blow-up. Community agent guidance: avoid `vh`; use width + `aspect-ratio`; avoid absolute-positioned main bodies; no horizontal scroll. (github.com/StageDog/tavern_helper_template)
- Render depth hides old floors; other HTML-injection plugins may duplicate UIs; more code = more jank — author recommends load links only in floors.
- Streaming: UIs render after text finishes.
- Assets/fonts commonly via jsDelivr mirrors (cache lag) and online font services.
- Community template skills cover engineering/adaptation only — little design guidance; example styles invite copying (inferred convergence).

## 8. Generation tests

**Setup**: October 2026, one model, two genres (cyberpunk underground clinic; cultivation outer-disciple), two skill versions each, no image tool, external images banned — all art CSS/SVG.

**Round 1 findings**: both versions derived similar concepts ("noodle-shop menu as medical record"); concept-level guidance added little for this model. An AI reviewer scoring "identity, narrative integration" preferred the metaphor-richer version; human review saw no real difference and flagged obvious "hand-made AVG" crudeness — reviewer criteria parroting the skill's own emphasis is circular. Crudeness sources: CSS/SVG block scenes & figures; per-module simulated props; the habitual game-UI kit (crooked red stamps, tag strings, step nodes, radar charts); many ideas at low precision each. **Conclusion**: polish depends on illustration assets and per-element precision; code-drawn art is concept-validation placeholder only; review must ask "does this look like a production with dedicated art polish", not count metaphors.

**Round 2** (illustration-first, web-collected, still no AI image tool): cultivation card used Song paintings, Tiangong Kaiwu woodcuts, Eighty-Seven Immortals scroll, museum object photos; cyberpunk card used HK night/back-alley photos, prosthetic-hand photo, tile texture — all PD/CC0/CC BY. Human review: direction correct, hand-made feel largely gone. **New issues**: over-restraint (illustration only a banner, rest dark panels + text); registration-form-like creation page; two boxed photos side by side (collage); generic game icons vs documentary photos; no bespoke character art obtainable online. Actual build time ~50–75 min (excluding ~6h external sync stalls).

## 9. Unverified

- Polished cards and their reception in closed Discord communities.
- Blocked: Reddit, Game UI Database, Tieba, Zhihu, Xiaohongshu, linux.do.
- Bilibili: few comments; subtitles need login.
- Open-source samples rendered in simulated environments; real-play screenshots unavailable (Wanjie Shop, SSR summons, Xinyuan Society, Astraea render failures — no conclusions).
- Game sources not adopted for lack of reliable primary material: Hades, visual-novel textbox conventions, Dead Space; "target render / key art / style frame" definitions (skill uses "core sample" and "design record" instead).
- Peer-skill stats/stars are self-reported or secondhand, not independently verified.
