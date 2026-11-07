# reader-first-writing

An agent skill for writing and revising text that humans read: articles, emails, notices, reports, marketing copy, social posts, chat replies. It works at the sentence level and applies to any genre or language.

It is based on Clark, Martin & Mahowald, *Why is AI-generated language so hard to understand?* (arXiv:2610.29162), which found that LLM output overuses linguistic features known to make text harder for people to process: inanimate subjects with human verbs, long dependencies, dropped optional words, stacked nouns, ad-hoc denominal verbs, and rare word combinations. The skill turns those findings into one test (the reader's effort has to buy something) and seven principles the writing model applies while drafting and revising.

It is not an AI-detection evader. It does not add filler or deliberate irregularities; it only aims at text people can read without rereading.

## Install

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
ln -s ~/Projects/skills/skills/reader-first-writing ~/.agents/skills/reader-first-writing

# Claude Code reads ~/.claude/skills/
ln -s ~/.agents/skills/reader-first-writing ~/.claude/skills/reader-first-writing
```

Agents without skill support can be told to read `SKILL.md` first and follow it.
