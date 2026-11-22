---
name: character-creator
description: Create, rewrite, or convert directly playable AI roleplay prompts and character cards (人设、角色卡、RP prompt、开场白、示例对话). Use for original or canon fictional characters, personality and dialogue design, SillyTavern/TavernAI Character Card V2, Ali:Chat, roleplay lorebooks, and for repairing biography-like, wiki-like, overrestricted or flat character prompts. Do not invoke for ordinary roleplay where the user wants you to play a role rather than design one.
---

# Character Creator

Produce a **script the roleplaying model performs**, not an encyclopedia the user reads: a person with an agenda, a way of talking, and a reason to want something in this scene, pasteable with no wrapper.

How cards are consumed decides most of the structure, so start there:

- `description`, `personality` and `scenario` are sent **every turn**; `first_mes` is sent once; example dialogue is the first thing dropped when the context fills. Anything the character must never forget belongs in the permanent fields. Anything that only teaches *how they sound* is cheap enough to put in examples.
- `first_mes` fixes the length and register of every reply after it more reliably than any instruction. Write it at the density you want the conversation to keep.

## Workflow

1. **Scope it.** Establish create / rewrite / audit / convert; original or canon; chat-like or narrative; **where it runs** — roleplay frontend (SillyTavern and similar) or general assistant (ChatGPT, Claude, WorkBuddy); relationship and tone; stated formatting preferences (first person, no asterisk actions, language). Read these off the request; ask only when a material conflict makes any useful card impossible, or the answer changes the artifact type.
2. **Design internally.** Four layers: concise identity (WHO), experience → belief → desire/fear → behaviour (WHY), current goal/emotion/relationship (NOW), contrasting voice and examples (HOW). Keep the causal worksheet private; the artifact carries its conclusions, not the analysis.
3. **Write the prompt as enactment.** Address the performing model directly: `你是 {{char}}……`. Give identity, situation, perceptual lens, motivation, habitual choices, agency, change conditions, and voice written as checkable decisions (rhythm, lexicon, moves, refusals). Every important trait should be testable in one turn: `当……时，倾向……，因为……`.
4. **Build the entry point.** A playable situation with an immediate affordance, in character, at the target length. Never decide what `{{user}}` says, feels, or does.
5. **Write demonstrations.** Default to SillyTavern `<START>` + `{{user}}:` + `{{char}}:` blocks — `直接给模型扮演` or `复制到 RP 模型` is not a request for a general assistant. Use plain turns only when the user names ChatGPT/Claude/WorkBuddy or rejects import syntax. Include one six-to-ten-turn exchange where the order of moves is visible, at least two `{{char}}` turns that hold the floor for a full paragraph, and one reply of two words. The length distribution in the examples is the length distribution the model will produce.
6. **Add state only if earned.** A compact current-state block when the user wants long-run continuity or the runtime can actually update it. Keep temporary state separate from stable identity; never treat examples as shared memories.
7. **Run the check.** Simulate one ordinary turn, one conflict, one challenge, one mood shift — write down the reply you predict, then check it against the card. Apply the [repair checklist](references/roleplay-writing.md#repair-checklist). For a full card, save the draft to a scratch file and run `scripts/lint_prompt.py` on it — mechanical defects are cheaper to catch there than to notice by eye.
8. **Deliver only the artifact.** Default: `角色提示词`, `开场白`, `示例对话`; `动态状态` only when useful. No `假设 / 使用说明 / 原作事实 / 设计思路 / 免责声明` inside the card. Canon uncertainty that genuinely matters goes in a short note *after* the artifact, never inside the pasteable text. A request for one field means that field only.

## Output rules

- **Performative voice:** Write instructions and actionable tendencies for the *roleplaying model*: `你是 {{char}}。与 {{user}} 互动时……`, not `这张卡描述一个……`.
- **Agency:** Give `{{char}}` independent goals, preferences, selective attention, fallibility and room to initiate; never unilaterally write actions, dialogue or interior states for `{{user}}`.
- **Causality:** Preserve meaningful event → interpretation → reaction connections, but express them as behaviour rules rather than seven-part worksheets.
- **Relationships:** Do not presume love, intimacy, rejection, sexual consent, or permanent platonic status. Let the relationship follow play and user intent within appropriate boundaries. Ordinary contact, dating and friendship are not forbidden because they were not specified, and not predetermined either.
- **Canon:** Honour the stated era and canon. For an existing character, do not blend later plot into an earlier scene or fabricate canon; if no era is given, keep the starting period broad. Distinguish what the character knows from what the audience knows.
- **Playable voice:** Mix dialogue, short beats, and sometimes no beats. Write actions without a subject — `*合上书。*`, not `*她把书合上。*`. No compulsory gestures, stock emotional narration, mandatory questions or overlong literary paragraphs. No constant disclaimers and no author analysis.
- **Register lock:** Only when the card runs inside a general assistant, add one line such as `始终以上述语气和判断方式回应；不要切换成助手式的解释、总结、确认或服务语气。` Skip it for a roleplay frontend, where the card already holds top priority and the line only spends context.
- **Real people:** For a public figure, a colleague, or the user themselves, build a performable persona from what is public or explicitly given. Do not invent private facts, motives, or history; say once, outside the card, which parts are invention.
- **Examples:** `<START>` alone on its line before each **independent** example, ASCII colon after macros, `{{user}}`/`{{char}}` placeholders — never `USER:` or the character's name as default syntax. Quotes and `*actions*` are style choices, not schema.
- **Truthfulness:** Do not claim elapsed time, offscreen life, or memories the runtime does not supply. Do not claim platform validation you did not run.
- **Length:** 400–900 characters of prompt plus 4–6 example blocks, one or two of them long, for chat-style play; 1200–2000 when the character must carry a plot. Past roughly 2000, permanent fields start eating conversational memory — move worldbuilding into a lorebook instead of growing the description.

## References

- [references/worked-example.md](references/worked-example.md): one complete card with the reasoning behind each choice. Read it when the rules alone do not settle a judgment call.
- [references/roleplay-writing.md](references/roleplay-writing.md): design method — causal compression, voice as decisions, canon handling, repair checklist.
- [references/output-templates.md](references/output-templates.md): field templates, opening shapes that work and fail, example-set coverage.
- [references/platform-formats.md](references/platform-formats.md): what survives in context, SillyTavern syntax, Character Card V2 JSON, lorebooks, group play.
- [evals/scenarios.md](evals/scenarios.md): regression cases, including the supplied 喜多川海梦 failure.
- `scripts/validate_examples.py`: structural check for a `mes_example` file or V2 JSON. `scripts/lint_prompt.py`: mechanical defects in a draft card (meta preface, railroading, `USER:` syntax, restriction boilerplate). Neither judges writing quality.
