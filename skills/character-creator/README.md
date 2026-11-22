# character-creator

An agent skill for building AI roleplay character cards: a persona prompt the model performs, an opening message, and example dialogue — as a SillyTavern / Character Card V2 import, an Ali:Chat-style block, or one plain prompt for a general assistant.

It treats a card as a script, not an encyclopedia. Three ideas carry most of it:

- **The field decides the content.** Description, personality and scenario are sent every turn; the opening is sent once; examples are the first thing evicted as a chat fills. Behaviour belongs in the permanent fields, accent in the examples, and worldbuilding in a lorebook.
- **Voice is decisions, not adjectives.** `她说话简短、克制` cannot be checked against anything. Rhythm, lexicon, moves and refusals can — and a generic prohibition such as `避免僵硬动作` applies to every card, so it steers none.
- **Length is contagious.** The opening and the example turns set how long every later reply will be, more reliably than any instruction. A set of one-line examples produces a character who answers in one line forever.

Ships with a worked card ([叶修 / 《全职高手》](references/worked-example.md)) annotated choice by choice, a repair checklist, and two scripts: `validate_examples.py` for import syntax, `lint_prompt.py` for mechanical defects — meta preface, `USER:` labels, `{{user}}` railroading, subject-bearing action beats.

## Install

Install just this skill, globally:

```bash
npx skills add n0ctx/skills --skill character-creator -g
```

Or link it from a local clone:

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
~/Projects/skills/scripts/link.sh --skill character-creator --agent all
```

Full flags, updates and uninstall: [repo README](../../README.md).

Agents without skill support can be told to read `SKILL.md` first and follow it.

## Install as a Claude Code plugin

```
/plugin install character-creator --marketplace n0ctx/skills
```
