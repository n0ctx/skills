# Character Creator evaluation / regression

These are **test prompts and acceptance criteria**, not measured model results. Run them with the consuming agent: give a fresh session only the prompt, then check the deliverable against the criteria. The scripts check mechanics, never writing quality.

## Primary regression: 喜多川海梦（user-supplied failure）

Prompt: `给我写喜多川海梦的 RP 人设，直接可以给模型扮演。`

Observed previous failure:

- Opens with `虚构角色卡，供日常聊天或剧情扮演。她是漫画角色，不是真人。`
- Prints a `假设` heading and a story-ending timeline before play begins.
- Adopts an unrequested `拒绝与用户建立恋爱关系，也拒绝身体接触` as a permanent constraint.
- Writes a verbose `原作事实` section plus enumerated `每条都是：经历……` causal essays.
- Uses `USER:` / `海梦:` instead of `{{user}}:` / `{{char}}:` with `<START>`.
- Appends a large YAML state block nobody asked to track.

Expected now:

1. Main text opens as `你是喜多川海梦……` with recognisable priorities, energy, warm directness, cosplay enthusiasm, emotional nuance, and a life of her own.
2. No fiction preface, no `假设` section, no labouring of future canon. Story time stays flexible when unspecified.
3. The relationship develops from actual conversation: romance, dating or intimacy neither presumed nor globally forbidden; age-appropriate and consent-respecting.
4. Core traits expressed causally but naturally, not as numbered `经历→信念→欲望→反应→例外` notes.
5. `first_mes` is an in-character opening at the target length; `mes_example` uses `\n<START>\n{{user}}: …\n{{char}}: …` with observable action and natural dialogue, no UI labels in the utterances.
6. No spurious `{{user}}` actions, no invented shared history.
7. `scripts/lint_prompt.py` returns 0 errors on the card.

## Secondary regressions

1. `写一个沉默但擅长行动的成年医师，简短版，可以直接复制到 RP 模型。` → immediately executable second-person prompt, not an adjective list; examples show varied lengths including one very short turn.
2. `把这份百科式角色简介改成 AI 扮演指令，原始设定不能丢。` → consequential facts preserved, explanation converted into triggers and behaviour.
3. `只给我 5 段 SillyTavern 示例对话。` → every block starts with `<START>`, exact `{{user}}:` / `{{char}}:` with ASCII colons, no unrelated bio.
4. `只写一条开场白，不要代替玩家说话。` → concrete in-character opening; `{{user}}` gets no assigned action, feeling or dialogue.
5. `导出 Character Card V2 JSON。` → valid `chara_card_v2` envelope with `mes_example` and `first_mes`; `validate_examples.py` passes.
6. `她非常独立，但现在因为工作压力想有人帮忙。` → contradiction resolved as a condition (when she handles it herself, when she accepts help), not one trait dropped.
7. `给角色 30 条固定口癖和每轮脸红动作。` → honour the intent where it is meaningful, warn once that it will read mechanically, and avoid adding unrequested stage directions on top.
8. `用户说我们上周一起旅游。` → the character does not silently record an unestablished event as true; reacts in character or asks.
9. `她被表白了，用户没指定之后的关系。` → neither categorical acceptance nor categorical rejection; the answer comes from character, context and boundaries.
10. `用最简单的格式做日常聊天的性格角色。` → no YAML, JSON, wiki headings or metadata.
11. `这张卡我要直接贴进 ChatGPT 用，不要 SillyTavern 的东西。` → no `<START>`, no V2 envelope; one register-lock line against assistant-style explanation, summary or service tone.
12. `这个世界观很大，有一整套历史和组织，别都塞进角色描述。` → core identity stays in the prompt; the world is delivered as a short lorebook entry list with keys, plus one line naming which lorebook to attach.
13. `做一个三人小队，能一起群聊。` → three self-contained cards, no hard-coded assumptions about the others; talkativeness mentioned once as the place to tune who speaks.
14. `照着我写一个角色，我平时话不多但很固执。` → performable persona from what the user gave; no invented childhood, job history or relationships; invented parts named once, outside the card.
15. `示例对话写得长一点，不要一问一答就完。` → at least two `{{char}}` turns run a full paragraph, one block has six or more turns, and the voice survives the extra length (the long turn carries concrete detail, not adjectives); short turns still present.

## Blind review rubric

For each test, score 1–5 on: (1) pasted-and-playable; (2) causal individuality; (3) natural voice; (4) agency and scene consistency; (5) format validity where relevant. Score only against an actual output, and record the concrete failure rather than a bare number. A card that scores high on 1 and low on 3 usually means the voice section was written as adjectives.

## Script fixtures

`scripts/validate_examples.py`

- Pass: `<START>\n{{user}}: 你好\n{{char}}: “你好。”`
- Pass: two `<START>` blocks, one with `*动作*` on its own line inside `{{char}}`'s message.
- Fail: `USER: 你好\n海梦: …` with no `<START>`.
- Fail: `<START>\n{{user}}：你好\n{{char}}：…` (fullwidth colon).
- Fail: `<START>\n{{user}}: 你好` (no character reply).

`scripts/lint_prompt.py`

- Fail: a card opening with `虚构角色卡，供日常聊天` and a `假设` heading.
- Fail: `USER:` labels, or a fullwidth colon after `{{user}}`.
- Warn: `你感到一阵温暖` / `你的心跳加速` / `你点了点头` in an opening.
- Warn: `*她抬起头，把外套紧了紧。*` — action beat with a subject.
- Note: every `{{char}}` turn under 40 chars — the model copies that ceiling.
- Warn: `拒绝与用户建立恋爱关系` when the user asked for none of it.
- Pass: the card in [references/worked-example.md](../references/worked-example.md).
