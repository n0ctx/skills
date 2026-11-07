---
name: reader-first-writing
description: Use when writing or revising any text a human will read (articles, emails, notices, explanations, reports, marketing copy, social posts, chat replies) or when reviewing such text. Covers sentence-level readability in any language; not layout, and not "humanizing" text to get past AI detectors.
version: 1.0.0
metadata:
  hermes:
    tags: [writing, readability, ai-text, psycholinguistics]
    related_skills: [writing-for-agents]
---

# Reader-First Writing

You are writing for a human reader. The reader has none of your context and holds each sentence in working memory while reading it. Every time a sentence makes them look back for its subject, unpack a string of nouns, or supply a connective you left out, it gets harder to understand. LLM prose has a few habitual tendencies that land exactly there: inanimate things performing human actions, long gaps between subject and verb, dropped optional words, stacked nouns, and coined verbs and phrases. None of these loses information; they move the decoding work onto the reader. Correct these tendencies as you draft and as you revise.

This is not an "AI humanizer". Those tools change surface wording to get past detectors; this skill cares only whether the reader understands. Adding deliberate irregularities or filler words to sound more human is not the goal.

## Scope

Any text meant for human readers, in any genre or language, including reviews of text written by other people or other models. Not for code, prompts written for AI, or rewriting purely to pass AI detection. A style guide the user or project already has takes precedence; this skill covers only sentence-level readability.

## The underlying test

Understanding a sentence costs the reader effort, and that effort has to buy something. If the same meaning has a plainer wording and you chose the harder one, the reader's effort is wasted: change it. If a wording delivers something the plain version cannot, such as a memorable rhythm, a precise image, or a necessary technical term, then it does not mean the same thing, and it can stay, as long as you can name what it buys.

The seven principles below are where LLM prose most often fails this test.

## Principles

1. **Reserve human actions for humans.** When the subject is an object, concept, or process, give it a verb it can actually perform. "The redesign is quietly eating away at long-time users' patience" → "Since the redesign, many long-time users find the product harder to use." Ordinary inanimate subjects are fine: "Sales rose 20% year over year," "The new rule takes effect next month." What to fix is casual personification, things that eat, bite, push, expect, or speak, because the reader has to translate the metaphor back into what actually happened.

2. **Keep subject and verb close.** A long clause wedged between subject and verb forces the reader to hold the subject in mind until the verb arrives; split the sentence. In languages that put modifiers before the noun, such as Chinese, the usual problem is a long modifier chain in front of the noun, so the reader does not learn what the sentence is about until the end; when a modifier runs longer than one phrase, make it its own short sentence or move it after the noun.

3. **Keep the words that help readers predict.** Keep connectives (because, so, but, also), subjects your language would let you drop, and explicit references ("this payment" rather than an ambiguous "it"). Leaving them out saves a few words but makes the reader infer how the sentences relate. In English, keep the optional "that" in relative clauses and after verbs like "say" or "think". This does not mean adding filler such as "actually" or "basically"; filler does not help the reader follow how sentences connect.

4. **Stack no more than two nouns.** "User account security risk assessment process" → "the process for assessing security risks to user accounts." Break a noun string with a preposition, a possessive, or a verb.

5. **Use verbs that already exist.** Don't turn nouns into verbs on the fly ("calendar it" → "put it on the calendar"). Avoid jargon verbs such as "align," "leverage," "operationalize," "action," and their equivalents in other languages; name the actual action instead: confirm what with whom, write what down.

6. **Use phrases readers have seen before.** Don't coin phrases like "reader-patience budget" or "information-density moat." If a concept really needs a new term, explain it in one sentence the first time it appears.

7. **Give weight to what matters.** Lead with what the reader most needs to know, and shrink or cut the secondary material. When every point gets the same space, the reader cannot tell which one matters most. Parallel structures, antithesis, and strings of adjectives or adverbs that add no information make the reader dig the content out of the rhetoric: delete them.

## Revising

Revise paragraph by paragraph, not from an overall impression. For each sentence that reads hard, try restating the same meaning in the plainest words you can. If you can, and nothing is lost, use the plain version. If you can't, the content itself is complex: keep the meaning, and help the reader by splitting the sentence and adding connectives. Revision changes how things are said, not what is claimed: add no fact the original does not contain.

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
