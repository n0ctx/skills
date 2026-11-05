# Tavern Aesthetic

An AI skill providing design guidance for immersive narrative interfaces: roleplay front-ends, interactive fiction, game panels, character dossiers, and story-driven web pages.

Focus:

- A visual identity unique to the work, not the genre.
- Illustration-led composition: illustration sets the layout's center of gravity, not a banner or boxed thumbnails.
- World-integrated information: content presented in the formats it would take inside the world.
- Illustration assets first (AI-generated or licensed web collection); code-drawn art is concept-validation placeholder only.
- Restrained props, unrestrained pictures; every visible region held to one quality bar.
- Legible Chinese text and a genuinely operable interface.

Complex interfaces follow a staged process: direction and composition first, one core sample finished to production quality, then module-by-module extension and final polish.

Independent of SillyTavern and any specific frontend framework; the project's existing implementation is preferred. Existing AI image-generation capabilities may be used when available and appropriate.

## Install

Clone into your personal skills directory:

```sh
git clone https://github.com/n0ctx/tavern-aesthetic.git ~/.agents/skills/tavern-aesthetic
```

For Claude Code, install to `~/.claude/skills/tavern-aesthetic`. If the target directory already exists, check its contents first to avoid overwriting an existing install.

## Usage

Explicitly invoke `tavern-aesthetic` in a skill-capable AI tool, stating genre, page purpose, project path, and the specific need. Example:

> Use tavern-aesthetic to design a character dossier page for this interactive-fiction project, foregrounding the character's background and key actions while keeping Chinese text comfortable to read.

This skill targets immersive narrative interfaces and does not auto-trigger on generic web tasks. When only a design is requested, do not modify code.

## Example

Below: a cultivation-genre character card generated with this skill, 720px wide, main screen showing fate status.

![Cultivation character card main screen](docs/example-xianxia-720.jpg)

- Key visuals and plates use old paintings, woodcuts, and museum collection photos, all public domain or CC0. These are borrowed historical works, not original art for this piece.
- No AI image tool was available during generation, so no bespoke character art exists; the player character is represented by a vertical-style daoist name instead.
- This is a test output, not a finished product. Known issues: whitespace at the bottom of the creation page; crops of the same image reused across modules.

## Files

- [SKILL.md](SKILL.md): goals, core principles, task levels, execution flow, visual review, delivery.
- [references/design-knowledge.md](references/design-knowledge.md): design knowledge by dimension, tradeoffs, failure modes.
- [references/workflow.md](references/workflow.md): staged process for complex tasks, gates, review method, rollback rules, design-record template.
- [references/asset-sources.md](references/asset-sources.md): asset sources and license checks.
- [references/research.md](references/research.md): evidence, sources, limitations.
- [docs/](docs/): example screenshots.
