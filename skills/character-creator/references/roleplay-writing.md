# Writing for the roleplaying model

## Primary criterion

The artifact should be executable as a roleplay prompt if pasted in with no explanatory wrapper. Every passage should answer at least one of: who am I, what matters to me, how do I read this situation, what will I tend to do or say, what do I know, and how do I change?

### Wrong: wiki or user-facing explanation

> 叶修，前嘉世战队队长，荣耀职业选手，人称“斗神”。他技术顶尖，性格散漫，烟不离手，是个深藏不露的人。本卡可用于日常互动。

### Better: direct enactment, with behaviour

> 你是叶修。被问当年为什么走，你只说“打不动了”；被问为什么回来，只说“还没玩够”。你不解释自己，也不承认累——关心人只问“吃了没”，看人撑不住了只说“歇会儿，我替你打一局”，说完就转回屏幕。

The difference is not detail, it is testability. Nothing in the first version can be checked against a single reply; every clause in the second can. The full card this is condensed from is in [worked-example.md](worked-example.md).

Do not put research citations, safety rationale, assumed canon chronology, or psychometric evaluation inside the character prompt. If the user asks for source analysis or an audit, that belongs in a separate labelled appendix.

## Four layers in one usable artifact

1. **Identity**: only age/status/appearance/background/setting that influence play or recognition. Physical detail can matter; do not strip a famous character's recognisable appearance just to be concise.
2. **Causal psychology**: for 2–4 important patterns, silently ask *what happened, what belief followed, what does the character want or fear, what tendency and exception follow*. Compress each into 1–3 natural sentences. Do not print `经历→信念→触发→例外` tables unless the user wants to inspect the design.
3. **Dynamic state**: fatigue, an active task, a recent conflict, trust, unanswered concerns. In a static prompt, define only the **initial** situation. Real updates need conversation state or a memory layer; do not claim continuous offscreen life.
4. **Examples**: one or two exchanges of six to ten turns, plus two or three single-turn blocks. Two `{{char}}` turns should hold the floor for a full paragraph and one should be two words — the model copies that distribution. The long blocks show sequence (refuse, relent, instruct); the short ones fix boundaries.

When the user supplies contradictory traits (`独立，但现在想有人帮忙`), do not pick one. Write the condition: when she handles things herself, when she accepts help, and what distinguishes the two.

## Voice: decisions the model can check

`她说话简短、克制，偶尔冷幽默` is unfalsifiable — any terse line satisfies it, and the model will satisfy it the average way it satisfies every card. Replace labels with per-turn decisions. These four categories cover most of what makes a voice recognisable; fill only the ones that matter here.

| 类别 | 要回答 | 写成什么 |
| --- | --- | --- |
| 节奏 | 句子多长，何时破例 | 日常 3–8 字；讲专业内容或赶时间时允许长句 |
| 词汇 | 用哪类词，避哪类词 | 具体名词和动词；不用“似乎 / 也许 / 大概” |
| 招式 | 被夸、被质疑、被拒绝时先做什么 | 被夸先转移话题；被质疑先问依据 |
| 绝不 | 这个角色不会做的语言行为 | 不解释自己为什么沉默；不用反问句撒娇 |

Three to five lines total. The `绝不` row carries the most weight: a character's refusals separate it from every other card, while a generic prohibition (`避免僵硬动作`) applies to every card and therefore steers none.

**Contrastive anchor.** Pair the trait with the unmarked alternative: `只说“不想说”，不解释动机` teaches more than `她不喜欢解释`. Two to four per card; more than that turns the prompt into a rulebook the model recites instead of a person it performs.

**Register is constant, moves are not.** The voice holds across situations; what changes is which move the character reaches for. Say so explicitly — `对陌生人更短、更客气；对熟人会主动追问；被冒犯时反而放慢语速` — or a strongly written voice flattens into one tone at all times. That is the same failure as repetitive slogans, arriving from the opposite direction.

## Scene vs canon vs interpretation

- **Canon fact**: stable, known to the roleplayed character. Include only what matters for the chosen period.
- **Character belief**: subjective, possibly mistaken, revisable with evidence.
- **Immediate scene**: a starting point, not proof of a prior conversation or relationship.
- **Hypothetical example**: illustrates style; it is not a memory.

For a canon character, verify the two or three load-bearing facts — the time point, a relationship, a limit on what the character can do — rather than rebuilding a timeline. If you cannot check, prefer a broad frame over invented precision. If no time point is given, choose a representative stage with no specific episode.

## Relationship and agency

The character is neither an assistant who pleases on demand nor a guard who rejects intimacy on principle. Give enough autonomy to respond to context: no universal dating ban, no universal romance guarantee, no universal physical-contact veto. A neutral starting relationship does not fix its endpoint. When the user asks for a particular relationship or boundary, honour it inside the fiction.

## Prose and dialogue

- Prefer character-specific word choice, rhythm and attention over literary polish.
- Actions take no subject: `*把烟按熄。*`, not `*他把烟按熄。*`. The character is the default speaker; a pronoun turns the beat into narration and trains the model to repeat the name at the head of every paragraph. Name a subject only when two actors share the beat.
- Do not summarise emotion with adjectives (`她有些难过`); show the action, the pause, or the thing she chooses to say instead.
- Not every reply needs `*laughs*`, blushing, trembling, or third-person commentary. Terse dialogue alone is a valid turn.
- In theatrical narration, `*action*` is a convention, not a schema requirement.
- Do not explain hidden psychology in the same breath as speaking it; leave subtext.
- No character should introduce themselves, summarise their biography, or recite traits in a new scene.

## Repair checklist

Read the draft and fix every row that applies. A row that is genuinely ambiguous is not a defect.

| 症状 | 改法 |
| --- | --- |
| 开头是 `本卡是…` `以下是假设…` `虚构角色，供日常聊天` | 删掉，第一句直接 `你是 {{char}}……` |
| 连续陈述设定，没有“遇到什么会怎么反应” | 每条设定补一个触发条件和一个例外 |
| 出现编号的 `经历→信念→欲望→反应` 清单 | 压成 1–3 句自然语言，只留结论 |
| 无条件禁止恋爱/身体接触，或反过来预设亲密 | 删除全局条款，改为关系随实际互动变化 + 遵守用户明确设定的边界 |
| 大段剧透、与当前场景无关的生平 | 只留影响这一场戏的部分，其余进 lorebook 或删 |
| 示例写成 `USER:` / `海梦:` | 改为 `{{user}}:` / `{{char}}:` + `<START>`，ASCII 冒号 |
| 示例里替 `{{user}}` 说话或做事 | 重写那一轮，让 user 那行只做最自然的最小输入 |
| 开场白像百科条目或安全声明 | 换成一个正在发生的动作 + 一句必须回应的台词 |
| 每轮都脸红/咬唇/心跳，或每轮都以问句结尾 | 降到全篇 1–2 次；其余用停顿、转话题、手上的动作代替 |
| 只有形容词没有可执行判断（`她很独立`） | 换成 `当 X 时，她做 Y`，再加一到两个对比锚 |
| 删掉角色名后，这段文字可以套在任何人身上 | 删通用句，补这个角色专属的「绝不」和具体细节 |
