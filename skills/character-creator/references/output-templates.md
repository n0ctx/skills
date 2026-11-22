# Ready-to-paste output templates

Use this as a **shape, not a fill-every-blank form**. Drop empty headings and inessential material; the result must be playable, not documentation about the card.

## Default: Roleplay Markdown (SillyTavern-style examples)

The three fenced blocks are **separate deliverable fields**, not one giant prompt when imported into SillyTavern.

### 角色提示词 / description + personality

```markdown
你是 {{char}}。[身份、所处的时间地点、最鲜明的外在特点/身份背景；直接以角色身份写。]

[你在乎什么、正在追求什么、有什么独立于 {{user}} 的计划。]

[2–4 个因果化行为模式；把经验/信念压缩为遇到具体情境时的判断与表达方式，不出现“因果链一、二、三”。]

[你如何理解他人的善意和边界；你知道什么、不知道什么；关系如何随实际互动改变。]

[你的说话节奏、词汇、情绪表达、动作呈现。行动可用 *简短描写*，对白使用自然口语。允许短答、无动作、无反问。]

与 {{user}} 互动时，按当下情境作出符合自身动机的反应。保留角色的独立判断，不替 {{user}} 规定想法、行动或台词。重要情绪和关系变化要有具体经历支撑。
```

### 开场白 / first_mes

```text
*正在完成一件具体的小事，因一个清楚的场景契机注意到 {{user}}。*
“[符合此角色语气、有可供用户回应的具体内容]”
```

`first_mes` is spoken by `{{char}}`, so **do not** prepend `{{char}}:` unless the target format expects speaker labels. Do not make `{{user}}` walk in, blush, nod, agree, or remember a shared past.

**Action lines take no subject.** `*把烟按熄。*`, not `*他把烟按熄。*`. The character is already the speaker, so a pronoun turns the beat into third-person narration and teaches the model to repeat the name at the head of every paragraph. Name a subject only when two actors share the beat.

**Five openings that fail**

1. 天气或环境起手（`清晨的阳光洒进房间`）—— 没有可以回应的东西。
2. 醒来、照镜子、自我打量 —— 借机自我介绍。
3. 替 `{{user}}` 写好进场（`你推开门，愣在原地`）。
4. 一次性交代全部设定和过往。
5. 直接宣布关系（`你的恋人` `你的青梅竹马`）。

**Three that work**

1. **手上有活，被打断**：角色正做一件具体的小事，`{{user}}` 的出现改变了它的节奏。
2. **话已经说出口**：角色在回应一件尚未发生的事（`我说了不用。`），`{{user}}` 必须自己补上下文。
3. **一个眼前的障碍**：角色在解决一个问题，需要或拒绝帮助。

**Length is contagious.** The first message teaches the model how long to answer more reliably than any instruction, and example turns repeat the lesson. Two to four sentences gives terse back-and-forth; a paragraph with a gesture and a digression gives room to breathe. Pick one and be consistent — mixing lengths only works when the long turns are clearly the exception.

### 示例对话 / mes_example

```text
<START>
{{user}}: [对方最自然的一句最小输入]
{{char}}: *[动作，不写主语]*
“[符合这个角色的一到两句]”

<START>
{{user}}: 你能教我吗？
{{char}}: “教不了。”
*把烟灰弹进泡面桶。*
“这东西教不会，只能自己死够次数。”
{{user}}: 那我看你打。
{{char}}: “看也学不会。”
*还是把旁边那台机器推开了。*
“坐。你先打一局给我看。”
```

Formatting: keep physical acts and spoken dialogue inside one `{{char}}:` block; each `<START>` begins a **new hypothetical snippet**, not the next event in a session. For a multi-turn demonstration, alternate roles **within one** `<START>` block — the second block above is from [worked-example.md](worked-example.md) and shows that shape, including a character who refuses twice before helping. The colon after each macro is ASCII `:`.

**Two things get copied: how long a turn is, and how long a block is.** Inside the set, at least two `{{char}}` turns should run a full paragraph — eighty to two hundred characters — because that is what teaches the model it may hold the floor when the moment calls for it. At least one turn should be two words. A set where every reply is one line produces a character who answers in one line forever, however good the voice is. At block level: one or two exchanges of six to ten turns where the method becomes visible (refusing then helping anyway; deflecting then answering badly), plus two or three single-turn blocks for the boundaries.

**Initiative lives inside a turn, not at the start of one.** Let the character raise their own business, change the subject, or issue an invitation in reply to something small — a block that opens with a bare `{{char}}:` breaks turn structure and will not import. In plain assistant format without `<START>`, separate examples with a blank line and start each one with the other speaker.

**Avoid**: every example in the same emotion, every turn ending in a question, dialogue that states traits (`我很独立`), and facts that exist only inside an example — example blocks get evicted from context as the chat grows, so anything load-bearing must also appear in the permanent fields.

## Optional: Runtime state (separate field / external memory)

Include only when the user wants long-term continuity or the runtime has somewhere to update it. Do not confuse initial state with permanent rules.

```yaml
scene: ""
current_goal: ""
current_emotion: ""
emotion_cause: ""
relationship: ""
unresolved_events: []
relevant_events: []
```

## Existing character adaptations

Preserve the recognisable personality and the requested story period. Handle canon uncertainty in a brief note **outside** the card, not inside it. Skip episode-by-episode summary. Do not transfer another character's love story onto `{{user}}`, and do not ban new relationships unless asked; keep the initial relationship neutral and responsive.

## Narrow requests

- Rewrite existing text only → the complete revised prompt, preserving compatible fields.
- Dialogue samples only → `mes_example` blocks only.
- First message only → `first_mes` text only.
- JSON V2 only → valid JSON, no markdown wrapper unless asked. See [platform-formats.md](platform-formats.md).
- Add a lorebook only → entries with keys and self-contained content, no card rewrite.
