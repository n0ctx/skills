# Changelog

## 1.0.0

- Card structure follows how cards are consumed, not how they read: `description`/`personality`/`scenario` are sent every turn, `first_mes` once, and example dialogue is evicted as a chat fills. Behaviour goes in the permanent fields, accent in the examples, worldbuilding in a lorebook.
- Voice written as four checkable decisions — rhythm, lexicon, moves, refusals — with contrastive anchors, replacing trait adjectives that cannot be tested against a single reply. A generic prohibition (`避免僵硬动作`) applies to every card, so it steers none.
- Worked card for 叶修 (《全职高手》), annotated choice by choice: two long exchanges and three short blocks, action beats without a subject, canon lines kept to two.
- Opening-message guidance: five shapes that fail, three that work, and the rule that the opening fixes the length of every reply after it. Example turns set the same ceiling, so the set carries both full paragraphs and a two-word reply.
- Platform reference: SillyTavern `<START>` syntax, Character Card V2 JSON, Ali:Chat, character lorebooks (only the main one travels with the card), group play, and Character's Note as the place to hold a voice against drift.
- `scripts/validate_examples.py` checks import syntax; `scripts/lint_prompt.py` catches mechanical defects — meta preface, `USER:` labels, `{{user}}` railroading, blanket restrictions, subject-bearing action beats, flat turn length.
- Regression cases include the 喜多川海梦 failure and the general-assistant branch, where the card has to carry its own register lock.
