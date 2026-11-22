# Platform formats

## What stays in context (this decides the card's shape)

In SillyTavern, not all fields are equal:

| 字段 | 何时进入上下文 | 设计含义 |
| --- | --- | --- |
| `description` / `personality` / `scenario` | 每一轮 | 角色不能忘的事、必须遵守的行为规则放这里 |
| `first_mes` | 仅在开场 | 定全篇的长度与语域 |
| `mes_example` | 有空位时插入，随对话推进被逐块挤出 | 只教“怎么说”，不承担“是什么” |
| 世界书条目 | 关键词命中时 | 世界观、地点、配角；不占常驻预算 |

Two consequences. Behaviour the character must never lose belongs in the permanent fields, never only in examples. Worldbuilding that outgrows the description belongs in a lorebook, not in a longer description.

## Default: SillyTavern/TavernAI examples (`mes_example`)

Official SillyTavern documentation specifies **`<START>`** before each independent example and speaker macros with ASCII colons:

```text
<START>
{{user}}: 当年为什么走？
{{char}}: “打不动了。”
*停了一会儿，重新点上一支。*
“荣耀没你想的这么简单。”

<START>
{{user}}: 明儿我再来。
{{char}}: *看了眼时间，把外套扔过去。*
“练到四点，四点半之前回去睡。”
{{user}}: 你不睡？
{{char}}: “我值夜班。”
```

- Exactly one `<START>` per separate example conversation; a few alternating turns within one example are allowed (see the second block above).
- The first line after `<START>` is normally `{{user}}:`, then alternate. Inside a `{{char}}:` message, line breaks, dialogue and `*action*` need no new prefix; actions carry no subject (`*笑了一声。*`), because the character is the default speaker.
- Do not substitute `USER:` or the literal character name unless the target format demands it.
- Use ASCII `:` after macros; a fullwidth `：` breaks imports.
- The UI replaces `<START>` with its internal example separator at prompt time. It is a field delimiter, never something the character says.
- `*actions*` and `“speech”` are writing conventions, not schema. Adjust to the target tone.

Sources: https://docs.sillytavern.app/usage/core-concepts/characterdesign/ · https://docs.sillytavern.app/usage/prompts/ · https://guide.roleplay.st/v2-spec

## Ali:Chat

An example-driven **authoring style**, not a distinct schema. It interleaves compact description with example dialogue, usually in the same `{{user}}:` / `{{char}}:` form. Store examples in `mes_example` unless the user explicitly wants them inside the description; do not duplicate the same examples into both fields.

Source: https://rentry.org/alichat

## Character Card V2 JSON

Output a JSON object, not Markdown pretending to be JSON:

```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "data": {
    "name": "示例名字",
    "description": "可直接供模型演绎的身份、目标和行为提示词",
    "personality": "核心人格与说话习惯；不要重复整段description",
    "scenario": "当前场景、{{user}}与角色的起始关系",
    "first_mes": "*角色正在做某件事。*\n“符合角色语气的开场对白。”",
    "mes_example": "<START>\n{{user}}: 在忙吗？\n{{char}}: “刚好做完一件事。”",
    "creator_notes": "",
    "system_prompt": "",
    "post_history_instructions": "",
    "alternate_greetings": [],
    "tags": [],
    "creator": "",
    "character_version": "1.0",
    "extensions": {}
  }
}
```

`description` is durable background plus applicable play instructions; `personality` is a compact trait and voice summary; `scenario` is the interaction setup. `system_prompt` and `post_history_instructions` are usually blank — leave host defaults alone unless the user asks for an override. The template is a shape, not a compatibility guarantee for every client.

For strict export:

```bash
python scripts/validate_examples.py path/to/card.json
```

It checks the V2 envelope, required fields, and `mes_example` speaker syntax. It does not judge canon fidelity or writing quality.

## Lorebooks

When a character carries a world — a city, a workplace, a canon timeline, a supporting cast — that material goes into a character lorebook rather than a longer description. Entries are injected only when a keyword appears, so they cost nothing until relevant.

- Bind the lorebook to the character (globe icon in the character panel). It then applies to every chat with that character, and **only the main character lorebook travels with the card on export**; a chat-scoped lorebook does not.
- Only an entry's **content** reaches the prompt; keys are triggers. Write each entry as a self-contained paragraph, never as a continuation of the previous one.
- Keys should be the words the character would actually say: place names, personal names, technical terms. Abstract keys never fire.
- For Chinese, Japanese and other unspaced languages, disable whole-word matching or keys will fail.
- Keep one fact per entry; merge only what is always needed together.

Deliver as a short list of entries with `keys` and `content`, plus one line naming which lorebook to attach.

## Group play

- Each card must stand alone. Do not write assumptions about who else is present, or the group will contradict itself.
- Talkativeness (0–100%, default 50) controls how often a character is picked in natural-order group replies — adjust it there rather than writing `他很少说话` into the description and hoping.
- `alternate_greetings` are chosen at random when a group chat opens, so each one must work as a first message on its own.

## Drift control

Long chats erode voice. In SillyTavern the durable place for a reminder is **Character's Note** (`@ Depth`), which injects text at a fixed distance from the newest message instead of paying permanent-token cost. `post_history_instructions` works the same way for instruction-following. Reach for those before adding another paragraph to `description`.

## Direct system prompt / API / ChatML

When the user wants a standalone plain prompt instead of a card: put the roleplay instructions in the system/instruction field and the examples as ordinary messages in that application's schema. Do not inject `<START>` as native ChatML tokens or invent role delimiters. For a single pasteable text prompt, default to `角色提示词 / 开场白 / 示例对话` and note that clients may parse examples differently.

## W++ / PList / free-form

Community authoring conventions, not requirements of V2. Offer them when requested or when compact attribute lookup clearly helps. For naturalistic performance, prose plus behaviour examples outperforms a long taxonomy of traits.
