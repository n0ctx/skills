---
name: reader-first-writing
description: MUST use for all writing and messaging for human readers, including drafting, revising, editing, reviewing, and discussions.
version: 1.1.0
metadata:
  hermes:
    tags: [writing, readability, ai-text, psycholinguistics]
    related_skills: [writing-for-agents]
---

# Reader-First Writing

You are writing for a human reader. The reader has none of your context and holds each sentence in working memory while reading it. Every time a sentence makes them look back for its subject, unpack a string of nouns, supply a connective you left out, or guess a premise the page never states, it gets harder to understand. LLM prose has a few habitual tendencies that land exactly there: inanimate things performing human actions, long gaps between subject and verb, dropped optional words, stacked nouns, coined verbs and phrases, sentences that depend on a premise this page has not stated, and metaphors or spoken phrases that add no distinction. None of these loses information; they move the decoding work onto the reader. Correct these tendencies as you draft and as you revise.

This is not an "AI humanizer". Those tools change surface wording to get past detectors; this skill cares only whether the reader understands. Adding deliberate irregularities or filler words to sound more human is not the goal.

## Scope

Any text meant for human readers, in any genre or language, including discussions and reviews. Messaging means composing or discussing message content, not merely sending or retrieving messages. Discussion or review alone does not authorize rewriting. For text intended both to guide an AI agent and to be read by humans, apply this skill alongside `writing-for-agents`; not for code or prompts intended only for AI. Do not rewrite purely to pass AI detection. A style guide the user or project already has takes precedence. This skill covers whether a reader who has only this page can follow each sentence, including a premise that sentence depends on. It does not set document structure, length, or tone.

## The underlying test

Understanding a sentence costs the reader effort, and that effort has to buy something. If the same meaning has a plainer wording and you chose the harder one, the reader's effort is wasted: change it. If a wording delivers something the plain version cannot, such as a memorable rhythm, a precise image, or a necessary technical term, then it does not mean the same thing, and it can stay, as long as you can name what it buys.

The principles below are where LLM prose most often fails this test.

## Principles

1. **Reserve human actions for humans.** When the subject is an object, concept, or process, give it a verb it can actually perform. "The redesign is quietly eating away at long-time users' patience" → "Since the redesign, many long-time users find the product harder to use." Ordinary inanimate subjects are fine: "Sales rose 20% year over year," "The new rule takes effect next month." What to fix is casual personification, things that eat, bite, push, expect, or speak, because the reader has to translate the metaphor back into what actually happened.

2. **Keep subject and verb close.** A long clause wedged between subject and verb forces the reader to hold the subject in mind until the verb arrives; split the sentence. In languages that put modifiers before the noun, such as Chinese, the usual problem is a long modifier chain in front of the noun, so the reader does not learn what the sentence is about until the end; when a modifier runs longer than one phrase, make it its own short sentence or move it after the noun.

3. **Keep the words that help readers predict.** Keep connectives (because, so, but, also), subjects your language would let you drop, and explicit references ("this payment" rather than an ambiguous "it"). Leaving them out saves a few words but makes the reader infer how the sentences relate. In English, keep the optional "that" in relative clauses and after verbs like "say" or "think". This does not mean adding filler such as "actually" or "basically"; filler does not help the reader follow how sentences connect.

4. **Stack no more than two nouns.** "User account security risk assessment process" → "the process for assessing security risks to user accounts." Break a noun string with a preposition, a possessive, or a verb.

5. **Use verbs that already exist.** Don't turn nouns into verbs on the fly ("calendar it" → "put it on the calendar"). Avoid jargon verbs such as "align," "leverage," "operationalize," "action," and their equivalents in other languages; name the actual action instead: confirm what with whom, write what down.

6. **Use phrases readers have seen before.** Don't coin phrases like "reader-patience budget" or "information-density moat." If a concept really needs a new term, explain it in one sentence the first time it appears.

7. **Give weight to what matters.** Lead with what the reader most needs to know, and shrink or cut the secondary material. When every point gets the same space, the reader cannot tell which one matters most. Parallel structures, antithesis, and strings of adjectives or adverbs that add no information make the reader dig the content out of the rhetoric: delete them.

8. **Supply the premise the sentence depends on.** A short sentence can still stop the reader if it treats as already known a person, decision, constraint, or earlier event this page has not stated. Task training under a length penalty drops those premises even when you still know them. Before the sentence that needs it, give the missing premise in one sentence. Do not open a background section, restate what the reader just said, or repeat what is already on the page. If you cannot name the premise the reader would have to guess, the sentence does not have this problem. When you are revising text you did not write, do not invent a premise the source does not contain; if the source states it elsewhere, move it next to the sentence.

> Before: The sync should merge per device.
> After: The same account writes a separate record on each device, and the later write overwrites the earlier one. The sync should merge per device instead of replacing the whole record.

9. **Do not explain by decorating.** A metaphor, analogy, or strongly spoken phrase stays only when you can name a distinction the plain sentence cannot draw. If deleting it leaves the reader knowing the same thing, delete it. The literal claim has to be in the sentence either way, because the reader should not have to translate the image back into the fact.

> "Think of the cache as a coat check" fails when "the cache stores a result so the same request is not computed again" already says it. Keep an analogy only when it is the only way to show a structural difference, and still state the fact.

## Revising

Revise paragraph by paragraph, not from an overall impression. For each sentence that reads hard, try restating the same meaning in the plainest words you can. If you can, and nothing is lost, use the plain version. If you can't, the content itself is complex: keep the meaning, and help the reader by splitting the sentence and adding connectives. Revision changes how things are said, not what is claimed. Add no fact the source does not contain. The one exception is principle 8: while drafting, a premise you know and the sentence depends on is not a new claim; when revising text you did not write, only move a premise the source already states.

If the plain restatement is still opaque to someone who has only this page, the gap is a missing premise, not a need for color. Apply principle 8. Do not reach for an analogy, a spoken intensifier, or a second explanation of the same point.

An example of the direction and size of a revision:

> Before: This release comprehensively empowers an upgraded user data sync experience, systematically resolving the cross-device content loss pain point, and going forward we will continue to consolidate user feedback and align on optimization directions.
>
> After: This update improves data sync and fixes the bug that lost content when switching between devices. We will keep collecting feedback and use it to decide what to improve next.

The revision drops "empowers," "consolidate," and "align"; breaks up the noun stacks "user data sync experience" and "cross-device content loss pain point"; replaces the abstract actor "this release empowers" with "this update" and "we"; and splits one long sentence so that each sentence says one thing.

## Before you hand it over

Go through the text paragraph by paragraph. For every "yes" below, apply the underlying test to decide whether to change it:

- Is an object or concept performing a human action?
- Is there a modifier longer than one phrase in front of a noun, or a long clause between subject and verb?
- Has a connective, subject, or reference been dropped?
- Are three or more nouns stacked together?
- Is there a noun used as a verb, a jargon verb, or a coined phrase the reader has not seen?
- Is what the reader most needs to know near the front?
- Is there parallelism, antithesis, or a string of modifiers that adds no information?
- Does a sentence depend on a person, decision, constraint, or event this page has not stated?
- After the literal claim is written, does a metaphor, analogy, or spoken phrase still add a distinction you can name?
